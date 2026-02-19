"""
Adapt vertretungsfall_all.json: for entries with startdatum "2025-03-21",
generate randomized enddatum by adding days (mean=4, std=2).
Output: vertretungsfall_adapted.json
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "data" / "vertretungsfall_all_original.json"
OUTPUT_FILE = Path(__file__).parent / "data" / "vertretungsfall_adapted.json"
TARGET_STARTDATUM = "2025-03-21"
DAYS_MEAN = 4
DAYS_STD = 2


def generate_days_to_add() -> int:
    """Generate days to add from normal distribution (mean=4, std=2)."""
    days = random.gauss(DAYS_MEAN, DAYS_STD)
    return max(0, int(round(days)))


def add_days_to_date(date_str: str, days: int) -> str:
    """Add days to a date string (YYYY-MM-DD) and return new date string."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    new_dt = dt + timedelta(days=days)
    return new_dt.strftime("%Y-%m-%d")


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    adapted_count = 0
    for entry in data:
        if entry.get("startdatum") == TARGET_STARTDATUM:
            days = generate_days_to_add()
            entry["enddatum"] = add_days_to_date(entry["startdatum"], days)
            adapted_count += 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"Adapted {adapted_count} entries with startdatum {TARGET_STARTDATUM}")
    print(f"Output written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
