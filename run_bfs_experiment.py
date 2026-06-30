"""
Breadth-first recommendation experiment for March 17–21, 2025.

For each date, explores alternatives in BFS order until 21 recommendation sets
are collected (1 + 3 + 9 + 8). Results and diffs are stored under cache_experiments/.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from calculate_diff import analyze_added_removed, get_mas_and_clients, recommendation_key
from get_recommendations import get_recommendations, prepare_output
from llm_formatting.assignment_simple import assignment_simple, assignments_to_markdown

TARGET_COUNT = 201
BRANCHING = 3
DATES = [datetime(2025, 3, day) for day in range(17, 22)] + [datetime(2025, 3, day) for day in range(25, 30)]

CACHE_ROOT = "cache_experiments"
CACHE_RECOMMENDATIONS = os.path.join(CACHE_ROOT, "cache_recommendations")
CACHE_DIFFS = os.path.join(CACHE_ROOT, "cache_diffs")
CACHE_SIMPLE_DIFFS = os.path.join(CACHE_ROOT, "cache_simple_diffs")


@dataclass
class RecommendationNode:
    index: int
    parent_index: Optional[int]
    forced_ma: Optional[str]
    forced_client: Optional[str]
    expansion_ma: Optional[str]
    output: Optional[Dict[str, Any]]
    prepared: List[Dict[str, Any]]


def date_folder(date: datetime) -> str:
    return date.strftime("%Y-%m-%d")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_recommendation_row(
    prepared: List[Dict[str, Any]], ma_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    if not prepared:
        return None
    if ma_id:
        for rec in prepared:
            if rec["mitarbeiter"]["id"] == ma_id:
                return rec
    return prepared[0]


def get_expansion_alternatives(
    prepared: List[Dict[str, Any]], ma_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    row = get_recommendation_row(prepared, ma_id)
    if row is None:
        return []
    return row.get("alternativeKlienten", [])[:BRANCHING]


def calculate_diff_from_outputs(
    results_old: Dict[str, Any], results_new: Dict[str, Any]
) -> tuple[Dict[str, Any], List[str]]:
    mas_old, clients_old = get_mas_and_clients(results_old)
    mas_new, clients_new = get_mas_and_clients(results_new)

    analysis_result, added, removed = analyze_added_removed(
        results_old["assignment_info"]["assigned_pairs"],
        results_new["assignment_info"]["assigned_pairs"],
    )

    old_assignments = [
        assignment_simple(assignment["ma"], assignment["klient"], mas_old, clients_old)
        for assignment in removed
    ]
    new_assignments = [
        assignment_simple(assignment["ma"], assignment["klient"], mas_new, clients_new)
        for assignment in added
    ]

    analysis_result["vorher"] = assignments_to_markdown(old_assignments)
    analysis_result["nachher"] = assignments_to_markdown(new_assignments)

    return analysis_result, list(mas_new.keys())


def get_changed_assignments_from_outputs(
    results_old: Dict[str, Any], results_new: Dict[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    old_recommendations = prepare_output(results_old)
    new_recommendations = prepare_output(results_new)

    old_map = {recommendation_key(item): item for item in old_recommendations}
    new_map = {recommendation_key(item): item for item in new_recommendations}

    removed = [old_map[key] for key in old_map if key not in new_map]
    added = [new_map[key] for key in new_map if key not in old_map]

    return {"added": added, "removed": removed}


def save_json(path: str, payload: Any) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_recommendation_node(date: datetime, node: RecommendationNode) -> None:
    folder = os.path.join(CACHE_RECOMMENDATIONS, date_folder(date))
    path = os.path.join(folder, f"{node.index:02d}.json")
    payload = {
        "index": node.index,
        "parent_index": node.parent_index,
        "forced_ma": node.forced_ma,
        "forced_client": node.forced_client,
        "expansion_ma": node.expansion_ma,
        "date": date.isoformat(),
        "prepared": node.prepared,
        "output": node.output,
    }
    save_json(path, payload)


def save_diff(
    date: datetime,
    parent_index: int,
    child_index: int,
    diff: Dict[str, Any],
    new_mas: List[str],
) -> None:
    folder = os.path.join(CACHE_DIFFS, date_folder(date))
    path = os.path.join(folder, f"{parent_index:02d}_to_{child_index:02d}.json")
    save_json(
        path,
        {
            "parent_index": parent_index,
            "child_index": child_index,
            "date": date.isoformat(),
            "new_mas": new_mas,
            "diff": diff,
        },
    )


def save_simple_diff(
    date: datetime,
    parent_index: int,
    child_index: int,
    simple_diff: Dict[str, List[Dict[str, Any]]],
) -> None:
    folder = os.path.join(CACHE_SIMPLE_DIFFS, date_folder(date))
    path = os.path.join(folder, f"{parent_index:02d}_to_{child_index:02d}.json")
    save_json(
        path,
        {
            "parent_index": parent_index,
            "child_index": child_index,
            "date": date.isoformat(),
            "changed_assignments": simple_diff,
        },
    )


def run_bfs_for_date(date: datetime) -> List[RecommendationNode]:
    nodes: List[RecommendationNode] = []
    queue: deque[Dict[str, Optional[str | int]]] = deque(
        [
            {
                "parent_index": None,
                "forced_ma": None,
                "forced_client": None,
                "expansion_ma": None,
            }
        ]
    )

    print(f"\n=== BFS for {date_folder(date)} ===")

    while queue and len(nodes) < TARGET_COUNT:
        state = queue.popleft()
        parent_index = state["parent_index"]
        forced_ma = state["forced_ma"]
        forced_client = state["forced_client"]
        expansion_ma = state["expansion_ma"]

        index = len(nodes)
        print(
            f"[{index:02d}] parent={parent_index} "
            f"forced=({forced_ma}, {forced_client})"
        )

        output = get_recommendations(
            forced_ma=forced_ma,
            forced_client=forced_client,
            date=date,
        )
        prepared = prepare_output(output) if output else []

        node = RecommendationNode(
            index=index,
            parent_index=parent_index if parent_index is not None else None,
            forced_ma=forced_ma,
            forced_client=forced_client,
            expansion_ma=expansion_ma,
            output=output,
            prepared=prepared,
        )
        nodes.append(node)
        save_recommendation_node(date, node)

        if len(nodes) >= TARGET_COUNT:
            break

        row_ma = forced_ma or (
            prepared[0]["mitarbeiter"]["id"] if prepared else None
        )
        alternatives = get_expansion_alternatives(prepared, row_ma)

        for alt in alternatives:
            queue.append(
                {
                    "parent_index": index,
                    "forced_ma": row_ma,
                    "forced_client": alt["id"],
                    "expansion_ma": row_ma,
                }
            )

    print(f"Collected {len(nodes)} recommendation sets for {date_folder(date)}")
    return nodes


def compute_and_cache_diffs(date: datetime, nodes: List[RecommendationNode]) -> None:
    for node in nodes:
        if node.parent_index is None:
            continue
        parent = nodes[node.parent_index]
        if parent.output is None or node.output is None:
            print(
                f"Skipping diff {node.parent_index:02d}->{node.index:02d}: "
                "missing optimizer output"
            )
            continue

        diff, new_mas = calculate_diff_from_outputs(parent.output, node.output)
        simple_diff = get_changed_assignments_from_outputs(parent.output, node.output)

        save_diff(date, node.parent_index, node.index, diff, new_mas)
        save_simple_diff(date, node.parent_index, node.index, simple_diff)
        print(f"Cached diff {node.parent_index:02d} -> {node.index:02d}")


def main() -> None:
    ensure_dir(CACHE_RECOMMENDATIONS)
    ensure_dir(CACHE_DIFFS)
    ensure_dir(CACHE_SIMPLE_DIFFS)

    summary: Dict[str, Any] = {"dates": {}}

    for date in DATES:
        nodes = run_bfs_for_date(date)
        compute_and_cache_diffs(date, nodes)
        summary["dates"][date_folder(date)] = {
            "recommendation_count": len(nodes),
            "diff_count": sum(1 for n in nodes if n.parent_index is not None),
            "nodes": [
                {
                    "index": n.index,
                    "parent_index": n.parent_index,
                    "forced_ma": n.forced_ma,
                    "forced_client": n.forced_client,
                }
                for n in nodes
            ],
        }

    save_json(os.path.join(CACHE_ROOT, "summary.json"), summary)
    print(f"\nDone. Summary written to {CACHE_ROOT}/summary.json")


if __name__ == "__main__":
    main()
