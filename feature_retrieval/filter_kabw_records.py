from typing import List

def filter_kabw_records(records: List) -> List:
    
    free_mas = []
    
    for record in records:
        if record["typ"] == "kabw":
            free_mas.append(record)
                
    return free_mas