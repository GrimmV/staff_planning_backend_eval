"""
Analyze grouped warning preservation across evaluation settings.

Groups the silver-label classes
    W = {"eher ablehnen", "ablehnen"}
and reports per-mode rates for:
    - Warning preservation
    - False reassurance
    - Hard-case warning preservation
    - Hard false reassurance
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from typing import Any, Dict, List, Literal, Optional

ScoreLabel = Literal["ablehnen", "eher ablehnen", "eher akzeptieren"]

CACHE_ROOT = "cache_experiments"
CACHE_SILVER_LABELS = os.path.join(CACHE_ROOT, "cache_silver_labels")
CACHE_EVALUATIONS = os.path.join(CACHE_ROOT, "cache_evaluations")
BALANCED_SAMPLE_PATH = os.path.join(CACHE_ROOT, "cache_balanced_sample.json")
EVALUATION_MODES = ("full", "simple", "simple_direct")
SCORE_ORDINAL: Dict[ScoreLabel, int] = {
    "eher akzeptieren": 0,
    "eher ablehnen": 1,
    "ablehnen": 2,
}

OUTPUT_DIR = "cache_experiments/analysis/warning_preservation"
WARNING_LABELS = {"eher ablehnen", "ablehnen"}
HARD_LABEL = "ablehnen"
FALSE_REASSURANCE_LABEL = "eher akzeptieren"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze whether warning labels are preserved when grouping "
            "'eher ablehnen' and 'ablehnen'."
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
        help="Directory for summary JSON and CSV table.",
    )
    return parser.parse_args()


def safe_rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def sanitize_model_name(model_name: str) -> str:
    return model_name.replace(".", "_").replace("/", "_")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_balanced_diff_keys(path: str = BALANCED_SAMPLE_PATH) -> set[str]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Balanced sample manifest not found at {path}. Run balance_dataset.py first."
        )
    manifest = load_json(path)
    return set(manifest["diff_keys"])


def load_balanced_silver_labels(
    allowed_diff_keys: set[str],
) -> Dict[str, ScoreLabel]:
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
            key = f"{date_folder}/{filename}"
            if key not in allowed_diff_keys:
                continue
            payload = load_json(os.path.join(date_path, filename))
            labels[key] = payload["silver_label"]
    return labels


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
    allowed_diff_keys: set[str],
) -> List[Dict[str, Any]]:
    mode_root = evaluation_dir(mode, model_slug)
    if not os.path.isdir(mode_root):
        raise FileNotFoundError(f"Missing evaluation mode directory: {mode_root}")

    pairs: List[Dict[str, Any]] = []
    for key, silver_label in silver_labels.items():
        if key not in allowed_diff_keys:
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
                "exact_match": silver_label == assessment_score,
            }
        )
    return pairs


def _format_rate(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def compute_mode_stats(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    warning_cases = [
        pair for pair in pairs if pair["silver_label"] in WARNING_LABELS
    ]
    hard_cases = [pair for pair in pairs if pair["silver_label"] == HARD_LABEL]

    warning_denominator = len(warning_cases)
    hard_denominator = len(hard_cases)

    warning_preserved = sum(
        1
        for pair in warning_cases
        if pair["assessment_score"] in WARNING_LABELS
    )
    false_reassurance = sum(
        1
        for pair in warning_cases
        if pair["assessment_score"] == FALSE_REASSURANCE_LABEL
    )
    hard_warning_preserved = sum(
        1
        for pair in hard_cases
        if pair["assessment_score"] in WARNING_LABELS
    )
    hard_false_reassurance = sum(
        1
        for pair in hard_cases
        if pair["assessment_score"] == FALSE_REASSURANCE_LABEL
    )

    return {
        "n_total": len(pairs),
        "n_warning_cases": warning_denominator,
        "n_hard_cases": hard_denominator,
        "warning_preservation": safe_rate(
            warning_preserved,
            warning_denominator,
        ),
        "false_reassurance": safe_rate(
            false_reassurance,
            warning_denominator,
        ),
        "hard_case_warning_preservation": safe_rate(
            hard_warning_preserved,
            hard_denominator,
        ),
        "hard_false_reassurance": safe_rate(
            hard_false_reassurance,
            hard_denominator,
        ),
        "counts": {
            "warning_preserved": warning_preserved,
            "false_reassurance": false_reassurance,
            "hard_warning_preserved": hard_warning_preserved,
            "hard_false_reassurance": hard_false_reassurance,
        },
    }


def write_csv(rows: List[Dict[str, Any]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "Mode",
                "Warning preservation",
                "False reassurance",
                "Hard-case warning preservation",
                "Hard false reassurance",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_table_rows(mode_stats: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for mode in EVALUATION_MODES:
        stats = mode_stats.get(mode)
        if stats is None:
            continue
        rows.append(
            {
                "Mode": mode,
                "Warning preservation": _format_rate(stats["warning_preservation"]),
                "False reassurance": _format_rate(stats["false_reassurance"]),
                "Hard-case warning preservation": _format_rate(
                    stats["hard_case_warning_preservation"]
                ),
                "Hard false reassurance": _format_rate(
                    stats["hard_false_reassurance"]
                ),
            }
        )
    return rows


def run_analysis(model_slug: str, output_dir: str) -> Dict[str, Any]:
    allowed_diff_keys = load_balanced_diff_keys()
    silver_labels = load_balanced_silver_labels(allowed_diff_keys)
    if not silver_labels:
        raise FileNotFoundError(f"No balanced silver labels found in {CACHE_SILVER_LABELS}")

    os.makedirs(output_dir, exist_ok=True)

    summary: Dict[str, Any] = {
        "model_slug": model_slug,
        "balanced_sample_n": len(allowed_diff_keys),
        "warning_labels": sorted(WARNING_LABELS),
        "hard_label": HARD_LABEL,
        "false_reassurance_prediction": FALSE_REASSURANCE_LABEL,
        "modes": {},
    }

    mode_stats: Dict[str, Dict[str, Any]] = {}
    for mode in EVALUATION_MODES:
        pairs = load_mode_pairs(mode, model_slug, silver_labels, allowed_diff_keys)
        mode_stats[mode] = compute_mode_stats(pairs)

    summary["modes"] = mode_stats

    rows = build_table_rows(mode_stats)
    csv_path = os.path.join(output_dir, "warning_preservation_table.csv")
    write_csv(rows, csv_path)

    summary_path = os.path.join(output_dir, "summary.json")
    save_json(summary_path, summary)

    summary["table_csv"] = csv_path.replace("\\", "/")
    summary["summary_json"] = summary_path.replace("\\", "/")
    summary["table_rows"] = rows
    return summary


def main() -> None:
    args = parse_args()
    model_slug = discover_model_slug(args.model)
    print(f"Analyzing warning preservation for model={model_slug}")
    summary = run_analysis(model_slug, args.output_dir)

    print(f"\nResults written to {args.output_dir}/")
    for row in summary["table_rows"]:
        print(
            f"  [{row['Mode']}] "
            f"warning_preservation={row['Warning preservation']}, "
            f"false_reassurance={row['False reassurance']}, "
            f"hard_case_warning_preservation={row['Hard-case warning preservation']}, "
            f"hard_false_reassurance={row['Hard false reassurance']}"
        )
    print(f"  table: {summary['table_csv']}")
    print(f"  summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()
