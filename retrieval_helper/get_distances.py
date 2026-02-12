from typing import List, Any
from retrieval_helper.read_file import read_file

def get_distances() -> List[Any]:
    
    endpoint_key = 'dist_ma_sch'
    
    distances = read_file(endpoint_key)
    
    return distances