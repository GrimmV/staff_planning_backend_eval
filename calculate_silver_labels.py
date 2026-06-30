"""
Compute silver labels for BFS recommendation diffs from cached diff statistics.

Labels (first matching rule wins):
  ablehnen        – high-priority client unassigned, or severe coverage loss
  eher ablehnen   – substantial experience drop, commute > 50 min, or
                    durchschnittlich_früher worsens for high-priority changes
  eher akzeptieren – everything else
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from utils.stats_feature_mapping import feature_mapping_dr

CACHE_ROOT = "cache_experiments"
CACHE_DIFFS = os.path.join(CACHE_ROOT, "cache_diffs")
CACHE_SILVER_LABELS = os.path.join(CACHE_ROOT, "cache_silver_labels")

PRIORITY_KEYS = ("hoch", "mittel", "niedrig")
SilverLabel = Literal["ablehnen", "eher ablehnen", "eher akzeptieren"]

FIELD_COMMUTE = feature_mapping_dr["timeToSchool"]
FIELD_CL_EXPERIENCE = feature_mapping_dr["cl_experience"]
FIELD_SCHOOL_EXPERIENCE = feature_mapping_dr["school_experience"]
FIELD_MA_AVAILABILITY = feature_mapping_dr["ma_availability"]
FIELD_CLIENT_PRIORITY = feature_mapping_dr["priority"]

EXPERIENCE_DROP_THRESHOLD = 2
COMMUTE_MAX_MINUTES = 50


@dataclass
class SilverMetrics:
    number_added: int = 0
    number_removed: int = 0
    high_priority_removed: int = 0
    high_priority_added: int = 0
    severe_coverage_loss: bool = False
    high_priority_client_unassigned: bool = False
    client_experience_drop: Optional[float] = None
    school_experience_drop: Optional[float] = None
    max_commute_minutes_added: Optional[int] = None
    high_priority_früher_removed: Optional[float] = None
    high_priority_früher_added: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number_added": self.number_added,
            "number_removed": self.number_removed,
            "high_priority_removed": self.high_priority_removed,
            "high_priority_added": self.high_priority_added,
            "severe_coverage_loss": self.severe_coverage_loss,
            "high_priority_client_unassigned": self.high_priority_client_unassigned,
            "client_experience_drop": self.client_experience_drop,
            "school_experience_drop": self.school_experience_drop,
            "max_commute_minutes_added": self.max_commute_minutes_added,
            "high_priority_früher_removed": self.high_priority_früher_removed,
            "high_priority_früher_added": self.high_priority_früher_added,
        }


@dataclass
class SilverEvaluation:
    label: SilverLabel
    triggered_rules: List[str] = field(default_factory=list)
    metrics: SilverMetrics = field(default_factory=SilverMetrics)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_diff_filename(filename: str) -> Optional[Tuple[int, int]]:
    stem = os.path.splitext(filename)[0]
    parts = stem.split("_to_")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def parse_commute_minutes(value: Optional[str]) -> Optional[int]:
    """Parse Fahrtzeit stats (minute values formatted via float_to_time)."""
    if value is None:
        return None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    return int(parts[0])


def parse_time_hours(value: Optional[str]) -> Optional[float]:
    """Parse durchschnittlich_früher stats (hour:minute decimal hours)."""
    if value is None:
        return None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    hours, minutes = int(parts[0]), int(parts[1])
    sign = -1 if hours < 0 else 1
    return sign * (abs(hours) + minutes / 60)


def get_field_stats(
    stats: Dict[str, Any], priority: str, field_name: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    fields = stats[priority]["felder"][field_name]
    return fields["entfernt"], fields["hinzugefügt"]


def max_experience_drop(stats: Dict[str, Any], field_name: str) -> Optional[float]:
    max_drop: Optional[float] = None
    for priority in PRIORITY_KEYS:
        removed, added = get_field_stats(stats, priority, field_name)
        removed_avg = removed.get("durchschnittlich_erfahrung", 0) or 0
        added_avg = added.get("durchschnittlich_erfahrung", 0) or 0
        if removed_avg <= 0:
            continue
        drop = removed_avg - added_avg
        if drop > 0 and (max_drop is None or drop > max_drop):
            max_drop = drop
    return max_drop


def max_commute_in_added(stats: Dict[str, Any]) -> Optional[int]:
    max_minutes: Optional[int] = None
    for priority in PRIORITY_KEYS:
        _, added = get_field_stats(stats, priority, FIELD_COMMUTE)
        minutes = parse_commute_minutes(added.get("max"))
        if minutes is not None and (max_minutes is None or minutes > max_minutes):
            max_minutes = minutes
    return max_minutes


def extract_metrics(stats: Dict[str, Any]) -> SilverMetrics:
    counts = stats["anzahl"]
    number_added = counts["hinzugefügt"]
    number_removed = counts["entfernt"]

    removed_prio, added_prio = get_field_stats(stats, "hoch", FIELD_CLIENT_PRIORITY)
    high_priority_removed = removed_prio["aufteilung"]["hoch"]
    high_priority_added = added_prio["aufteilung"]["hoch"]

    removed_früher, added_früher = get_field_stats(stats, "hoch", FIELD_MA_AVAILABILITY)

    return SilverMetrics(
        number_added=number_added,
        number_removed=number_removed,
        high_priority_removed=high_priority_removed,
        high_priority_added=high_priority_added,
        severe_coverage_loss=number_added + 1 < number_removed,
        high_priority_client_unassigned=high_priority_removed > high_priority_added,
        client_experience_drop=max_experience_drop(stats, FIELD_CL_EXPERIENCE),
        school_experience_drop=max_experience_drop(stats, FIELD_SCHOOL_EXPERIENCE),
        max_commute_minutes_added=max_commute_in_added(stats),
        high_priority_früher_removed=parse_time_hours(
            removed_früher.get("durchschnittlich_früher")
        ),
        high_priority_früher_added=parse_time_hours(
            added_früher.get("durchschnittlich_früher")
        ),
    )


def experience_drops_substantially(metrics: SilverMetrics) -> bool:
    for drop in (metrics.client_experience_drop, metrics.school_experience_drop):
        if drop is not None and drop > EXPERIENCE_DROP_THRESHOLD:
            return True
    return False


def commute_above_threshold(metrics: SilverMetrics) -> bool:
    return (
        metrics.max_commute_minutes_added is not None
        and metrics.max_commute_minutes_added > COMMUTE_MAX_MINUTES
    )


def high_priority_früher_goes_down(metrics: SilverMetrics) -> bool:
    removed = metrics.high_priority_früher_removed
    added = metrics.high_priority_früher_added
    if removed is None or added is None:
        return False
    return added < removed


def evaluate_silver_label(stats: Dict[str, Any]) -> SilverEvaluation:
    metrics = extract_metrics(stats)
    triggered_rules: List[str] = []
    label: SilverLabel = "eher akzeptieren"

    if metrics.high_priority_client_unassigned:
        triggered_rules.append("high_priority_client_unassigned")
    if metrics.severe_coverage_loss:
        triggered_rules.append("severe_coverage_loss")

    if triggered_rules:
        return SilverEvaluation(
            label="ablehnen",
            triggered_rules=triggered_rules,
            metrics=metrics,
        )

    if experience_drops_substantially(metrics):
        triggered_rules.append("experience_drop_substantial")
    if commute_above_threshold(metrics):
        triggered_rules.append("commute_above_50_minutes")
    if high_priority_früher_goes_down(metrics):
        triggered_rules.append("high_priority_früher_goes_down")

    if triggered_rules:
        return SilverEvaluation(
            label="eher ablehnen",
            triggered_rules=triggered_rules,
            metrics=metrics,
        )

    return SilverEvaluation(
        label=label,
        triggered_rules=triggered_rules,
        metrics=metrics,
    )


def build_result(
    date_folder: str,
    parent_index: int,
    child_index: int,
    diff_path: str,
    evaluation: SilverEvaluation,
) -> Dict[str, Any]:
    relative_diff_ref = os.path.join(
        "cache_experiments", "cache_diffs", date_folder, os.path.basename(diff_path)
    )
    return {
        "date": date_folder,
        "recommendation_index": child_index,
        "parent_index": parent_index,
        "diff_reference": relative_diff_ref.replace("\\", "/"),
        "silver_label": evaluation.label,
        "triggered_rules": evaluation.triggered_rules,
        "metrics": evaluation.metrics.to_dict(),
    }


def iter_diff_files() -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    if not os.path.isdir(CACHE_DIFFS):
        return entries

    for date_folder in sorted(os.listdir(CACHE_DIFFS)):
        date_path = os.path.join(CACHE_DIFFS, date_folder)
        if not os.path.isdir(date_path):
            continue
        for filename in sorted(os.listdir(date_path)):
            if filename.endswith(".json"):
                entries.append((date_folder, os.path.join(date_path, filename)))
    return entries


def calculate_silver_labels_for_all() -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "dates": {},
        "total_diffs": 0,
        "label_counts": {
            "ablehnen": 0,
            "eher ablehnen": 0,
            "eher akzeptieren": 0,
        },
    }

    for date_folder, diff_path in iter_diff_files():
        filename = os.path.basename(diff_path)
        indices = parse_diff_filename(filename)
        if indices is None:
            print(f"Skipping unrecognized diff file: {diff_path}")
            continue

        parent_index, child_index = indices
        diff_payload = load_json(diff_path)
        evaluation = evaluate_silver_label(diff_payload["diff"]["stats"])
        result = build_result(
            date_folder, parent_index, child_index, diff_path, evaluation
        )

        output_path = os.path.join(CACHE_SILVER_LABELS, date_folder, filename)
        save_json(output_path, result)

        if date_folder not in summary["dates"]:
            summary["dates"][date_folder] = {
                "by_recommendation_index": {},
                "label_counts": {
                    "ablehnen": 0,
                    "eher ablehnen": 0,
                    "eher akzeptieren": 0,
                },
            }

        summary["dates"][date_folder]["by_recommendation_index"][str(child_index)] = (
            result
        )
        summary["dates"][date_folder]["label_counts"][evaluation.label] += 1
        summary["label_counts"][evaluation.label] += 1
        summary["total_diffs"] += 1

        print(
            f"{date_folder}/{filename}: {evaluation.label} "
            f"({', '.join(evaluation.triggered_rules) or 'no negative rules'})"
        )

    save_json(os.path.join(CACHE_SILVER_LABELS, "summary.json"), summary)
    return summary


def main() -> None:
    os.makedirs(CACHE_SILVER_LABELS, exist_ok=True)
    summary = calculate_silver_labels_for_all()
    counts = summary["label_counts"]
    print(
        f"\nDone. Labeled {summary['total_diffs']} diffs. "
        f"ablehnen={counts['ablehnen']}, "
        f"eher ablehnen={counts['eher ablehnen']}, "
        f"eher akzeptieren={counts['eher akzeptieren']}. "
        f"Results in {CACHE_SILVER_LABELS}/"
    )


if __name__ == "__main__":
    main()
