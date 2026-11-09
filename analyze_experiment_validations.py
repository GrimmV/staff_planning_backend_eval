"""
Visualize LLM-as-a-judge validation results (clarity and coherence) and
assessment-generation token usage across evaluation settings.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from alignment_analysis import (
    CACHE_COMPLEXITY,
    EVALUATION_MODES,
    MODE_COLORS,
    MODE_DISPLAY_LABELS,
    complexity_group,
    discover_model_slug,
    evaluation_dir,
    load_balanced_diff_keys,
    load_complexity_by_diff,
    load_complexity_quartile_config,
    load_json,
    save_json,
)

CACHE_VALIDATIONS = "cache_experiments/cache_validations"
OUTPUT_DIR = "cache_experiments/analysis/output_validation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze clarity/coherence validation scores and assessment token usage "
            "across evaluation settings."
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
        "--validation-dir",
        default=CACHE_VALIDATIONS,
        help="Directory with per-case validation results.",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory for charts and summary JSON.",
    )
    return parser.parse_args()


def validation_path(validation_dir: str, mode: str, diff_key: str) -> str:
    return os.path.join(validation_dir, mode, diff_key.replace("/", os.sep))


def evaluation_path(model_slug: str, mode: str, diff_key: str) -> str:
    return os.path.join(evaluation_dir(mode, model_slug), diff_key.replace("/", os.sep))


def case_judgment_scores(validation: Dict[str, Any]) -> Tuple[float, float]:
    clarity_scores = [step["clarity"]["score"] for step in validation["steps"].values()]
    coherence_scores = [step["coherence"]["score"] for step in validation["steps"].values()]
    return (
        sum(clarity_scores) / len(clarity_scores),
        sum(coherence_scores) / len(coherence_scores),
    )


def sum_assessment_tokens(assessment: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    llm_calls = assessment.get("llm_calls")
    if not isinstance(llm_calls, dict) or not llm_calls:
        return None, None

    input_total = 0
    output_total = 0
    for call in llm_calls.values():
        input_tokens = call.get("input_tokens")
        output_tokens = call.get("output_tokens")
        if input_tokens is None or output_tokens is None:
            return None, None
        input_total += int(input_tokens)
        output_total += int(output_tokens)
    return input_total, output_total


def build_records(
    model_slug: str,
    validation_dir: str,
    allowed_diff_keys: set[str],
    complexities: Dict[str, int],
    quartile_breakpoints: Tuple[float, float, float],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    for mode in EVALUATION_MODES:
        for diff_key in sorted(allowed_diff_keys):
            val_path = validation_path(validation_dir, mode, diff_key)
            eval_path = evaluation_path(model_slug, mode, diff_key)
            if not os.path.exists(val_path):
                continue
            if not os.path.exists(eval_path):
                continue

            validation = load_json(val_path)
            evaluation = load_json(eval_path)
            clarity, coherence = case_judgment_scores(validation)
            input_tokens, output_tokens = sum_assessment_tokens(evaluation["assessment"])

            complexity = complexities.get(diff_key)
            record: Dict[str, Any] = {
                "mode": mode,
                "diff_key": diff_key,
                "clarity": clarity,
                "coherence": coherence,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "complexity": complexity,
            }
            if complexity is not None:
                record["complexity_group"] = complexity_group(
                    complexity, quartile_breakpoints
                )
            records.append(record)

    return records


def records_to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(records)


def _ordered_modes(df: pd.DataFrame) -> List[str]:
    return [mode for mode in EVALUATION_MODES if mode in set(df["mode"])]


def plot_scores_by_mode(
    df: pd.DataFrame,
    model_slug: str,
    output_path: str,
) -> None:
    modes = _ordered_modes(df)
    mode_labels = [MODE_DISPLAY_LABELS[mode] for mode in modes]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), sharey=True)

    for ax, metric, title in zip(
        axes,
        ("clarity", "coherence"),
        ("Klarheit", "Kohärenz"),
    ):
        data = [df.loc[df["mode"] == mode, metric].tolist() for mode in modes]
        box = ax.boxplot(
            data,
            tick_labels=mode_labels,
            patch_artist=True,
            widths=0.55,
            medianprops={"color": "black", "linewidth": 1.2},
        )
        for patch, mode in zip(box["boxes"], modes):
            patch.set_facecolor(MODE_COLORS[mode])
            patch.set_alpha(0.65)
        ax.set_ylim(0, 10.5)
        ax.set_ylabel("Score (0–10)")
        ax.set_xlabel("Setting")
        ax.set_title(title)
        ax.grid(axis="y", linestyle="--", alpha=0.35)

    fig.suptitle(
        f"LLM-Validierung – Klarheit und Kohärenz nach Setting\nModell: {model_slug}",
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_scores_by_complexity(
    df: pd.DataFrame,
    model_slug: str,
    complexity_group_keys: Tuple[str, ...],
    complexity_group_labels: Dict[str, str],
    output_path: str,
) -> None:
    plot_df = df.dropna(subset=["complexity_group"]).copy()
    if plot_df.empty:
        raise ValueError("No validation records with complexity scores found.")

    group_order = [group for group in complexity_group_keys if group in plot_df["complexity_group"].unique()]
    modes = _ordered_modes(plot_df)
    x_labels = [
        f"{complexity_group_labels.get(group, group)}\n"
        f"(n={len(plot_df[plot_df['complexity_group'] == group]) // len(modes)})"
        for group in group_order
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    width = 0.22
    offsets = np.linspace(-(len(modes) - 1) / 2, (len(modes) - 1) / 2, len(modes)) * width

    for ax, metric, title in zip(
        axes,
        ("clarity", "coherence"),
        ("Klarheit", "Kohärenz"),
    ):
        x = np.arange(len(group_order))
        for offset, mode in zip(offsets, modes):
            values = [
                plot_df.loc[
                    (plot_df["complexity_group"] == group) & (plot_df["mode"] == mode),
                    metric,
                ].tolist()
                for group in group_order
            ]
            box = ax.boxplot(
                values,
                positions=x + offset,
                widths=width * 0.9,
                patch_artist=True,
                medianprops={"color": "black", "linewidth": 1.1},
                manage_ticks=False,
            )
            for patch in box["boxes"]:
                patch.set_facecolor(MODE_COLORS[mode])
                patch.set_alpha(0.65)

        ax.set_xticks(x)
        ax.set_xticklabels(x_labels)
        ax.set_ylim(0, 10.5)
        ax.set_ylabel("Score (0–10)")
        ax.set_xlabel("Komplexitätsquartil")
        ax.set_title(title)
        ax.grid(axis="y", linestyle="--", alpha=0.35)

    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            markerfacecolor=MODE_COLORS[mode],
            markersize=10,
            alpha=0.65,
            label=MODE_DISPLAY_LABELS[mode],
        )
        for mode in modes
    ]
    fig.legend(handles=handles, loc="upper center", ncol=len(modes), bbox_to_anchor=(0.5, 1.08))
    fig.suptitle(
        f"LLM-Validierung – Klarheit und Kohärenz nach Komplexität\nModell: {model_slug}",
        y=1.12,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_tokens_by_mode(
    df: pd.DataFrame,
    model_slug: str,
    output_path: str,
) -> None:
    token_df = df.dropna(subset=["input_tokens", "output_tokens"]).copy()
    if token_df.empty:
        raise ValueError("No evaluation records with llm_calls token usage found.")

    modes = _ordered_modes(token_df)
    mode_labels = [MODE_DISPLAY_LABELS[mode] for mode in modes]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))

    for ax, metric, title in zip(
        axes,
        ("input_tokens", "output_tokens"),
        ("Input-Tokens (summiert)", "Output-Tokens (summiert)"),
    ):
        data = [token_df.loc[token_df["mode"] == mode, metric].tolist() for mode in modes]
        box = ax.boxplot(
            data,
            tick_labels=mode_labels,
            patch_artist=True,
            widths=0.55,
            medianprops={"color": "black", "linewidth": 1.2},
        )
        for patch, mode in zip(box["boxes"], modes):
            patch.set_facecolor(MODE_COLORS[mode])
            patch.set_alpha(0.65)
        ax.set_ylabel("Tokens pro Assessment")
        ax.set_xlabel("Setting")
        ax.set_title(title)
        ax.grid(axis="y", linestyle="--", alpha=0.35)

    fig.suptitle(
        f"Tokenverbrauch der Assessment-Generierung nach Setting\n"
        f"Modell: {model_slug} (inkl. Tabellen- und Statistik-Zusammenfassungen)",
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def summarize_records(
    records: List[Dict[str, Any]],
    complexity_group_keys: Tuple[str, ...],
) -> Dict[str, Any]:
    def mean_metric(items: List[Dict[str, Any]], key: str) -> Optional[float]:
        values = [item[key] for item in items if item.get(key) is not None]
        return round(float(np.mean(values)), 2) if values else None

    summary: Dict[str, Any] = {"modes": {}, "by_complexity": {}}
    for mode in EVALUATION_MODES:
        mode_records = [record for record in records if record["mode"] == mode]
        summary["modes"][mode] = {
            "n": len(mode_records),
            "mean_clarity": mean_metric(mode_records, "clarity"),
            "mean_coherence": mean_metric(mode_records, "coherence"),
            "mean_input_tokens": mean_metric(mode_records, "input_tokens"),
            "mean_output_tokens": mean_metric(mode_records, "output_tokens"),
        }

    for group in complexity_group_keys:
        group_records = [
            record for record in records if record.get("complexity_group") == group
        ]
        summary["by_complexity"][group] = {
            "n": len(group_records),
            "mean_clarity": mean_metric(group_records, "clarity"),
            "mean_coherence": mean_metric(group_records, "coherence"),
        }

    return summary


def run_analysis(
    model_slug: str,
    validation_dir: str,
    output_dir: str,
) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    complexities = {
        key: value
        for key, value in load_complexity_by_diff().items()
        if key in allowed_diff_keys
    }
    if not complexities:
        raise FileNotFoundError(f"No complexity scores found in {CACHE_COMPLEXITY}")

    complexity_group_keys, complexity_group_labels, quartile_breakpoints = (
        load_complexity_quartile_config()
    )

    records = build_records(
        model_slug,
        validation_dir,
        allowed_diff_keys,
        complexities,
        quartile_breakpoints,
    )
    if not records:
        raise FileNotFoundError(
            f"No validation results found in {validation_dir} for model {model_slug}."
        )

    df = records_to_dataframe(records)
    os.makedirs(output_dir, exist_ok=True)

    scores_by_mode_path = os.path.join(output_dir, "clarity_coherence_by_mode.png")
    plot_scores_by_mode(df, model_slug, scores_by_mode_path)

    scores_by_complexity_path = os.path.join(
        output_dir, "clarity_coherence_by_complexity.png"
    )
    plot_scores_by_complexity(
        df,
        model_slug,
        complexity_group_keys,
        complexity_group_labels,
        scores_by_complexity_path,
    )

    tokens_by_mode_path = os.path.join(output_dir, "assessment_tokens_by_mode.png")
    plot_tokens_by_mode(df, model_slug, tokens_by_mode_path)

    mode_summary = summarize_records(records, complexity_group_keys)
    summary: Dict[str, Any] = {
        "model_slug": model_slug,
        "balanced_sample_n": len(allowed_diff_keys),
        "validation_dir": validation_dir.replace("\\", "/"),
        "complexity_groups": list(complexity_group_keys),
        "complexity_group_labels": complexity_group_labels,
        "n_records": len(records),
        "modes": mode_summary["modes"],
        "by_complexity": mode_summary["by_complexity"],
        "charts": {
            "clarity_coherence_by_mode": scores_by_mode_path.replace("\\", "/"),
            "clarity_coherence_by_complexity": scores_by_complexity_path.replace("\\", "/"),
            "assessment_tokens_by_mode": tokens_by_mode_path.replace("\\", "/"),
        },
    }

    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)
    summary["summary_json"] = summary_path.replace("\\", "/")
    return summary


def main() -> None:
    args = parse_args()
    model_slug = discover_model_slug(args.model)
    print(f"Analyzing output validation results for model={model_slug}")
    summary = run_analysis(model_slug, args.validation_dir, args.output_dir)

    print(f"\nResults written to {args.output_dir}/")
    for mode in EVALUATION_MODES:
        stats = summary["modes"].get(mode, {})
        if not stats:
            continue
        print(
            f"  [{mode}] n={stats['n']}, "
            f"clarity={stats['mean_clarity']}, coherence={stats['mean_coherence']}, "
            f"input_tokens={stats['mean_input_tokens']}, "
            f"output_tokens={stats['mean_output_tokens']}"
        )
    for chart_key, chart_path in summary["charts"].items():
        print(f"  chart ({chart_key}): {chart_path}")
    print(f"  summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()
