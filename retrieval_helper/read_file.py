import json

# Read file
def read_file(filename: str) -> dict | None:
    try:
        with open(f'data/{filename}.json', 'r') as openfile:
        
            # Reading from json file
            output = json.load(openfile)
        return output
    except (PermissionError, FileNotFoundError):
        return None
    
    