from id_handling.name_generator import load_school_name_mappings

def client_simple(name, client_object):
    
    school_name_mappings = load_school_name_mappings()
    
    client = {
        "name": name,
        "id": client_object["id"],
        "nicht_vertreten_bis": client_object["available_until"],
        "anwesenheit": client_object["timeWindow"],
        "qualifikationen": client_object["neededQualifications"],
        "schule": school_name_mappings[client_object["school"]],
        "prioritaet": translate_priority(client_object["priority"]),
    }
    
    return client

def translate_priority(priority):
    if priority == 1:
        return "hoch"
    elif priority == 2:
        return "mittel"
    else:
        return "niedrig"