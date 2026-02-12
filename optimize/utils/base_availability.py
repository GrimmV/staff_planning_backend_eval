from datetime import datetime


start = datetime.strptime("00:00:00", '%H:%M:%S').time()
default_end = datetime.strptime("23:59:59", '%H:%M:%S').time()
start_as_float = start.hour + start.minute / 60
default_end_as_float = default_end.hour + default_end.minute / 60
base_availability = (start_as_float, default_end_as_float)