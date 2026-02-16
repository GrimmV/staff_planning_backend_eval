import hashlib
import os
import json

CACHE_DIR = "cache_llm"

def cache_result(input: str, result: dict) -> None:
    """Cache the result of the LLM call for the given input."""
    
    hash_object = hashlib.sha256(input.encode())
    hex_dig = hash_object.hexdigest()
    
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        
    with open(os.path.join(CACHE_DIR, f"{hex_dig}.json"), "w") as f:
        json.dump(result, f)
        
        
def retrieve_cached_result(input: str) -> dict | None:
    """Retrieve the cached result for the given input."""
    
    hash_object = hashlib.sha256(input.encode())
    hex_dig = hash_object.hexdigest()
    
    if not os.path.exists(CACHE_DIR):
        return None
    try:
        with open(os.path.join(CACHE_DIR, f"{hex_dig}.json"), "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None