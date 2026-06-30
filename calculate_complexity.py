"""
Compute complexity scores for BFS recommendation sets from cached diffs.

complexity = number_added
           + |number_added - number_removed|
           + high_priority_clients_affected
           + priority_changes
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

CACHE_ROOT = "cache_experiments"
CACHE_DIFFS = os.path.join(CACHE_ROOT, "cache_diffs")
CACHE_SIMPLE_DIFFS = os.path.join(CACHE_ROOT, "cache_simple_diffs")
CACHE_COMPLEXITY = os.path.join(CACHE_ROOT, "cache_complexity")


@dataclass
class ComplexityComponents:
    number_added: int
    added_removed_difference: int
    high_priority_clients_affected: int
    priority_changes: int

    @property
    def complexity(self) -> int:
        return (
            self.number_added
            + self.added_removed_difference
            + self.high_priority_clients_affected
            + self.priority_changes
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "number_added": self.number_added,
            "added_removed_difference": self.added_removed_difference,
            "high_priority_clients_affected": self.high_priority_clients_affected,
            "priority_changes": self.priority_changes,
            "complexity": self.complexity,
        }


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


def count_high_priority_clients(
    added: List[Dict[str, Any]], removed: List[Dict[str, Any]]
) -> int:
    high_priority_client_ids = set()
    for item in added + removed:
        if item["klient"]["prioritaet"] == "hoch":
            high_priority_client_ids.add(item["klient"]["id"])
    return len(high_priority_client_ids)


def count_priority_changes(
    added: List[Dict[str, Any]], removed: List[Dict[str, Any]]
) -> int:
    removed_by_ma = {item["mitarbeiter"]["id"]: item for item in removed}
    added_by_ma = {item["mitarbeiter"]["id"]: item for item in added}

    changes = 0
    for ma_id in removed_by_ma.keys() & added_by_ma.keys():
        removed_priority = removed_by_ma[ma_id]["klient"]["prioritaet"]
        added_priority = added_by_ma[ma_id]["klient"]["prioritaet"]
        if removed_priority != added_priority:
            changes += 1
    return changes


def compute_components(
    diff_payload: Dict[str, Any],
    simple_diff_payload: Optional[Dict[str, Any]],
) -> ComplexityComponents:
    counts = diff_payload["diff"]["stats"]["anzahl"]
    number_added = counts["hinzugefügt"]
    number_removed = counts["entfernt"]
    added_removed_difference = abs(number_added - number_removed)

    if simple_diff_payload is not None:
        changed = simple_diff_payload["changed_assignments"]
        added = changed.get("added", [])
        removed = changed.get("removed", [])
    else:
        added = []
        removed = []

    return ComplexityComponents(
        number_added=number_added,
        added_removed_difference=added_removed_difference,
        high_priority_clients_affected=count_high_priority_clients(added, removed),
        priority_changes=count_priority_changes(added, removed),
    )


def build_result(
    date_folder: str,
    parent_index: int,
    child_index: int,
    diff_path: str,
    components: ComplexityComponents,
) -> Dict[str, Any]:
    relative_diff_ref = os.path.join(
        "cache_experiments", "cache_diffs", date_folder, os.path.basename(diff_path)
    )
    return {
        "date": date_folder,
        "recommendation_index": child_index,
        "parent_index": parent_index,
        "diff_reference": relative_diff_ref.replace("\\", "/"),
        "components": {
            "number_added": components.number_added,
            "added_removed_difference": components.added_removed_difference,
            "high_priority_clients_affected": components.high_priority_clients_affected,
            "priority_changes": components.priority_changes,
        },
        "complexity": components.complexity,
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
            if not filename.endswith(".json"):
                continue
            entries.append((date_folder, os.path.join(date_path, filename)))
    return entries


def calculate_complexity_for_all() -> Dict[str, Any]:
    summary: Dict[str, Any] = {"dates": {}, "total_diffs": 0}

    for date_folder, diff_path in iter_diff_files():
        filename = os.path.basename(diff_path)
        indices = parse_diff_filename(filename)
        if indices is None:
            print(f"Skipping unrecognized diff file: {diff_path}")
            continue

        parent_index, child_index = indices
        diff_payload = load_json(diff_path)

        simple_diff_path = os.path.join(CACHE_SIMPLE_DIFFS, date_folder, filename)
        simple_diff_payload = (
            load_json(simple_diff_path) if os.path.exists(simple_diff_path) else None
        )
        if simple_diff_payload is None:
            print(f"Warning: no matching simple diff for {diff_path}")

        components = compute_components(diff_payload, simple_diff_payload)
        result = build_result(
            date_folder, parent_index, child_index, diff_path, components
        )

        output_path = os.path.join(CACHE_COMPLEXITY, date_folder, filename)
        save_json(output_path, result)

        if date_folder not in summary["dates"]:
            summary["dates"][date_folder] = {
                "recommendation_complexities": {},
                "by_recommendation_index": {},
            }

        summary["dates"][date_folder]["recommendation_complexities"][filename] = (
            components.complexity
        )
        summary["dates"][date_folder]["by_recommendation_index"][str(child_index)] = (
            result
        )
        summary["total_diffs"] += 1

        print(
            f"{date_folder}/{filename}: complexity={components.complexity} "
            f"(added={components.number_added}, "
            f"diff={components.added_removed_difference}, "
            f"high_prio={components.high_priority_clients_affected}, "
            f"prio_changes={components.priority_changes})"
        )

    save_json(os.path.join(CACHE_COMPLEXITY, "summary.json"), summary)
    return summary


def main() -> None:
    os.makedirs(CACHE_COMPLEXITY, exist_ok=True)
    summary = calculate_complexity_for_all()
    print(
        f"\nDone. Computed complexity for {summary['total_diffs']} diffs. "
        f"Results in {CACHE_COMPLEXITY}/"
    )


if __name__ == "__main__":
    main()
