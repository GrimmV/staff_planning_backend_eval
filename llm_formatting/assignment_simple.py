from typing import Dict, List
from utils.float_to_time import float_to_time
from utils.diff_features import features_default

def assignment_simple(ma_id, client_id, mas: Dict, clients: Dict) -> Dict:
    
    ma = mas[ma_id]
    client = clients[client_id]
    
    schule = client["schule"]
    klient_erfahrung = next(
        (item["tage"] for item in ma["klient_erfahrung"] if item["name"] == client["name"]),
        None
    )
    schule_erfahrung = next(
        (item["tage"] for item in ma["schule_erfahrung"] if item["name"] == schule),
        None
    )
    
    assignment = {
        "klient_name": client["name"],
        "klient_benötigte_qualifikationen": client["qualifikationen"],
        "klient_tag_bis": float_to_time(client["anwesenheit"][1]),
        "klient_prioritaet": client["prioritaet"],
        "klient_nicht_vertreten_bis": client["nicht_vertreten_bis"],
        "mitarbeiter_name": ma["name"],
        "mitarbeiter_qualifikationen": ma["qualifikationen"],
        "mitarbeiter_tag_bis": float_to_time(ma["zeitfenster"][1]),
        "mitarbeiter_kann_vertreten_bis": ma["verfuegbar_bis"],
        "mitarbeiter_fahrtzeit": ma["schulen"][schule],
        "mitarbeiter_erfahrung_mit_dem_klienten": klient_erfahrung + " Tage" if klient_erfahrung is not None else "Keine",
        "mitarbeiter_erfahrung_mit_der_schule": schule_erfahrung + " Tage" if schule_erfahrung is not None else "Keine",
    }
    
    return assignment


def assignments_to_markdown(assignments, max_travel_time=60):
    header = f"| {' | '.join(features_default)} |\n"
    header += (
        f"| {' | '.join(['-' * len(f) for f in features_default])} |\n"
    )

    rows = []

    for a in assignments:
        # --- Qualification match ---
        required = set(a["klient_benötigte_qualifikationen"])
        available = set(a["mitarbeiter_qualifikationen"])
        match = required.issubset(available)

        quali_icon = "✅" if match else "❌"

        # --- Travel time check ---
        travel = a["mitarbeiter_fahrtzeit"]
        travel_icon = "✅" if travel <= max_travel_time else "❌"

        row = (
            f"| {a['mitarbeiter_name']} "
            f"| {a['klient_name']} "
            f"| {a['klient_prioritaet']} "
            f"| {a['klient_tag_bis']} "
            f"| {a['mitarbeiter_tag_bis']} "
            f"| {quali_icon} "
            f"| {travel} min {travel_icon} "
            f"| {a['mitarbeiter_erfahrung_mit_dem_klienten']} "
            f"| {a['mitarbeiter_erfahrung_mit_der_schule']} "
            f"| {a['klient_nicht_vertreten_bis']} "
            f"| {a['mitarbeiter_kann_vertreten_bis']} "
        )

        rows.append(row)

    return header + "\n".join(rows)
