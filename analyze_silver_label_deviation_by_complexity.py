"""
Analyze silver-label vs. assessment alignment by recommendation complexity
for each evaluation setting.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Tuple

from alignment_analysis import (
    CACHE_COMPLEXITY,
    CACHE_SILVER_LABELS,
    EVALUATION_MODES,
    complexity_group,
    count_alignment_buckets,
    discover_model_slug,
    load_balanced_diff_keys,
    load_balanced_silver_labels,
    load_complexity_by_diff,
    load_complexity_quartile_config,
    load_mode_pairs,
    normalize_alignment_counts,
    plot_alignment_by_complexity_line,
    save_json,
)
from label_metrics import evaluate_pairs

OUTPUT_DIR = "cache_experiments/analysis/silver_label_deviation_by_complexity"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze silver-label alignment by recommendation complexity groups "
            "for each evaluation setting."
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
        help="Directory for charts and summary JSON.",
    )
    return parser.parse_args()


def group_pairs_by_complexity(
    pairs: List[Dict[str, Any]],
    complexities: Dict[str, int],
    complexity_group_keys: Tuple[str, ...],
    quartile_breakpoints: Tuple[float, float, float],
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {
        group: [] for group in complexity_group_keys
    }
    for pair in pairs:
        complexity = complexities.get(pair["diff_key"])
        if complexity is None:
            continue
        grouped[complexity_group(complexity, quartile_breakpoints)].append(pair)
    return grouped


def analyze_mode_by_complexity(
    mode: str,
    model_slug: str,
    silver_labels: Dict[str, Any],
    complexities: Dict[str, int],
    allowed_diff_keys: set[str],
    complexity_group_keys: Tuple[str, ...],
    quartile_breakpoints: Tuple[float, float, float],
) -> Dict[str, Any]:
    pairs = load_mode_pairs(mode, model_slug, silver_labels, allowed_diff_keys)
    grouped_pairs = group_pairs_by_complexity(
        pairs, complexities, complexity_group_keys, quartile_breakpoints
    )
    mode_label_metrics = evaluate_pairs(pairs)

    group_stats: Dict[str, Any] = {}

    for group in complexity_group_keys:
        group_pairs = grouped_pairs[group]
        alignment_counts = count_alignment_buckets(group_pairs)
        alignment_percentages = normalize_alignment_counts(
            {group: alignment_counts},
            [group],
        )[group]
        label_metrics = evaluate_pairs(group_pairs)
        group_stats[group] = {
            "n": len(group_pairs),
            "alignment_counts": alignment_counts,
            "alignment_percentages": {
                category: round(alignment_percentages[category], 1)
                for category in alignment_percentages
            },
            **label_metrics,
        }

    return {
        "groups": group_stats,
        "label_metrics": mode_label_metrics,
    }


def run_analysis(model_slug: str, output_dir: str) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    silver_labels = load_balanced_silver_labels()
    if not silver_labels:
        raise FileNotFoundError(f"No balanced silver labels found in {CACHE_SILVER_LABELS}")

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

    os.makedirs(output_dir, exist_ok=True)

    summary: Dict[str, Any] = {
        "model_slug": model_slug,
        "balanced_sample_n": len(allowed_diff_keys),
        "complexity_groups": list(complexity_group_keys),
        "complexity_group_labels": complexity_group_labels,
        "complexity_quartiles": {
            "q1": quartile_breakpoints[0],
            "q2": quartile_breakpoints[1],
            "q3": quartile_breakpoints[2],
        },
        "modes": {},
        "charts": {},
    }

    for mode in EVALUATION_MODES:
        mode_result = analyze_mode_by_complexity(
            mode,
            model_slug,
            silver_labels,
            complexities,
            allowed_diff_keys,
            complexity_group_keys,
            quartile_breakpoints,
        )
        summary["modes"][mode] = {
            "groups": mode_result["groups"],
            "label_metrics": mode_result["label_metrics"],
        }

    alignment_chart_path = os.path.join(output_dir, "alignment_by_complexity.png")
    plot_alignment_by_complexity_line(
        summary["modes"],
        model_slug,
        alignment_chart_path,
        complexity_group_keys,
        complexity_group_labels,
    )
    summary["charts"]["alignment_by_complexity"] = alignment_chart_path.replace("\\", "/")

    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)
    summary["summary_json"] = summary_path.replace("\\", "/")
    return summary


def main() -> None:
    args = parse_args()
    model_slug = discover_model_slug(args.model)
    print(f"Analyzing silver label deviation by complexity (model={model_slug})")
    summary = run_analysis(model_slug, args.output_dir)

    print(f"\nResults written to {args.output_dir}/")
    for mode in EVALUATION_MODES:
        print(f"  [{mode}]")
        mode_metrics = summary["modes"][mode]["label_metrics"]
        overall_macro = (
            f"{mode_metrics['macro_recall']:.1%}"
            if mode_metrics["macro_recall"] is not None
            else "n/a"
        )
        print(
            f"    overall: n={mode_metrics['n_valid']}, macro_recall={overall_macro}"
        )
        for group in summary["complexity_groups"]:
            stats = summary["modes"][mode]["groups"][group]
            counts = stats["alignment_counts"]
            percentages = stats["alignment_percentages"]
            macro_recall_str = (
                f"{stats['macro_recall']:.1%}"
                if stats["macro_recall"] is not None
                else "n/a"
            )
            optimism_str = (
                f"{stats['harmful_optimism_at_risk']:.1%}"
                if stats["harmful_optimism_at_risk"] is not None
                else "n/a"
            )
            print(
                f"    [{group}] n={stats['n']}, "
                f"macro_recall={macro_recall_str}, "
                f"harmful_optimism_at_risk={optimism_str}, "
                f"aligned={counts['aligned']} ({percentages['aligned']:.1f}%), "
                f"unaligned={counts['unaligned']} ({percentages['unaligned']:.1f}%), "
                f"completely unaligned={counts['completely_unaligned']} "
                f"({percentages['completely_unaligned']:.1f}%)"
            )
    print(f"  chart: {summary['charts']['alignment_by_complexity']}")
    print(f"  summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()
