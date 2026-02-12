from id_handling.name_generator import load_school_name_mappings
from id_handling.name_generator import load_name_mappings

def ma_simple(name, ma_object):
    
    name_mappings = load_name_mappings()
    school_name_mappings = load_school_name_mappings()
    
    cl_experience_simple = [
        {"name": name_mappings[client_id], "tage": cl_experience}
        for client_id, cl_experience in ma_object["cl_experience"].items()
    ]
    school_experience_simple = [
        {"name": school_name_mappings[school_name], "tage": school_experience}
        for school_name, school_experience in ma_object["school_experience"].items()
    ]
    
    ma_simple = {
        "name": name,
        "id": ma_object["id"],
        "verfuegbar_bis": ma_object["available_until"],
        "zeitfenster": ma_object["availability"],
        "qualifikationen": ma_object["qualifications"],
        "klient_erfahrung": cl_experience_simple,
        "schule_erfahrung": school_experience_simple,
        "schulen": {school_name_mappings[school_name]: time_to_school for school_name, time_to_school in ma_object["timeToSchool"].items()},
    }
    
    return ma_simple