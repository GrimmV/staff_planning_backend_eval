"""
Estimate paired stratified bootstrap uncertainty for label-based metrics.

Metrics:
    - Exact match
    - Harmful optimism (at-risk)
    - Warning preservation

Bootstrap design:
    - resample at the case level, not per setting
    - keep the same resampled cases paired across all evaluation modes
    - resample within silver-label strata to preserve the balanced 50/50/50 design
"""

from __future__ import annotations

import argparse
import csv
import os
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

from alignment_analysis import (
    EVALUATION_MODES,
    ScoreLabel,
    discover_model_slug,
    load_balanced_diff_keys,
    load_balanced_silver_labels,
    load_mode_pairs,
    save_json,
)
from dissertation_figure_style import (
    MODE_COLORS, MODE_LABELS, MODE_MARKERS, WIDTH, apply_style,
    percentage_axis, export_figure,
)
from label_metrics import evaluate_pairs

OUTPUT_DIR = "cache_experiments/analysis/label_metric_uncertainty"
WARNING_LABELS = {"eher ablehnen", "ablehnen"}
BOOTSTRAP_SEED = 42
DEFAULT_BOOTSTRAP_SAMPLES = 10_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate paired, stratified bootstrap confidence intervals for "
            "label-based evaluation metrics."
        )
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model slug or name used in cache_evaluations folders "
            "(default: auto-detect from available evaluation caches)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory for summary JSON, CSV table, and CI plot.",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=DEFAULT_BOOTSTRAP_SAMPLES,
        help=f"Number of paired stratified bootstrap samples (default: {DEFAULT_BOOTSTRAP_SAMPLES}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=BOOTSTRAP_SEED,
        help=f"Random seed for bootstrap resampling (default: {BOOTSTRAP_SEED}).",
    )
    return parser.parse_args()


def compute_warning_preservation(pairs: Sequence[Dict[str, Any]]) -> float | None:
    warning_cases = [pair for pair in pairs if pair["silver_label"] in WARNING_LABELS]
    if not warning_cases:
        return None
    preserved = sum(
        1 for pair in warning_cases if pair["assessment_score"] in WARNING_LABELS
    )
    return preserved / len(warning_cases)


def build_metric_arrays(
    case_records: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, np.ndarray]]:
    silver_ord = np.array(
        [
            {"eher akzeptieren": 0, "eher ablehnen": 1, "ablehnen": 2}[record["silver_label"]]
            for record in case_records
        ],
        dtype=np.int8,
    )
    at_risk_mask = silver_ord > 0

    arrays: Dict[str, Dict[str, np.ndarray]] = {}
    for mode in EVALUATION_MODES:
        pred_ord = np.array(
            [
                {
                    "eher akzeptieren": 0,
                    "eher ablehnen": 1,
                    "ablehnen": 2,
                }[record["pairs"][mode]["assessment_score"]]
                for record in case_records
            ],
            dtype=np.int8,
        )
        arrays[mode] = {
            "exact_match": (pred_ord == silver_ord),
            "harmful_optimism_at_risk": (pred_ord < silver_ord) & at_risk_mask,
            "warning_preservation": (pred_ord > 0) & at_risk_mask,
            "at_risk_mask": at_risk_mask,
        }

    return arrays


def build_paired_case_records(model_slug: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    allowed_diff_keys = load_balanced_diff_keys()
    silver_labels = load_balanced_silver_labels()

    if not silver_labels:
        raise FileNotFoundError("No balanced silver labels found.")

    mode_pairs_by_key: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for mode in EVALUATION_MODES:
        pairs = load_mode_pairs(mode, model_slug, silver_labels, allowed_diff_keys)
        mode_pairs_by_key[mode] = {pair["diff_key"]: pair for pair in pairs}

    case_records: List[Dict[str, Any]] = []
    missing_cases: Dict[str, List[str]] = {}
    for diff_key in sorted(allowed_diff_keys):
        silver_label = silver_labels.get(diff_key)
        if silver_label is None:
            continue

        missing_modes = [
            mode for mode in EVALUATION_MODES if diff_key not in mode_pairs_by_key[mode]
        ]
        if missing_modes:
            missing_cases[diff_key] = missing_modes
            continue

        case_records.append(
            {
                "diff_key": diff_key,
                "silver_label": silver_label,
                "pairs": {
                    mode: mode_pairs_by_key[mode][diff_key] for mode in EVALUATION_MODES
                },
            }
        )

    if missing_cases:
        preview = ", ".join(
            f"{diff_key} ({'/'.join(modes)})"
            for diff_key, modes in list(missing_cases.items())[:5]
        )
        raise FileNotFoundError(
            "Missing evaluation outputs for some balanced cases across modes: "
            f"{preview}"
        )

    stratum_sizes: Dict[str, int] = {}
    for record in case_records:
        label = record["silver_label"]
        stratum_sizes[label] = stratum_sizes.get(label, 0) + 1

    return case_records, stratum_sizes


def stratify_case_indices(
    case_records: Sequence[Dict[str, Any]],
) -> Dict[ScoreLabel, np.ndarray]:
    strata: Dict[ScoreLabel, List[int]] = {
        "ablehnen": [],
        "eher ablehnen": [],
        "eher akzeptieren": [],
    }
    for idx, record in enumerate(case_records):
        strata[record["silver_label"]].append(idx)
    return {
        label: np.array(indices, dtype=int) for label, indices in strata.items() if indices
    }


def summarize_bootstrap_distribution(
    samples: np.ndarray,
) -> Dict[str, float | List[float]]:
    lower, upper = np.percentile(samples, [2.5, 97.5])
    return {
        "mean": float(np.mean(samples)),
        "std": float(np.std(samples, ddof=1)),
        "ci_lower": float(lower),
        "ci_upper": float(upper),
    }


def run_paired_stratified_bootstrap(
    case_records: Sequence[Dict[str, Any]],
    n_bootstrap: int,
    seed: int,
) -> Dict[str, Any]:
    strata = stratify_case_indices(case_records)
    if not strata:
        raise ValueError("No case records available for bootstrap.")

    point_estimates: Dict[str, Dict[str, float | None]] = {}
    bootstrap_values: Dict[str, Dict[str, np.ndarray]] = {
        mode: {
            "exact_match": np.empty(n_bootstrap, dtype=float),
            "harmful_optimism_at_risk": np.empty(n_bootstrap, dtype=float),
            "warning_preservation": np.empty(n_bootstrap, dtype=float),
        }
        for mode in EVALUATION_MODES
    }
    metric_arrays = build_metric_arrays(case_records)

    for mode in EVALUATION_MODES:
        mode_pairs = [record["pairs"][mode] for record in case_records]
        label_metrics = evaluate_pairs(mode_pairs)
        point_estimates[mode] = {
            "exact_match": label_metrics["exact_match_rate"],
            "harmful_optimism_at_risk": label_metrics["harmful_optimism_at_risk"],
            "warning_preservation": compute_warning_preservation(mode_pairs),
        }

    rng = np.random.default_rng(seed)
    for sample_idx in range(n_bootstrap):
        sampled_indices_parts: List[np.ndarray] = []
        for indices in strata.values():
            sampled_indices_parts.append(
                rng.choice(indices, size=len(indices), replace=True)
            )
        sampled_indices = np.concatenate(sampled_indices_parts)

        for mode in EVALUATION_MODES:
            at_risk_n = int(metric_arrays[mode]["at_risk_mask"][sampled_indices].sum())
            bootstrap_values[mode]["exact_match"][sample_idx] = float(
                metric_arrays[mode]["exact_match"][sampled_indices].mean()
            )
            bootstrap_values[mode]["harmful_optimism_at_risk"][sample_idx] = float(
                metric_arrays[mode]["harmful_optimism_at_risk"][sampled_indices].sum()
                / at_risk_n
            )
            bootstrap_values[mode]["warning_preservation"][sample_idx] = float(
                metric_arrays[mode]["warning_preservation"][sampled_indices].sum()
                / at_risk_n
            )

    summary_modes: Dict[str, Any] = {}
    for mode in EVALUATION_MODES:
        metric_summary: Dict[str, Any] = {}
        for metric_key, samples in bootstrap_values[mode].items():
            metric_summary[metric_key] = {
                "point_estimate": point_estimates[mode][metric_key],
                **summarize_bootstrap_distribution(samples),
            }
        summary_modes[mode] = metric_summary

    return {
        "point_estimates": point_estimates,
        "bootstrap_values": bootstrap_values,
        "modes": summary_modes,
    }


def write_csv(rows: List[Dict[str, Any]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "metric",
                "mode",
                "point_estimate",
                "ci_lower",
                "ci_upper",
                "bootstrap_mean",
                "bootstrap_std",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_table_rows(summary_modes: Dict[str, Any]) -> List[Dict[str, Any]]:
    metric_labels = {
        "exact_match": "Exact match",
        "harmful_optimism_at_risk": "Harmful optimism (at-risk)",
        "warning_preservation": "Warning preservation",
    }
    rows: List[Dict[str, Any]] = []
    for metric_key, metric_label in metric_labels.items():
        for mode in EVALUATION_MODES:
            stats = summary_modes[mode][metric_key]
            rows.append(
                {
                    "metric": metric_label,
                    "mode": mode,
                    "point_estimate": stats["point_estimate"],
                    "ci_lower": stats["ci_lower"],
                    "ci_upper": stats["ci_upper"],
                    "bootstrap_mean": stats["mean"],
                    "bootstrap_std": stats["std"],
                }
            )
    return rows


def plot_confidence_intervals(
    summary_modes: Dict[str, Any],
    model_slug: str,
    output_path: str,
) -> None:
    del model_slug
    apply_style()
    metric_order = [
        ("exact_match", "Exact match\n(higher is better)"),
        ("harmful_optimism_at_risk", "Harmful optimism\n(lower is better)"),
        ("warning_preservation", "Warning preservation\n(higher is better)"),
    ]
    fig, ax = plt.subplots(figsize=(WIDTH, 3.5))
    fig.subplots_adjust(left=0.31, right=0.96, bottom=0.17, top=0.86)
    for offset, mode in zip((-0.23, 0, 0.23), EVALUATION_MODES):
        for index, (key, _) in enumerate(metric_order):
            stats = summary_modes[mode][key]
            point, lower, upper = [100 * float(stats[k]) for k in
                                   ("point_estimate", "ci_lower", "ci_upper")]
            ax.errorbar(point, index + offset,
                        xerr=[[point - lower], [upper - point]],
                        fmt=MODE_MARKERS[mode], linestyle="none",
                        color=MODE_COLORS[mode], elinewidth=0.9,
                        capsize=3, capthick=0.9, markersize=5,
                        label=MODE_LABELS[mode] if index == 0 else None)
    ax.set_yticks(range(3), [label for _, label in metric_order])
    ax.set_ylim(2.55, -0.55)
    percentage_axis(ax)
    ax.set_xlabel("Proportion of eligible cases")
    fig.legend(*ax.get_legend_handles_labels(), loc="upper center",
               ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.0),
               handlelength=1.4, handletextpad=0.5, columnspacing=1.2)
    export_figure(fig, output_path, "Label alignment and warning-related metrics.",
        "Figure 8.7. Points show estimates; capped lines show 95% percentile confidence "
        "intervals (2.5th-97.5th percentiles) from 10,000 case-level bootstrap resamples "
        "with seed 42, stratified by the three silver-label classes (50 cases each), "
        "using identical sampled case identifiers across configurations. Exact match "
        "is exact categorical agreement over all 150 cases (higher is better). Harmful "
        "optimism is a more accepting assessment than the silver policy among its 100 "
        "warning cases (eher ablehnen or ablehnen; lower is better). Warning preservation "
        "is retention of either warning label among those same 100 cases (higher is better). "
        "Harmful optimism is distinct from false reassurance: ablehnen to eher ablehnen "
        "is optimistic but retains a warning, so optimism and warning preservation are "
        "not complements. The silver-label rules are a diagnostic policy, not objective "
        "planner ground truth. Separate interval overlap does not establish paired significance.")
    plt.close(fig)


def run_analysis(
    model_slug: str,
    output_dir: str,
    bootstrap_samples: int,
    seed: int,
) -> Dict[str, Any]:
    case_records, stratum_sizes = build_paired_case_records(model_slug)
    if len(case_records) != 150 or sorted(stratum_sizes.values()) != [50, 50, 50]:
        raise ValueError("Figure 8.7 requires all 150 paired cases, 50 per silver class.")
    if bootstrap_samples != 10_000 or seed != 42:
        raise ValueError("Figure 8.7 requires 10,000 bootstrap resamples and seed 42.")
    bootstrap_result = run_paired_stratified_bootstrap(
        case_records,
        n_bootstrap=bootstrap_samples,
        seed=seed,
    )

    os.makedirs(output_dir, exist_ok=True)

    rows = build_table_rows(bootstrap_result["modes"])
    csv_path = os.path.join(output_dir, "label_metric_uncertainty.csv")
    write_csv(rows, csv_path)

    chart_path = os.path.join(output_dir, "label_metric_uncertainty.png")
    plot_confidence_intervals(bootstrap_result["modes"], model_slug, chart_path)

    summary: Dict[str, Any] = {
        "model_slug": model_slug,
        "balanced_sample_n": len(case_records),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
        "bootstrap_design": {
            "unit": "case",
            "paired_across_modes": True,
            "stratified_by": "silver_label",
            "preserve_balanced_design": True,
            "confidence_interval": "percentile_95",
        },
        "silver_label_strata": stratum_sizes,
        "metrics": [
            "exact_match",
            "harmful_optimism_at_risk",
            "warning_preservation",
        ],
        "modes": bootstrap_result["modes"],
        "artifacts": {
            "table_csv": csv_path.replace("\\", "/"),
            "plot_png": chart_path.replace("\\", "/"),
            "plot_pdf": chart_path.replace(".png", ".pdf").replace("\\", "/"),
            "plot_svg": chart_path.replace(".png", ".svg").replace("\\", "/"),
            "caption": chart_path.replace(".png", ".caption.txt").replace("\\", "/"),
        },
        "methods_text": (
            "To quantify the uncertainty of the label-based metrics, we computed "
            "non-parametric 95% bootstrap confidence intervals. Because all three "
            "prompting configurations were evaluated on the same cases, resampling "
            "was performed at the case level and paired across configurations. In "
            "addition, resampling was stratified by the silver label to preserve "
            "the balanced evaluation design with equal support for the three "
            "reference categories. For each bootstrap sample, all label-based "
            "metrics were recomputed. Confidence intervals were obtained from the "
            "2.5th and 97.5th percentiles of the resulting bootstrap distribution."
        ),
    }

    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)
    summary["summary_json"] = summary_path.replace("\\", "/")
    return summary


def _format_ci(stats: Dict[str, Any]) -> str:
    return (
        f"{stats['point_estimate']:.1%} "
        f"[{stats['ci_lower']:.1%}, {stats['ci_upper']:.1%}]"
    )


def main() -> None:
    args = parse_args()
    model_slug = discover_model_slug(args.model)
    print(
        "Analyzing label metric uncertainty "
        f"(model={model_slug}, bootstrap_samples={args.bootstrap_samples})"
    )
    summary = run_analysis(
        model_slug=model_slug,
        output_dir=args.output_dir,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )

    print(f"\nResults written to {args.output_dir}/")
    for mode in EVALUATION_MODES:
        metrics = summary["modes"][mode]
        print(
            f"  [{mode}] "
            f"exact_match={_format_ci(metrics['exact_match'])}, "
            f"harmful_optimism_at_risk={_format_ci(metrics['harmful_optimism_at_risk'])}, "
            f"warning_preservation={_format_ci(metrics['warning_preservation'])}"
        )
    print(f"  plot: {summary['artifacts']['plot_png']}")
    print(f"  table: {summary['artifacts']['table_csv']}")
    print(f"  summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()
