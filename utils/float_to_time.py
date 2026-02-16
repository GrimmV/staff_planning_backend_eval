def float_to_time(float: float) -> str:
    hours = int(float)
    minutes = int((float - hours) * 60)
    return f"{hours:02d}:{minutes:02d}"