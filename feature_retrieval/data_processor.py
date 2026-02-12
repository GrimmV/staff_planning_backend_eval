
from typing import List, Tuple, Dict
from datetime import datetime

from feature_retrieval.client_features import aggregate_client_features
from feature_retrieval.ma_features import aggregate_ma_features
from feature_retrieval.filter_mabw_records import filter_mabw_records
from feature_retrieval.filter_kabw_records import filter_kabw_records
from feature_retrieval.retrieve_ids import get_ma_assignments, get_open_client_ids, get_free_ma_ids


class DataProcessor:
    
    def __init__(self, mas, clients, distances, experience_log) -> None:
        self.mas = mas
        self.clients = clients
        
        self.distances = distances
        self.experience_log = experience_log
        

    def get_mabw_records(self, vertretungen: List) -> Dict:
        
        filtered_mabw_records = filter_mabw_records(vertretungen)
        
        return filtered_mabw_records
    
    def get_kabw_records(self, vertretungen: List) -> Dict:
        
        filtered_kabw_records = filter_kabw_records(vertretungen)
        
        return filtered_kabw_records
    
    def get_ma_assignments(self, rescheduled_ma_records: List) -> Dict:
        
        return get_ma_assignments(rescheduled_ma_records)
    
    def create_day_dataset(self, clients, mas, date: datetime):

        clients_df, clients_dict = aggregate_client_features(
            clients, date
        )
        mas_df, mas_dict = aggregate_ma_features(
            mas, self.distances, clients_dict, self.experience_log
        )
        
        return clients_df, mas_df


    def get_open_clients_and_mas(self, vertretungen: List, assigned_mas: List, open_client_records: List) -> Tuple[List, List]:        
        
        filtered_kabw_records = filter_kabw_records(vertretungen, assigned_mas)
        absent_client_records = filtered_kabw_records["absent_clients"]
        free_ma_records = filtered_kabw_records["free_mas"]
        
        open_client_ids = get_open_client_ids(open_client_records)
        free_ma_ids = get_free_ma_ids(free_ma_records, absent_client_records, self.mas)

        return open_client_ids, free_ma_ids


    def get_client_record_assignments(self, records: List) -> Dict[str, str]:
        
        client_record_assignments = {}
        
        for record in records:
            client_record_assignments[record["klientzubegleiten"]["id"]] = record["id"]
            
        return client_record_assignments