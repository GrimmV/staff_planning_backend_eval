from typing import List

def get_objects_by_id(objects: List, object_ids: List) -> List:
    
    filtered_clients = [obj for obj in objects if obj.get('id') in object_ids]
    
    return filtered_clients