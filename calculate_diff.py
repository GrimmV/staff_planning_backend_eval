from typing import List, Dict, Any, Tuple
from retrieval_helper.read_file import read_file
from id_handling.name_generator import load_name_mappings
import statistics
import json

from get_recommendations import get_recommendations


feature_mapping_dr = {
    "timeToSchool": "Fahrtzeit in Minuten",
    "cl_experience": "Erfahrung mit dem Klienten",
    "school_experience": "Erfahrung mit der Schule",
    "priority": "Klienten-Priorität",
    "availability_gap": "Mitarbeiterverfügbarkeit in Tagen",
}

name_mappings = load_name_mappings()


def key_of(item: Dict) -> Tuple[str, str]:
    return item["ma"], item["klient"]


def is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def gather_numeric_fields(items: List[Dict]) -> List[str]:
    fields = set()
    for it in items:
        for elem in it["features"]:
            if is_number(elem["value"]):
                fields.add(elem["feature"])
        break
    return sorted(fields)


def compute_basic_stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"mittelwert": None, "median": None, "standardabweichung": None, "max": None, "min": None}
    count = len(values)
    mean = statistics.mean(values)
    median = statistics.median(values)
    max_value = max(values)
    min_value = min(values)
    std = None
    if count >= 2:
        # sample standard deviation
        try:
            std = statistics.pstdev(
                values
            )  # population stdev is fine here; use stdev() if you prefer sample
        except Exception:
            std = None
    return {"mittelwert": round(mean, 2), "median": round(median, 2), "standardabweichung": round(std, 2), "max": round(max_value, 2), "min": round(min_value, 2)}


def field_values(items: List[Dict], field: str) -> List[float]:
    vals = []
    for item in items:
        if is_number(item[field]["value"]):
            vals.append(float(item[field]["value"]))
    return vals


def analyze_added_removed(
    old: List[Dict], new: List[Dict]
) -> Dict:
    old_map = {key_of(x): x for x in old}
    new_map = {key_of(x): x for x in new}

    added = []
    removed = []
    all_keys = set(old_map.keys()) | set(new_map.keys())
    
    for k in old_map.keys():
        if k not in new_map.keys():
            removed.append(old_map[k])
    for k in new_map.keys():
        if k not in old_map.keys():
            added.append(new_map[k])

    stats = {
        "felder": {},
        "anzahl": {
            "alt": len(old),
            "neu": len(new),
            "hinzugefügt": len(added),
            "entfernt": len(removed),
        },
    }

    for field, description in feature_mapping_dr.items():
        values_added = [item[field] for item in added]
        values_removed = [item[field] for item in removed]

        stats_added = compute_basic_stats(values_added)
        stats_removed = compute_basic_stats(values_removed)

        stats["felder"][description] = {
            "hinzugefügt": stats_added,
            "entfernt": stats_removed,
            "mittelwert_änderung_hinzugefügt_minus_entfernt": (
                None
                if (not values_added or not values_removed)
                else round(statistics.mean(values_added) - statistics.mean(values_removed), 2)
            ),
        }

    return {
        "hinzugefügt": added,
        "entfernt": removed,
        "stats": stats,
    }


def calculate_diff(add_client: str, add_ma: str, unavailable_clients: List[str] = None, unavailable_mas: List[str] = None) -> Dict[str, Any]:
    """
    Calculate the difference between two recommendation snapshots and generate abnormality descriptions.
    
    Args:
        hard_constraints: Hard constraints for the recommendation (default: {})
        client: OpenAI client instance (optional, for LLM calls)
        tracer: Tracer instance (optional, for Phoenix tracing)
    
    Returns:
        Dictionary containing:
        - result: The analysis result with added/removed items and stats
        - abnormality_descriptions: List of abnormality descriptions for abnormal added items
    """
    
    new_clients = unavailable_clients + [add_client] if unavailable_clients is not None else [add_client]
    new_mas = unavailable_mas + [add_ma] if unavailable_mas is not None else [add_ma]
    
    results_old = get_recommendations(unavailable_clients, unavailable_mas)
    results_new = get_recommendations(new_clients, new_mas)

    analysis_result = analyze_added_removed(results_old["assignment_info"]["assigned_pairs"], results_new["assignment_info"]["assigned_pairs"])
    
    return analysis_result


if __name__ == "__main__":
    
    analysis_result = calculate_diff("dc4f6682-5418-4e69-b08e-eded0d66b060", "f3bf2472-89c6-4bd0-bd31-b092a48a89c3")
    print(json.dumps(analysis_result, indent=4))