from typing import List, Dict, Any, Tuple
from retrieval_helper.read_file import read_file
from id_handling.name_generator import load_name_mappings
import statistics
import json

from get_recommendations import get_recommendations, get_mas_and_clients
from llm_formatting.assignment_simple import assignment_simple
from llm_formatting.assignment_simple import assignments_to_markdown


feature_mapping_dr = {
    "timeToSchool": "Fahrtzeit in Minuten",
    "cl_experience": "Erfahrung mit dem Klienten",
    "school_experience": "Erfahrung mit der Schule",
    "priority": "Klienten-Priorität",
    "availability_gap": "Mitarbeiterverfügbarkeit in Tagen",
    "ma_availability": "Zeitfenster des Mitarbeiters ist über vollen Zeitraum des Klienten",
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
        return {"durchschnitt": None, "max": None, "min": None}
    count = len(values)
    mean = statistics.mean(values)
    max_value = max(values)
    min_value = min(values)
    if count >= 2:
        # sample standard deviation
        try:
            std = statistics.pstdev(
                values
            )  # population stdev is fine here; use stdev() if you prefer sample
        except Exception:
            std = None
    return {"durchschnitt": round(mean, 2), "max": round(max_value, 2), "min": round(min_value, 2)}

def compute_priority_stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"aufteilung": {"hoch": 0, "mittel": 0, "niedrig": 0}}
    return {"aufteilung": {"hoch": values.count(1), "mittel": values.count(2), "niedrig": values.count(3)}}

def compute_verfügbarkeit_stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"voller_zeitraum": 0, "teilweiser_zeitraum": 0, "durchschnittlich_fehlend": 0}
    voller_zeitraum = [value for value in values if value >= 0]
    teilweiser_zeitraum = [value for value in values if value < 0]
    durchschnittlich_fehlend = statistics.mean(teilweiser_zeitraum) if len(teilweiser_zeitraum) > 0 else 0
    return {"voller_zeitraum": len(voller_zeitraum), "teilweiser_zeitraum": len(teilweiser_zeitraum), "durchschnittlich_fehlend": durchschnittlich_fehlend}

def compute_erfahrung_stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"mit_erfahrung": 0, "ohne_erfahrung": 0, "durchschnittlich_erfahrung": 0}
    mit_erfahrung = [value for value in values if value > 0]
    ohne_erfahrung = [value for value in values if value == 0]
    durchschnittlich_erfahrung = statistics.mean(mit_erfahrung) if len(mit_erfahrung) > 0 else 0
    return {"mit_erfahrung": len(mit_erfahrung), "ohne_erfahrung": len(ohne_erfahrung), "durchschnittlich_erfahrung": durchschnittlich_erfahrung}

def compute_zeitfenster_stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"voller_zeitraum": 0, "teilweiser_zeitraum": 0}
    return {"voller_zeitraum": values.count(True), "teilweiser_zeitraum": values.count(False)}

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
    
    for k in old_map.keys():
        if k not in new_map.keys():
            removed.append(old_map[k])
    for k in new_map.keys():
        if k not in old_map.keys():
            added.append(new_map[k])

    stats = {
        "felder": {},
        "anzahl": {
            "gesamt_vorher": len(old),
            "gesamt_nachher": len(new),
            "hinzugefügt": len(added),
            "entfernt": len(removed),
        },
    }

    for field, description in feature_mapping_dr.items():
        values_added = [item[field] for item in added]
        values_removed = [item[field] for item in removed]

        if field == "ma_availability":
            stats_added = compute_zeitfenster_stats(values_added)
            stats_removed = compute_zeitfenster_stats(values_removed)
        elif field == "priority":
            stats_added = compute_priority_stats(values_added)
            stats_removed = compute_priority_stats(values_removed)
        elif field == "availability_gap":
            stats_added = compute_verfügbarkeit_stats(values_added)
            stats_removed = compute_verfügbarkeit_stats(values_removed)
        elif field == "cl_experience":
            stats_added = compute_erfahrung_stats(values_added)
            stats_removed = compute_erfahrung_stats(values_removed)
        elif field == "school_experience":
            stats_added = compute_erfahrung_stats(values_added)
            stats_removed = compute_erfahrung_stats(values_removed)
        else:
            stats_added = compute_basic_stats(values_added)
            stats_removed = compute_basic_stats(values_removed)

        stats["felder"][description] = {
            "hinzugefügt": stats_added,
            "entfernt": stats_removed
        }

    return {
        "stats": stats,
    }, added, removed


def calculate_diff(add_client: str, add_ma: str, unavailable_clients: List[str] = None, unavailable_mas: List[str] = None, features: List[str] = None) -> Dict[str, Any]:
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
    for d in results_old["assignment_info"]["assigned_pairs"]:
        if d["ma"] == add_ma:
            results_old["assignment_info"]["assigned_pairs"].remove(d)
            break
    results_new = get_recommendations(new_clients, new_mas)
    
    mas_old, clients_old = get_mas_and_clients(results_old)
    mas_new, clients_new = get_mas_and_clients(results_new)

    analysis_result, added, removed = analyze_added_removed(results_old["assignment_info"]["assigned_pairs"], results_new["assignment_info"]["assigned_pairs"])
    
    old_assignments = [assignment_simple(assignment["ma"], assignment["klient"], mas_old, clients_old) for assignment in removed]
    new_assignments = [assignment_simple(assignment["ma"], assignment["klient"], mas_new, clients_new) for assignment in added]
    
    old_assignments_markdown = assignments_to_markdown(old_assignments)
    new_assignments_markdown = assignments_to_markdown(new_assignments)
    
    analysis_result["vorher"] = old_assignments_markdown
    analysis_result["nachher"] = new_assignments_markdown
    
    return analysis_result, list(mas_new.keys())


if __name__ == "__main__":
    
    analysis_result, _ = calculate_diff("dc4f6682-5418-4e69-b08e-eded0d66b060", "f3bf2472-89c6-4bd0-bd31-b092a48a89c3")
    print(json.dumps(analysis_result, indent=4))