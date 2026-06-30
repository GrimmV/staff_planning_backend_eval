"""Shared helpers for silver-label vs. assessment alignment analysis."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

CACHE_ROOT = "cache_experiments"
CACHE_DIFFS = os.path.join(CACHE_ROOT, "cache_diffs")
CACHE_SILVER_LABELS = os.path.join(CACHE_ROOT, "cache_silver_labels")
CACHE_COMPLEXITY = os.path.join(CACHE_ROOT, "cache_complexity")
CACHE_EVALUATIONS = os.path.join(CACHE_ROOT, "cache_evaluations")
BALANCED_SAMPLE_PATH = os.path.join(CACHE_ROOT, "cache_balanced_sample.json")

BALANCE_TARGET_LABELS: Tuple[ScoreLabel, ...] = (
    "ablehnen",
    "eher ablehnen",
    "eher akzeptieren",
)

EVALUATION_MODES: Tuple[str, ...] = ("full", "simple", "simple_direct")

ScoreLabel = Literal["ablehnen", "eher ablehnen", "eher akzeptieren"]
SCORE_LABELS: Tuple[ScoreLabel, ...] = ("ablehnen", "eher ablehnen", "eher akzeptieren")
SCORE_ORDINAL: Dict[ScoreLabel, int] = {
    "eher akzeptieren": 0,
    "eher ablehnen": 1,
    "ablehnen": 2,
}

AlignmentCategory = Literal["aligned", "unaligned", "completely_unaligned"]
ALIGNMENT_CATEGORIES: Tuple[AlignmentCategory, ...] = (
    "aligned",
    "unaligned",
    "completely_unaligned",
)
ALIGNMENT_LABELS: Dict[AlignmentCategory, str] = {
    "aligned": "Übereinstimmend",
    "unaligned": "Abweichend",
    "completely_unaligned": "Völlig abweichend",
}
ALIGNMENT_COLORS: Dict[AlignmentCategory, str] = {
    "aligned": "#2ca02c",
    "unaligned": "#ff7f0e",
    "completely_unaligned": "#d62728",
}

MODE_COLORS: Dict[str, str] = {
    "full": "#1f77b4",
    "simple": "#ff7f0e",
    "simple_direct": "#2ca02c",
}

MODE_DISPLAY_LABELS: Dict[str, str] = {
    "full": "full",
    "simple": "simple",
    "simple_direct": "simple_direct",
}

METRIC_PLOT_SPECS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Exact match", ("exact_match_rate",)),
    ("Macro recall", ("macro_recall",)),
    ("Recall ablehnen", ("class_recall", "ablehnen")),
    ("Harmful optimism (at-risk)", ("harmful_optimism_at_risk",)),
    ("Severe harmful optimism", ("severe_harmful_optimism",)),
    ("Over-caution (at-risk)", ("over_caution_at_risk",)),
)

COMPLEXITY_QUARTILE_KEYS: Tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4")


def sanitize_model_name(model_name: str) -> str:
    return model_name.replace(".", "_").replace("/", "_")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def diff_key(date_folder: str, filename: str) -> str:
    return f"{date_folder}/{filename}"


def alignment_category(ordinal_deviation: int) -> AlignmentCategory:
    if ordinal_deviation == 0:
        return "aligned"
    if ordinal_deviation == 1:
        return "unaligned"
    return "completely_unaligned"


def empty_alignment_counts() -> Dict[AlignmentCategory, int]:
    return {category: 0 for category in ALIGNMENT_CATEGORIES}


def count_alignment_buckets(pairs: List[Dict[str, Any]]) -> Dict[AlignmentCategory, int]:
    counts = empty_alignment_counts()
    for pair in pairs:
        counts[alignment_category(pair["ordinal_deviation"])] += 1
    return counts


def triggered_rules_key(triggered_rules: List[str]) -> str:
    if not triggered_rules:
        return "(none)"
    return "|".join(sorted(triggered_rules))


def compute_complexity_quartile_breakpoints(
    complexities: Dict[str, int],
) -> Tuple[float, float, float]:
    if not complexities:
        raise ValueError("Cannot compute complexity quartiles from an empty set.")
    values = np.array(list(complexities.values()), dtype=float)
    q1, q2, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    return float(q1), float(q2), float(q3)


def complexity_quartile_group(
    complexity: int,
    breakpoints: Tuple[float, float, float],
) -> str:
    q1, q2, q3 = breakpoints
    if complexity <= q1:
        return "Q1"
    if complexity <= q2:
        return "Q2"
    if complexity <= q3:
        return "Q3"
    return "Q4"


def load_balanced_sample(path: str = BALANCED_SAMPLE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Balanced sample manifest not found at {path}. "
            "Run balance_dataset.py first."
        )
    return load_json(path)


def load_balanced_diff_keys(path: str = BALANCED_SAMPLE_PATH) -> set[str]:
    manifest = load_balanced_sample(path)
    return set(manifest["diff_keys"])


def load_complexity_quartile_config(
    path: str = BALANCED_SAMPLE_PATH,
) -> Tuple[Tuple[str, ...], Dict[str, str], Tuple[float, float, float]]:
    manifest = load_balanced_sample(path)
    quartiles = manifest["complexity_quartiles"]
    keys = tuple(quartiles["bin_keys"])
    labels = quartiles["bin_labels"]
    breakpoints = (
        float(quartiles["q1"]),
        float(quartiles["q2"]),
        float(quartiles["q3"]),
    )
    return keys, labels, breakpoints


def filter_dict_by_diff_keys(
    mapping: Dict[str, Any],
    allowed_diff_keys: set[str],
) -> Dict[str, Any]:
    return {key: value for key, value in mapping.items() if key in allowed_diff_keys}


def load_silver_label_records() -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(CACHE_SILVER_LABELS):
        return records

    for date_folder in sorted(os.listdir(CACHE_SILVER_LABELS)):
        date_path = os.path.join(CACHE_SILVER_LABELS, date_folder)
        if not os.path.isdir(date_path):
            continue
        for filename in sorted(os.listdir(date_path)):
            if not filename.endswith(".json"):
                continue
            records[diff_key(date_folder, filename)] = load_json(
                os.path.join(date_path, filename)
            )
    return records


def load_balanced_silver_labels(
    path: str = BALANCED_SAMPLE_PATH,
) -> Dict[str, ScoreLabel]:
    allowed = load_balanced_diff_keys(path)
    return filter_dict_by_diff_keys(load_silver_labels(), allowed)


def load_balanced_silver_label_records(
    path: str = BALANCED_SAMPLE_PATH,
) -> Dict[str, Dict[str, Any]]:
    allowed = load_balanced_diff_keys(path)
    return filter_dict_by_diff_keys(load_silver_label_records(), allowed)


def complexity_group(
    complexity: int,
    breakpoints: Optional[Tuple[float, float, float]] = None,
) -> str:
    if breakpoints is None:
        _, _, breakpoints = load_complexity_quartile_config()
    return complexity_quartile_group(complexity, breakpoints)


def load_silver_labels() -> Dict[str, ScoreLabel]:
    labels: Dict[str, ScoreLabel] = {}
    if not os.path.isdir(CACHE_SILVER_LABELS):
        return labels

    for date_folder in sorted(os.listdir(CACHE_SILVER_LABELS)):
        date_path = os.path.join(CACHE_SILVER_LABELS, date_folder)
        if not os.path.isdir(date_path):
            continue
        for filename in sorted(os.listdir(date_path)):
            if not filename.endswith(".json"):
                continue
            payload = load_json(os.path.join(date_path, filename))
            labels[diff_key(date_folder, filename)] = payload["silver_label"]
    return labels


def load_complexity_by_diff() -> Dict[str, int]:
    complexities: Dict[str, int] = {}
    if not os.path.isdir(CACHE_COMPLEXITY):
        return complexities

    for date_folder in sorted(os.listdir(CACHE_COMPLEXITY)):
        date_path = os.path.join(CACHE_COMPLEXITY, date_folder)
        if not os.path.isdir(date_path):
            continue
        for filename in sorted(os.listdir(date_path)):
            if not filename.endswith(".json"):
                continue
            payload = load_json(os.path.join(date_path, filename))
            complexities[diff_key(date_folder, filename)] = payload["complexity"]
    return complexities


def discover_model_slug(
    requested_model: Optional[str],
    required_modes: Optional[set[str]] = None,
) -> str:
    if not os.path.isdir(CACHE_EVALUATIONS):
        raise FileNotFoundError(f"Missing evaluations directory: {CACHE_EVALUATIONS}")

    required = required_modes or set(EVALUATION_MODES)
    pattern = re.compile(r"^(full|simple|simple_direct)__(.+)$")
    slugs: Dict[str, set[str]] = {}
    for entry in os.listdir(CACHE_EVALUATIONS):
        match = pattern.match(entry)
        if not match or not os.path.isdir(os.path.join(CACHE_EVALUATIONS, entry)):
            continue
        mode, slug = match.groups()
        slugs.setdefault(slug, set()).add(mode)

    complete = [slug for slug, modes in slugs.items() if required.issubset(modes)]
    if not complete:
        raise FileNotFoundError(
            f"No evaluation cache folder contains all required modes ({', '.join(sorted(required))})."
        )

    if requested_model is None:
        return sorted(complete)[0]

    requested_slug = sanitize_model_name(requested_model)
    if requested_slug in complete:
        return requested_slug
    if requested_model in complete:
        return requested_model

    raise ValueError(
        f"Model '{requested_model}' not found. Available model slugs: "
        f"{', '.join(sorted(complete))}"
    )


def evaluation_dir(mode: str, model_slug: str) -> str:
    return os.path.join(CACHE_EVALUATIONS, f"{mode}__{model_slug}")


def load_mode_pairs(
    mode: str,
    model_slug: str,
    silver_labels: Dict[str, ScoreLabel],
    allowed_diff_keys: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    mode_root = evaluation_dir(mode, model_slug)
    if not os.path.isdir(mode_root):
        raise FileNotFoundError(f"Missing evaluation mode directory: {mode_root}")

    pairs: List[Dict[str, Any]] = []
    for key, silver_label in silver_labels.items():
        if allowed_diff_keys is not None and key not in allowed_diff_keys:
            continue
        eval_path = os.path.join(mode_root, key.replace("/", os.sep))
        if not os.path.exists(eval_path):
            continue
        payload = load_json(eval_path)
        assessment_score = payload["assessment"]["score"]
        ordinal_deviation = abs(
            SCORE_ORDINAL[silver_label] - SCORE_ORDINAL[assessment_score]
        )
        pairs.append(
            {
                "diff_key": key,
                "silver_label": silver_label,
                "assessment_score": assessment_score,
                "ordinal_deviation": ordinal_deviation,
                "alignment": alignment_category(ordinal_deviation),
                "exact_match": silver_label == assessment_score,
            }
        )
    return pairs


def normalize_alignment_counts(
    group_counts: Dict[str, Dict[AlignmentCategory, int]],
    x_labels: List[str],
) -> Dict[str, Dict[AlignmentCategory, float]]:
    normalized: Dict[str, Dict[AlignmentCategory, float]] = {}
    for label in x_labels:
        counts = group_counts[label]
        total = sum(counts[category] for category in ALIGNMENT_CATEGORIES)
        if total == 0:
            normalized[label] = {category: 0.0 for category in ALIGNMENT_CATEGORIES}
            continue
        normalized[label] = {
            category: counts[category] / total * 100 for category in ALIGNMENT_CATEGORIES
        }
    return normalized


def plot_alignment_bar_chart(
    group_counts: Dict[str, Dict[AlignmentCategory, int]],
    x_labels: List[str],
    title: str,
    x_axis_label: str,
    output_path: str,
    display_labels: Optional[Dict[str, str]] = None,
    normalize: bool = False,
) -> None:
    x = np.arange(len(x_labels))
    width = 0.22
    offsets = np.array([-width, 0.0, width])
    tick_labels = [
        display_labels.get(label, label) if display_labels else label for label in x_labels
    ]
    values_by_category: Dict[AlignmentCategory, List[float]] = {
        category: [] for category in ALIGNMENT_CATEGORIES
    }

    if normalize:
        normalized = normalize_alignment_counts(group_counts, x_labels)
        for label in x_labels:
            for category in ALIGNMENT_CATEGORIES:
                values_by_category[category].append(normalized[label][category])
        y_label = "Anteil (%)"
        value_format = "{:.0f}%"
    else:
        for label in x_labels:
            for category in ALIGNMENT_CATEGORIES:
                values_by_category[category].append(float(group_counts[label][category]))
        y_label = "Anzahl Empfehlungen"
        value_format = "{:.0f}"

    fig, ax = plt.subplots(figsize=(max(8, len(x_labels) * 2.2), 5.5))

    for offset, category in zip(offsets, ALIGNMENT_CATEGORIES):
        values = values_by_category[category]
        bars = ax.bar(
            x + offset,
            values,
            width,
            label=ALIGNMENT_LABELS[category],
            color=ALIGNMENT_COLORS[category],
        )
        for bar, value in zip(bars, values):
            if value > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    value_format.format(value),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(tick_labels)
    ax.set_xlabel(x_axis_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.legend()
    ax.set_ylim(bottom=0, top=100 if normalize else None)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _nested_metric_value(stats: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
    value: Any = stats
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    if value is None:
        return None
    return float(value)


def plot_mode_metrics_dotplot(
    mode_stats: Dict[str, Dict[str, Any]],
    model_slug: str,
    output_path: str,
    modes: Tuple[str, ...] = EVALUATION_MODES,
) -> None:
    metric_labels = [label for label, _ in METRIC_PLOT_SPECS]
    y_positions = np.arange(len(metric_labels))

    fig, ax = plt.subplots(figsize=(8.5, 0.55 * len(metric_labels) + 1.8))

    for mode in modes:
        stats = mode_stats[mode]
        xs: List[float] = []
        ys: List[float] = []
        for row_idx, (_, keys) in enumerate(METRIC_PLOT_SPECS):
            value = _nested_metric_value(stats, keys)
            if value is None:
                continue
            xs.append(value * 100)
            ys.append(row_idx)

        ax.scatter(
            xs,
            ys,
            s=70,
            color=MODE_COLORS[mode],
            label=MODE_DISPLAY_LABELS[mode],
            zorder=3,
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(metric_labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Rate (%)")
    ax.set_title(
        f"Silver Label vs. Assessment – Metriken nach Setting\nModell: {model_slug}"
    )
    ax.grid(axis="x", linestyle="--", alpha=0.35, zorder=0)
    ax.legend(loc="lower right", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_alignment_by_complexity_line(
    mode_summaries: Dict[str, Dict[str, Any]],
    model_slug: str,
    output_path: str,
    complexity_group_keys: Tuple[str, ...],
    complexity_group_labels: Dict[str, str],
    modes: Tuple[str, ...] = EVALUATION_MODES,
) -> None:
    x = np.arange(len(complexity_group_keys))
    reference_mode = modes[0]
    group_sizes = [
        mode_summaries[reference_mode]["groups"][group]["n"]
        for group in complexity_group_keys
    ]
    x_tick_labels = [
        f"{complexity_group_labels.get(group, group)}\n(n={size})"
        for group, size in zip(complexity_group_keys, group_sizes)
    ]

    fig, ax = plt.subplots(figsize=(8.5, 5.5))

    for mode in modes:
        aligned_percentages = [
            mode_summaries[mode]["groups"][group]["alignment_percentages"]["aligned"]
            for group in complexity_group_keys
        ]
        ax.plot(
            x,
            aligned_percentages,
            marker="o",
            linewidth=2,
            markersize=7,
            color=MODE_COLORS[mode],
            label=MODE_DISPLAY_LABELS[mode],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(x_tick_labels)
    ax.set_ylabel("Übereinstimmend (%)")
    ax.set_xlabel("Komplexitätsquartil")
    ax.set_ylim(0, 100)
    ax.set_title(
        f"Silver Label vs. Assessment – Übereinstimmung nach Komplexität\n"
        f"Modell: {model_slug}"
    )
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(loc="best", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)

