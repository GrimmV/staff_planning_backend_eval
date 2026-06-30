"""
Compare silver labels with LLM assessment scores across evaluation settings.

Produces per-mode confusion-matrix heatmaps and a compact metrics dot plot across settings.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt

from alignment_analysis import (
    CACHE_SILVER_LABELS,
    EVALUATION_MODES,
    SCORE_ORDINAL,
    count_alignment_buckets,
    discover_model_slug,
    load_balanced_diff_keys,
    load_balanced_silver_labels,
    load_mode_pairs,
    plot_mode_metrics_dotplot,
    save_json,
)
from label_metrics import confusion_matrix_dataframe, evaluate_pairs

OUTPUT_DIR = "cache_experiments/analysis/silver_label_deviation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze deviation between silver labels and LLM assessment scores."
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


def compute_mode_stats(pairs: list[Dict[str, Any]]) -> Dict[str, Any]:
    label_metrics = evaluate_pairs(pairs)
    alignment_counts = count_alignment_buckets(pairs)
    return {
        "n": label_metrics["n_valid"],
        "alignment_counts": alignment_counts,
        **label_metrics,
    }


def _format_rate(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def plot_mode_heatmap(
    matrix: pd.DataFrame,
    mode: str,
    stats: Dict[str, Any],
    model_slug: str,
    output_path: str,
) -> None:
    fig, ax = plt.subplots(figsize=(7, 5.5))
    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="YlOrRd",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Anzahl Diffs"},
        ax=ax,
    )
    ax.set_xlabel("LLM Assessment Score")
    ax.set_ylabel("Silver Label")
    ax.set_title(
        f"{mode} – Silver Label vs. Assessment\n"
        f"Modell: {model_slug} | n={stats['n']} | "
        f"Übereinstimmung={_format_rate(stats['exact_match_rate'])} | "
        f"Macro-Recall={_format_rate(stats['macro_recall'])} | "
        f"Ø Abweichung={stats['mean_ordinal_deviation']:.2f}"
        if stats["mean_ordinal_deviation"] is not None
        else (
            f"{mode} – Silver Label vs. Assessment\n"
            f"Modell: {model_slug} | n={stats['n']}"
        )
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def run_analysis(model_slug: str, output_dir: str) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    silver_labels = load_balanced_silver_labels()
    if not silver_labels:
        raise FileNotFoundError(f"No balanced silver labels found in {CACHE_SILVER_LABELS}")

    os.makedirs(output_dir, exist_ok=True)

    summary: Dict[str, Any] = {
        "model_slug": model_slug,
        "balanced_sample_n": len(allowed_diff_keys),
        "score_labels": list(SCORE_ORDINAL.keys()),
        "score_ordinal": SCORE_ORDINAL,
        "modes": {},
        "charts": {},
    }

    alignment_by_mode: Dict[str, Dict[str, int]] = {}
    mode_stats: Dict[str, Dict[str, Any]] = {}

    for mode in EVALUATION_MODES:
        pairs = load_mode_pairs(mode, model_slug, silver_labels, allowed_diff_keys)
        stats = compute_mode_stats(pairs)
        matrix = confusion_matrix_dataframe(stats)
        alignment_by_mode[mode] = stats["alignment_counts"]
        mode_stats[mode] = stats

        heatmap_path = os.path.join(output_dir, f"heatmap_{mode}.png")
        plot_mode_heatmap(matrix, mode, stats, model_slug, heatmap_path)

        summary["modes"][mode] = {
            **stats,
            "confusion_matrix": matrix.to_dict(),
            "heatmap": heatmap_path.replace("\\", "/"),
        }
        summary["charts"][f"heatmap_{mode}"] = heatmap_path.replace("\\", "/")

    metrics_chart_path = os.path.join(output_dir, "metrics_by_mode.png")
    plot_mode_metrics_dotplot(mode_stats, model_slug, metrics_chart_path)
    summary["charts"]["metrics_by_mode"] = metrics_chart_path.replace("\\", "/")
    summary["alignment_by_setting"] = alignment_by_mode

    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)
    summary["summary_json"] = summary_path.replace("\\", "/")
    return summary


def main() -> None:
    args = parse_args()
    model_slug = discover_model_slug(args.model)
    print(f"Analyzing silver label deviation for model={model_slug}")
    summary = run_analysis(model_slug, args.output_dir)

    print(f"\nResults written to {args.output_dir}/")
    for mode in EVALUATION_MODES:
        stats = summary["modes"][mode]
        counts = stats["alignment_counts"]
        signed_deviation = (
            f"{stats['signed_ordinal_deviation']:.2f}"
            if stats["signed_ordinal_deviation"] is not None
            else "n/a"
        )
        print(
            f"  [{mode}] n={stats['n']}, "
            f"macro_recall={_format_rate(stats['macro_recall'])}, "
            f"harmful_optimism_at_risk={_format_rate(stats['harmful_optimism_at_risk'])}, "
            f"severe_harmful_optimism={_format_rate(stats['severe_harmful_optimism'])}, "
            f"signed_deviation={signed_deviation}, "
            f"aligned={counts['aligned']}, "
            f"unaligned={counts['unaligned']}, "
            f"completely unaligned={counts['completely_unaligned']}"
        )
    print(f"  summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()
