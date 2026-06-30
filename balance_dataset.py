"""
Build a stratified balanced sample manifest for silver-label classes.

Downsamples eher ablehnen and eher akzeptieren to match the ablehnen count while
preserving stratum proportions across date, complexity quartile, and triggered rules.
Selection is deterministic (sorted diff keys), not random.

Original caches are untouched; only diff_key IDs are written to
cache_experiments/cache_balanced_sample.json.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from alignment_analysis import (
    BALANCED_SAMPLE_PATH,
    BALANCE_TARGET_LABELS,
    CACHE_SILVER_LABELS,
    ScoreLabel,
    compute_complexity_quartile_breakpoints,
    complexity_quartile_group,
    load_complexity_by_diff,
    load_silver_label_records,
    save_json,
    triggered_rules_key,
)

Stratum = Tuple[str, str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a stratified balanced sample manifest keyed by diff_key "
            "(date/parent_to_child.json)."
        )
    )
    parser.add_argument(
        "--output",
        default=BALANCED_SAMPLE_PATH,
        help="Path for the balanced sample manifest JSON.",
    )
    return parser.parse_args()


def build_stratum(
    record: Dict[str, Any],
    complexities: Dict[str, int],
    quartile_breakpoints: Tuple[float, float, float],
) -> Stratum:
    diff_key = record["diff_key"]
    date = record["date"]
    complexity = complexities[diff_key]
    cx_bin = complexity_quartile_group(complexity, quartile_breakpoints)
    rules = triggered_rules_key(record.get("triggered_rules") or [])
    return date, cx_bin, rules


def proportional_allocate(stratum_sizes: Dict[Stratum, int], target: int) -> Dict[Stratum, int]:
    total = sum(stratum_sizes.values())
    if total == 0:
        return {}
    if total <= target:
        return {stratum: size for stratum, size in stratum_sizes.items()}

    allocations: Dict[Stratum, int] = {}
    remainders: List[Tuple[float, Stratum]] = []
    allocated = 0
    for stratum in sorted(stratum_sizes):
        size = stratum_sizes[stratum]
        exact = target * size / total
        base = int(exact)
        allocations[stratum] = base
        remainders.append((exact - base, stratum))
        allocated += base

    for _, stratum in sorted(remainders, key=lambda item: (-item[0], item[1])):
        if allocated >= target:
            break
        allocations[stratum] += 1
        allocated += 1

    return allocations


def select_from_strata(
    records_by_stratum: Dict[Stratum, List[str]],
    target: int,
) -> Tuple[List[str], Dict[str, int]]:
    stratum_sizes = {
        stratum: len(keys) for stratum, keys in records_by_stratum.items()
    }
    allocations = proportional_allocate(stratum_sizes, target)

    selected: List[str] = []
    stratum_counts: Dict[str, int] = {}
    for stratum in sorted(records_by_stratum):
        keys = sorted(records_by_stratum[stratum])
        take = min(allocations.get(stratum, 0), len(keys))
        picked = keys[:take]
        selected.extend(picked)
        stratum_counts["|".join(stratum)] = len(picked)

    if len(selected) < target:
        remaining = target - len(selected)
        selected_set = set(selected)
        pool = sorted(
            key
            for keys in records_by_stratum.values()
            for key in keys
            if key not in selected_set
        )
        for key in pool[:remaining]:
            selected.append(key)

    return sorted(selected[:target]), stratum_counts


def stratified_sample_class(
    class_records: List[Dict[str, Any]],
    complexities: Dict[str, int],
    quartile_breakpoints: Tuple[float, float, float],
    target: int,
) -> Tuple[List[str], Dict[str, int]]:
    records_by_stratum: Dict[Stratum, List[str]] = defaultdict(list)
    for record in class_records:
        stratum = build_stratum(record, complexities, quartile_breakpoints)
        records_by_stratum[stratum].append(record["diff_key"])

    return select_from_strata(records_by_stratum, target)


def build_balanced_manifest(
    silver_records: Dict[str, Dict[str, Any]],
    complexities: Dict[str, int],
) -> Dict[str, Any]:
    quartile_breakpoints = compute_complexity_quartile_breakpoints(complexities)
    q1, q2, q3 = quartile_breakpoints

    records_by_label: Dict[ScoreLabel, List[Dict[str, Any]]] = {
        label: [] for label in BALANCE_TARGET_LABELS
    }
    for diff_key, record in silver_records.items():
        label = record["silver_label"]
        if label not in BALANCE_TARGET_LABELS:
            continue
        records_by_label[label].append({**record, "diff_key": diff_key})

    class_counts_before = {
        label: len(records_by_label[label]) for label in BALANCE_TARGET_LABELS
    }
    target_per_class = min(class_counts_before.values())
    if target_per_class == 0:
        raise ValueError("At least one target silver-label class has zero samples.")

    diff_keys_by_class: Dict[str, List[str]] = {}
    stratum_sample_counts_by_class: Dict[str, Dict[str, int]] = {}
    all_diff_keys: List[str] = []

    for label in BALANCE_TARGET_LABELS:
        selected, stratum_counts = stratified_sample_class(
            records_by_label[label],
            complexities,
            quartile_breakpoints,
            target_per_class,
        )
        diff_keys_by_class[label] = selected
        stratum_sample_counts_by_class[label] = stratum_counts
        all_diff_keys.extend(selected)

    class_counts_after = {
        label: len(diff_keys_by_class[label]) for label in BALANCE_TARGET_LABELS
    }

    return {
        "strategy": "stratified_silver_balance",
        "stratify_by": ["date", "complexity_quartile", "triggered_rules"],
        "target_labels": list(BALANCE_TARGET_LABELS),
        "target_per_class": target_per_class,
        "class_counts_before": class_counts_before,
        "class_counts_after": class_counts_after,
        "complexity_quartiles": {
            "q1": q1,
            "q2": q2,
            "q3": q3,
            "bin_keys": ["Q1", "Q2", "Q3", "Q4"],
            "bin_labels": {
                "Q1": f"≤{q1:g}",
                "Q2": f"{q1:g}–{q2:g}",
                "Q3": f"{q2:g}–{q3:g}",
                "Q4": f">{q3:g}",
            },
        },
        "diff_keys": sorted(all_diff_keys),
        "diff_keys_by_class": diff_keys_by_class,
        "stratum_sample_counts_by_class": stratum_sample_counts_by_class,
    }


def run_balance(output_path: str) -> Dict[str, Any]:
    silver_records = load_silver_label_records()
    if not silver_records:
        raise FileNotFoundError(f"No silver labels found in {CACHE_SILVER_LABELS}")

    complexities = load_complexity_by_diff()
    missing = [key for key in silver_records if key not in complexities]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} silver-label diffs are missing complexity scores."
        )

    manifest = build_balanced_manifest(silver_records, complexities)
    save_json(output_path, manifest)
    manifest["manifest_path"] = output_path.replace("\\", "/")
    return manifest


def main() -> None:
    args = parse_args()
    manifest = run_balance(args.output)

    print(f"Balanced sample written to {manifest['manifest_path']}")
    print(f"  target per class: {manifest['target_per_class']}")
    print("  class counts before:")
    for label, count in manifest["class_counts_before"].items():
        print(f"    {label}: {count}")
    print("  class counts after:")
    for label, count in manifest["class_counts_after"].items():
        print(f"    {label}: {count}")
    print(f"  total diff_keys: {len(manifest['diff_keys'])}")
    q = manifest["complexity_quartiles"]
    print(
        f"  complexity quartiles: Q1={q['q1']}, Q2={q['q2']}, Q3={q['q3']}"
    )


if __name__ == "__main__":
    main()
