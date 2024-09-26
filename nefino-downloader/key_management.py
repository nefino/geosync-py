import os
from .storage import get_app_directory


def get_api_key() -> str:
    """Returns the API key stored in the app's directory. 
    Asks the user for the key and saves it if it doesn't exist."""
    key_file = os.path.join(get_app_directory(), 'api_key.txt')
    
    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            key = f.read()
            return key
    else:
        key = input('Enter your API key:\n')
        with open(key_file, 'w') as f:
            f.write(key)
        return key

def reset_api_key():
    """Deletes the API key stored in the app's directory 
    to allow the user to enter a new one."""
    key_file = os.path.join(get_app_directory(), 'api_key.txt')
    
    if os.path.exists(key_file):
        os.remove(key_file)