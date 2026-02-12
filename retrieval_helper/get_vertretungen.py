from typing import List, Any
from retrieval_helper.read_file import read_file
from datetime import datetime

def get_vertretungen(date: datetime) -> List[Any]:
    
    endpoint_key = 'vertretungsfall_all'
    
    vertretungen = read_file(endpoint_key)
    
    sub_vertretungen = [vertretung for vertretung in vertretungen if datetime.strptime(vertretung["startdatum"], "%Y-%m-%d") <= date and datetime.strptime(vertretung["enddatum"], "%Y-%m-%d") >= date]
    
    return sub_vertretungen