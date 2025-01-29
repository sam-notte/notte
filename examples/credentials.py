import os
from dotenv import load_dotenv

load_dotenv()

def get_credentials():
    username = os.getenv("TWITTER_USERNAME")
    password = os.getenv("TWITTER_PASSWORD")
    
    if not username or not password:
        raise ValueError("Missing TWITTER_USERNAME or TWITTER_PASSWORD in .env file")
        
    return username, password 