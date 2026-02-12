import json
import os
import random
from typing import Dict

# Common first and last names for random generation
FIRST_NAMES = [
    "Anna", "Max", "Sophie", "Tom", "Emma", "Lukas", "Hannah", "Felix", "Mia", "Noah",
    "Lena", "Ben", "Laura", "Jonas", "Sarah", "Paul", "Julia", "Finn", "Lisa", "Leon",
    "Maria", "Tim", "Emily", "David", "Clara", "Julian", "Amelie", "Moritz", "Marie", "Niklas",
    "Luisa", "Elias", "Charlotte", "Anton", "Johanna", "Theo", "Lina", "Jakob", "Nora", "Samuel"
]

LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
    "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun",
    "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Schmitz", "Krause", "Meier", "Lehmann",
    "Schmid", "Schulze", "Maier", "Köhler", "Herrmann", "König", "Walter", "Huber", "Mayer", "Peters"
]

# Path to the name storage file
NAME_STORAGE_FILE = "data/name_mappings.json"

# Path to the school name storage file
SCHOOL_NAME_STORAGE_FILE = "data/school_name_mappings.json"


def load_name_mappings() -> Dict[str, str]:
    """Load name mappings from file. Returns empty dict if file doesn't exist."""
    if os.path.exists(NAME_STORAGE_FILE):
        try:
            with open(NAME_STORAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_name_mappings(mappings: Dict[str, str]) -> None:
    """Save name mappings to file."""
    # Ensure the directory exists
    os.makedirs(os.path.dirname(NAME_STORAGE_FILE), exist_ok=True)
    
    with open(NAME_STORAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)


def load_school_name_mappings() -> Dict[str, str]:
    """Load school name mappings from file. Returns empty dict if file doesn't exist."""
    if os.path.exists(SCHOOL_NAME_STORAGE_FILE):
        try:
            with open(SCHOOL_NAME_STORAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_school_name_mappings(mappings: Dict[str, str]) -> None:
    """Save school name mappings to file."""
    # Ensure the directory exists
    os.makedirs(os.path.dirname(SCHOOL_NAME_STORAGE_FILE), exist_ok=True)
    
    with open(SCHOOL_NAME_STORAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)


def generate_random_name() -> str:
    """Generate a random full name."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    return f"{first_name} {last_name}"


def generate_random_school_name() -> str:
    """Generate a random school name based on last names."""
    last_name = random.choice(LAST_NAMES)
    return f"{last_name}-Schule"


def ensure_names_for_ids(ids: list) -> Dict[str, str]:
    """
    Ensure that all provided IDs have names in the storage.
    If a name doesn't exist for an ID, generate one and save it.
    Returns a dictionary mapping ID to name.
    """
    name_mappings = load_name_mappings()
    updated = False
    
    for id_value in ids:
        if id_value not in name_mappings:
            name_mappings[id_value] = generate_random_name()
            updated = True
    
    if updated:
        save_name_mappings(name_mappings)
    
    return {id_value: name_mappings[id_value] for id_value in ids}


def ensure_school_names_for_ids(ids: list) -> Dict[str, str]:
    """
    Ensure that all provided school IDs have school names in the storage.
    If a name doesn't exist for an ID, generate one and save it.
    Returns a dictionary mapping school ID to school name.
    """
    school_name_mappings = load_school_name_mappings()
    updated = False
    
    for id_value in ids:
        if id_value not in school_name_mappings:
            school_name_mappings[id_value] = generate_random_school_name()
            updated = True
    
    if updated:
        save_school_name_mappings(school_name_mappings)
    
    return {id_value: school_name_mappings[id_value] for id_value in ids}

