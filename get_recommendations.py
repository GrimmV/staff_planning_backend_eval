from retrieval_helper.get_distances import get_distances
from retrieval_helper.get_clients import get_clients
from retrieval_helper.get_mas import get_mas
from retrieval_helper.get_experience_log import get_experience_log
from retrieval_helper.get_vertretungen import get_vertretungen
from datetime import datetime
from typing import List, Dict

from feature_retrieval.data_processor import DataProcessor
from feature_retrieval.retrieve_objects import get_objects_by_id

from id_handling.name_generator import ensure_names_for_ids, ensure_school_names_for_ids
from optimize.optimizer import Optimizer
from optimize.utils.caching import cache_result, retrieve_cached_result

from frontend_formatting.ma_simple import ma_simple
from frontend_formatting.client_simple import client_simple

def get_recommendations(unavailable_clients: List[str] = None, unavailable_mas: List[str] = None, forced_ma: str = None, forced_client: str = None):
        
    setting_str = f"unavailable_clients: {unavailable_clients}, unavailable_mas: {unavailable_mas}, forced_ma: {forced_ma}, forced_client: {forced_client}"
    cached_result = retrieve_cached_result(setting_str)
    if cached_result is not None:
        clients = len(cached_result["clients"])
        mas = len(cached_result["mas"])
        print(f"Cached result found for {clients} clients and {mas} MAS")
        return cached_result
    
    distances = get_distances()
    clients = get_clients()
    mas = get_mas()
    
    print(f"Using {len(clients)} clients and {len(mas)} MAS")
    experience_log = get_experience_log()
    
    date = datetime(2025, 3, 21)
    vertretungen = get_vertretungen(date)
    
    data_processor = DataProcessor(mas, clients, distances, experience_log)
    
    # Retrieve open clients from todays vertretungen
    open_clients_vertretung, open_mas_vertretung = data_processor.get_mabw_records(vertretungen)
    open_client_ids = [open_client["klientzubegleiten"]["id"] for open_client in open_clients_vertretung]
    open_clients = get_objects_by_id(clients, open_client_ids)
    open_ma_ids = [open_ma["mavertretend"]["id"] for open_ma in open_mas_vertretung]
    open_mas = get_objects_by_id(mas, open_ma_ids)
    
    clients_df, mas_df = data_processor.create_day_dataset(open_clients, open_mas, date)
    
    # Generate and persist names for MAS and clients
    ma_name_mappings = ensure_names_for_ids(mas_df["id"].tolist())
    client_name_mappings = ensure_names_for_ids(clients_df["id"].tolist())
    
    all_unique_schools = list(set(clients_df["school"].tolist()))
    school_name_mappings = ensure_school_names_for_ids(all_unique_schools)
    
    # Add name columns to dataframes
    mas_df["name"] = mas_df["id"].map(ma_name_mappings)
    clients_df["name"] = clients_df["id"].map(client_name_mappings)
    clients_df["school_name"] = clients_df["school"].map(school_name_mappings)
    
    # iterate over the mas_df and add a column "available_until" based on the free_ma_ids in the form {"id": "123", "until": "2025-01-01"}
    # First, generate the column with the correct values and then add it to the dataframe
    mas_df["available_until"] = mas_df["id"].map(lambda x: next((datetime.strptime(item["enddatum"], "%Y-%m-%d") for item in open_mas_vertretung if item["mavertretend"]["id"] == x), None))
    clients_df["available_until"] = clients_df["id"].map(lambda x: next((datetime.strptime(item["enddatum"], "%Y-%m-%d") for item in open_clients_vertretung if item["klientzubegleiten"]["id"] == x), None))
    
    # remove entries from mas_df where timeToSchool is empty
    mas_df = mas_df[mas_df["timeToSchool"] != {}].reset_index(drop=True)
    print(f"After filtering: {len(mas_df)} MAS and {len(clients_df)} clients")
    if unavailable_clients is not None:
        clients_df = clients_df[~clients_df["id"].isin(unavailable_clients)].reset_index(drop=True)
    if unavailable_mas is not None:
        mas_df = mas_df[~mas_df["id"].isin(unavailable_mas)].reset_index(drop=True)
    
    if len(mas_df) == 0 or len(clients_df) == 0:
        output = {"assignment_info": [], "mas": mas_df.to_dict(orient="records"), "clients": clients_df.to_dict(orient="records")}
        print("No MAS or clients available. Returning None.")
        return None
    
    optimizer = Optimizer(mas_df, clients_df, forced_ma=forced_ma, forced_client=forced_client)
    optimizer.create_model()

    objective_value = optimizer.solve_model()
    print(f"Objective Value: {objective_value}")
    
    if objective_value is not None:
        results = optimizer.process_results()
        mas_df["available_until"] = mas_df["available_until"].apply(lambda x: x.strftime("%Y-%m-%d") if x is not None else None)
        clients_df["available_until"] = clients_df["available_until"].apply(lambda x: x.strftime("%Y-%m-%d") if x is not None else None)
        output = {"assignment_info": results, "mas": mas_df.to_dict(orient="records"), "clients": clients_df.to_dict(orient="records")}
    else:
        print("No feasible solution found.")
        # return {"assignment_info": None, "mas": mas_df.to_dict(orient="records"), "clients": clients_df.to_dict(orient="records")}
        output = None
        
    cache_result(setting_str, output)    
    return output
    
def prepare_output(output: Dict) -> Dict:
    
    assignments = output["assignment_info"]["assigned_pairs"]
    
    recommendations = []
    
    for assignment in assignments:
        ma = assignment["ma"]
        client = assignment["klient"]
        
        raw_ma = next((d for d in output["mas"] if d.get("id") == ma), None)
        raw_client = next((d for d in output["clients"] if d.get("id") == client), None)
        
        assignment_ma = ma_simple(raw_ma["name"], raw_ma)
        assignment_client = client_simple(raw_client["name"], raw_client)
        alternative_clients = find_alternatives(output["clients"], raw_ma, raw_client["id"])
        
        recommendations.append({"mitarbeiter": assignment_ma, "klient": assignment_client, "alternativeKlienten": alternative_clients})
    
    return recommendations

def get_mas_and_clients(output: Dict) -> Dict:
    assignments = output["assignment_info"]["assigned_pairs"]
    
    mas = {}
    clients = {}
    
    for assignment in assignments:
        ma = assignment["ma"]
        client = assignment["klient"]
        
        raw_ma = next((d for d in output["mas"] if d.get("id") == ma), None)
        raw_client = next((d for d in output["clients"] if d.get("id") == client), None)
        
        mas[raw_ma["id"]] = ma_simple(raw_ma["name"], raw_ma)
        clients[raw_client["id"]] = client_simple(raw_client["name"], raw_client)
    
    return mas, clients

def find_alternatives(clients: List[Dict], ma: Dict, client_id: str):
    
    print(ma)
    alternatives = []
    not_yet_tried = [client["id"] for client in clients if client["id"] != client_id]
    
    for client_id in ma["cl_experience"].keys():
        # make sure the client is not already assigned
        if len(alternatives) >= 3:
            return alternatives
        if client_id in not_yet_tried:
            raw_client = next((d for d in clients if d.get("id") == client_id), None)
            alternatives.append(
                client_simple(raw_client["name"], raw_client)
            )
            not_yet_tried.remove(client_id)
    
    for school_name in ma["school_experience"].keys():
        all_school_clients = [d for d in clients if d.get("school") == school_name]
        for raw_client in all_school_clients:
            if len(alternatives) >= 3:
                return alternatives
            if raw_client["id"] in not_yet_tried:
                alternatives.append(
                    client_simple(raw_client["name"], raw_client)
                )
                not_yet_tried.remove(raw_client["id"])
    
    schools_ordered_dist = sorted(ma["timeToSchool"].items(), key=lambda x: x[1])
    for school_name, _ in schools_ordered_dist:
        all_school_clients = [d for d in clients if d.get("school") == school_name]
        for raw_client in all_school_clients:
            if len(alternatives) >= 3:
                return alternatives
            if raw_client["id"] in not_yet_tried:
                alternatives.append(
                    client_simple(raw_client["name"], raw_client)
                )
                not_yet_tried.remove(raw_client["id"])
    
    return alternatives

if __name__ == "__main__":
    output = get_recommendations()
    prepared_output = prepare_output(output)
    print(output)