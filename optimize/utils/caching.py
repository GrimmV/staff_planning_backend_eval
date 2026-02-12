import hashlib
import os
import json

CACHE_DIR = "cache"

def cache_result(unique_settings: str, result: dict) -> None:
    """Cache the result of the optimization for the given unique settings."""
    
    hash_object = hashlib.sha256(unique_settings.encode())
    hex_dig = hash_object.hexdigest()
    
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        
    with open(os.path.join(CACHE_DIR, f"{hex_dig}.json"), "w") as f:
        json.dump(result, f)
        
        
def retrieve_cached_result(unique_settings: str) -> dict | None:
    """Retrieve the cached result for the given unique settings."""
    
    hash_object = hashlib.sha256(unique_settings.encode())
    hex_dig = hash_object.hexdigest()
    
    if not os.path.exists(CACHE_DIR):
        return None
    try:
        with open(os.path.join(CACHE_DIR, f"{hex_dig}.json"), "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None