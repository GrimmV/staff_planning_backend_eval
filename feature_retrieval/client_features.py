from typing import List
from datetime import datetime
import pandas as pd

weekDaysMapping = ("montag", "dienstag", 
                   "mittwoch", "donnerstag",
                   "freitag", "samstag", "sonntag")

def aggregate_client_features(open_client_objects: List, date: datetime):
    client_dict = {
        "id": [],
        "neededQualifications": [],
        "timeWindow": [],
        "priority": [],
        "school": []
    }
    weekday = get_weekday(date)
    for client in open_client_objects:
        if get_timewindow(client, weekday) is None:
            pass
        client_dict["id"].append(client["id"])
        client_dict["neededQualifications"].append(get_qualifications(client))
        client_dict["timeWindow"].append(get_timewindow(client, weekday)) 
        priority_id = client.get("vertretungab")["id"] if client.get("vertretungab") != None else 100       
        client_dict["priority"].append(convert_priority(priority_id))
        client_dict["school"].append(client["schule"]["id"] if client.get("schule", None) != None else None)
        
    client_df = pd.DataFrame.from_dict(client_dict)
    
    
    return client_df, client_dict

def get_qualifications(client):
    attributes = []
    if client.get("hatdiabetes", 0) == 1:
        attributes.append("diabetes")
    if client.get("brauchtpflege", 0) == 1:
        attributes.append("pflege")

    return attributes

def get_timewindow(client, weekday):
    timetable = client.get("aktuellerstundenplan")
    if (timetable == None) or timetable.get(f"{weekday}von") == None:
        return None
    start = timetable.get(f"{weekday}von")
    start_formatted = datetime.strptime(start, '%H:%M:%S').time()
    end = timetable.get(f"{weekday}bis")
    end_formatted = datetime.strptime(end, '%H:%M:%S').time()
    start_as_float = start_formatted.hour + start_formatted.minute / 60
    end_as_float = end_formatted.hour + end_formatted.minute / 60
    
    return (start_as_float, end_as_float)

def convert_priority(priority_id):
    
    if priority_id == "tag1hoheprio":
        return 1
    elif priority_id == "tag1":
        return 2
    else:
        return 3
    

def get_weekday(target_date: datetime) -> str:
    weekday_num = target_date.weekday()
    weekday = weekDaysMapping[weekday_num]
    return weekday