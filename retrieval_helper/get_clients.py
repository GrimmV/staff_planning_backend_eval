from typing import List, Any
from retrieval_helper.read_file import read_file

def get_clients() -> List[Any]:
    
    endpoint_key = 'klient'
    
    clients = read_file(endpoint_key)
    
    return clients