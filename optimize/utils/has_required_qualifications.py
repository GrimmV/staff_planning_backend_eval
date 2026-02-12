from typing import List

def has_required_qualifications(employee_quals: List, client_qual: List) -> bool:
    return all(x in employee_quals for x in client_qual)