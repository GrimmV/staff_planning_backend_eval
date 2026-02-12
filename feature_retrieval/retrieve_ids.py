from typing import List, Dict
import pandas as pd

def get_free_ma_ids(free_ma_records: List, absent_client_records, mas) -> List:
    
    open_mas = []
    for record in free_ma_records:
        if "mafrei" in record:
            open_mas.append({
                "id": record["mafrei"]["id"],
                "until": record.get("enddatum", None)
            })
        else:
            open_mas.append({
                "id": record["mavertretend"]["id"],
                "until": record.get("enddatum", None)
            })
    
    # Additionally to the free mas based on the records, search the database for mas without clients.
    # TODO: Check how to do it properly, as this includes mas that are not active anymore
    # absent_client_ids = [elem["klientabwesend"]["id"] for elem in absent_client_records]
    # for ma in mas:
    #     clients = ma.get("aktiveklientinnen", [])
    #     if len(clients) == 1:
    #         client_id = clients[0]
    #         if client_id in absent_client_ids:
    #             print(f"found free ma: {ma['id']} for absent client...")
    #             open_mas.append(ma["id"])
    
    return open_mas

def get_ma_assignments(rescheduled_ma_records: List) -> Dict[str, str]:
    
    replaced_mas = {}
    
    for record in rescheduled_ma_records:
        replaced_mas[record["mavertretend"]["id"]] = record["klientzubegleiten"]["id"] 
    
    return replaced_mas

def get_client_record_assignments(records: List) -> Dict[str, str]:
    
    client_record_assignments = {}
    
    for record in records:
        client_record_assignments[record["klientzubegleiten"]["id"]] = record["id"]
        
    return client_record_assignments

def get_open_client_ids(records: List) -> List:
        
    clients = []
    
    for record in records:
        clients.append({
            "id": record["klientzubegleiten"]["id"],
            "until": record.get("enddatum", None)
        })
        
    return clients