from typing import List, Any
from retrieval_helper.read_file import read_file

def get_mas() -> List[Any]:
    
    endpoint_key = 'ma'
    
    mas = read_file(endpoint_key)
    
    return mas