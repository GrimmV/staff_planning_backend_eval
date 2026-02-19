def float_to_time(value: float) -> str:
    is_negative = value < 0
    abs_value = abs(value)
    hours = int(abs_value)
    minutes = int((abs_value - hours) * 60)
    result = f"{hours}:{minutes:02d}"
    return f"-{result}" if is_negative else result