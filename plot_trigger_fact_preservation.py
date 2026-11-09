"""
Create a grouped dissertation figure for trigger-fact preservation.

The plot compares five trigger-preservation metrics across the three prompting
configurations:
    - Trigger-fact recall
    - Complete preservation
    - Hard-trigger recall
    - Caution-trigger recall
    - Critical omission rate

It is designed to make the main qualitative pattern easy to see:
direct summary loses hard triggers almost completely, while full evidence and
condensed evidence preserve most trigger facts.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = "cache_experiments/analysis/trigger_fact_preservation"
DEFAULT_INPUT_CANDIDATES = (
    os.path.join(OUTPUT_DIR, "summary.json"),
    os.path.join(OUTPUT_DIR, "trigger_fact_preservation.json"),
)
DEFAULT_OUTPUT_FILENAME = "trigger_fact_preservation_metrics.png"

from dissertation_figure_style import (
    MODE_ORDER, MODE_LABELS, MODE_COLORS, WIDTH, apply_style,
    percentage_axis, export_figure,
)

METRIC_ORDER = (
    ("trigger_fact_recall", "Overall trigger-fact recall"),
    ("complete_trigger_preservation", "Complete preservation"),
    ("hard_trigger_recall", "Hard-trigger recall"),
    ("caution_trigger_recall", "Caution-trigger recall"),
    ("critical_omission_rate", "Critical omission"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot grouped trigger-fact preservation metrics across prompting "
            "configurations."
        )
    )
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "Path to the trigger-fact preservation summary JSON "
            "(default: auto-detect in analysis directory)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Directory for the generated plot.",
    )
    parser.add_argument(
        "--output-name",
        default=DEFAULT_OUTPUT_FILENAME,
        help=f"Output PNG filename (default: {DEFAULT_OUTPUT_FILENAME}).",
    )
    return parser.parse_args()


def load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def resolve_input_path(requested_path: str | None) -> str:
    if requested_path is not None:
        if not os.path.exists(requested_path):
            raise FileNotFoundError(f"Input file not found: {requested_path}")
        return requested_path

    for candidate in DEFAULT_INPUT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "Could not find a trigger-fact preservation summary. Checked: "
        + ", ".join(DEFAULT_INPUT_CANDIDATES)
    )


def validate_summary(summary: Dict[str, Any]) -> None:
    modes = summary.get("modes")
    if not isinstance(modes, dict):
        raise ValueError("Input JSON does not contain a 'modes' object.")

    missing_modes = [mode for mode in MODE_ORDER if mode not in modes]
    if missing_modes:
        raise ValueError(
            "Input JSON is missing required modes: " + ", ".join(missing_modes)
        )

    for mode in MODE_ORDER:
        for metric_key, _ in METRIC_ORDER:
            if metric_key not in modes[mode]:
                raise ValueError(
                    f"Input JSON is missing metric '{metric_key}' for mode '{mode}'."
                )


def build_plot_matrix(summary: Dict[str, Any]) -> np.ndarray:
    """Recompute rates from recorded exact counts, never rounded percentages."""
    columns = []
    for mode in MODE_ORDER:
        record = summary["modes"][mode]
        cases, facts = record["n_cases_with_triggers"], record["n_trigger_facts"]
        counts = record["counts"]
        hard, caution = counts["severity"]["hard"], counts["severity"]["caution"]
        if (cases, facts) != (100, 104) or hard["facts"] + caution["facts"] != facts:
            raise ValueError("Expected 100 triggered cases and 104 classified trigger facts.")
        columns.append([
            counts["preserved_facts"] / facts,
            counts["complete_cases"] / cases,
            hard["preserved"] / hard["facts"],
            caution["preserved"] / caution["facts"],
            counts["critical_omission_cases"] / cases,
        ])
    matrix = np.array(columns).T
    if not np.isfinite(matrix).all() or ((matrix < 0) | (matrix > 1)).any():
        raise ValueError("Trigger rates must be finite proportions.")
    return matrix


def plot_grouped_metrics(summary: Dict[str, Any], output_path: str) -> Dict[str, Any]:
    matrix = build_plot_matrix(summary) * 100
    apply_style()
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH, 5.6),
                             gridspec_kw={"height_ratios": [4, 1.2]})
    fig.subplots_adjust(left=0.31, right=0.90, bottom=0.1, top=0.87, hspace=0.58)
    for ax, rows, title in zip(axes, (range(4), range(4, 5)), (
        "(a) Trigger-fact preservation - higher is better",
        "(b) Critical omission - lower is better",
    )):
        rows = list(rows)
        for column, mode in enumerate(MODE_ORDER):
            bars = ax.barh(np.arange(len(rows)) + (column - 1) * 0.24,
                           matrix[rows, column], height=0.21,
                           color=MODE_COLORS[mode], label=MODE_LABELS[mode])
            for bar in bars:
                ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height()/2,
                        f"{bar.get_width():.0f}%", va="center", fontsize=9, clip_on=False)
        ax.set_yticks(range(len(rows)), [METRIC_ORDER[i][1] for i in rows])
        ax.set_ylim(len(rows) - 0.5, -0.5)
        percentage_axis(ax)
        ax.set_title(title, loc="left", pad=12, x=-0.48)
    axes[1].set_xlabel("Proportion of eligible facts or cases")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center",
               ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.0),
               handlelength=1.4, handletextpad=0.5, columnspacing=1.2)
    denominators = [summary["modes"][m]["counts"]["severity"] for m in MODE_ORDER]
    hard_n, caution_n = denominators[0]["hard"]["facts"], denominators[0]["caution"]["facts"]
    if any((d["hard"]["facts"], d["caution"]["facts"]) != (hard_n, caution_n) for d in denominators):
        raise ValueError("Trigger denominators differ across configurations.")
    artifacts = export_figure(fig, output_path, "Preservation of decision-critical trigger facts.",
        "Figure 8.8. Overall trigger-fact recall is correctly communicated facts / 104 trigger "
        f"facts; hard-trigger and caution-trigger recall use {hard_n} hard and {caution_n} caution "
        "facts, respectively. Complete preservation is cases retaining every required fact / "
        "100 triggered cases. Critical omission is cases retaining none of the required facts / "
        "100 triggered cases, not cases missing at least one fact. Partial preservation means "
        "complete preservation and critical omission are not necessarily complements. Higher "
        "is better for the four preservation/recall metrics; lower is better for omission. "
        "Bars use exact recorded counts; labels round to whole percentages. Hard and caution "
        "triggers originate from diagnostic silver-label rules. Fact preservation is distinct "
        "from categorical warning preservation: facts can be mentioned alongside an insufficiently "
        "cautious label. No confidence intervals are shown.")
    plt.close(fig)
    return {**artifacts, "mode_labels": MODE_LABELS,
            "metric_labels": dict(METRIC_ORDER)}


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input)
    summary = load_json(input_path)
    validate_summary(summary)

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, args.output_name)
    artifacts = plot_grouped_metrics(summary, output_path)

    metadata = {
        "input_json": input_path.replace("\\", "/"),
        "artifacts": artifacts,
    }
    metadata_path = os.path.join(args.output_dir, "trigger_fact_preservation_plot.json")
    save_json(metadata_path, metadata)
    metadata_path_display = metadata_path.replace("\\", "/")

    print(f"Trigger-fact plot written to {artifacts['plot_png']}")
    print(f"Plot metadata written to {metadata_path_display}")


if __name__ == "__main__":
    main()
