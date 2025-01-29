from typing import TypedDict
import json
class Credentials(TypedDict):
    username: str
    password: str

def get_credentials_for_domain(url: str | None) -> tuple[str | None, str | None]:
    """Get credentials for a given domain from environment variables."""
    if not url:
        return None, None
        
    from urllib.parse import urlparse
    import os
    
    with open('examples/vault.json', 'r') as f:
        CREDENTIALS_MAP = json.load(f)

        if url not in CREDENTIALS_MAP:
            return None, None
            
        creds = CREDENTIALS_MAP[url]
        username = creds["username"]
        password = creds["password"]
    
    return username, password