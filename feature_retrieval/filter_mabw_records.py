from typing import Tuple, List, Dict

def filter_mabw_records(records: List) -> Tuple[List]:
    
    open_clients = []
    open_mas = []
    
    for record in records:
        if record["typ"] == "mabw":
            if "mavertretend" in  record:
                open_mas.append(record)
            if 'klientzubegleiten' in record:
                open_clients.append(record)
        
    
    return open_clients, open_mas