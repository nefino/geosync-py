"""This module handles creating and finding directories where the app should store its files."""

import os
import platform

APP_NAME='nefino-geosync'

def get_app_directory() -> str:
    """Returns the directory where the app should store its files. 
    Creates it if it doesn't exist."""
    system = platform.system()
    
    if system == 'Windows':
        base_dir = os.path.join(os.getenv('APPDATA'), APP_NAME)
    elif system == 'Darwin':  # macOS
        base_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', APP_NAME)
    else:  # Linux and other Unix-like systems
        base_dir = os.path.join(os.path.expanduser('~'), f'.{APP_NAME}')
    
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    
    return base_dir

def get_download_directory(pk: str) -> str:
    """Returns the directory where the app should store downloaded analyses. 
    Creates it if it doesn't exist."""
    downloads_dir = os.path.join(get_app_directory(), 'downloads', pk)
    
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
    
    return downloads_dir

def get_output_path(state: str, cluster: str) -> str:
    """Returns the path to store the latest version of downloaded files."""
    output_dir = os.path.join(get_app_directory(), "newestData", state, cluster)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir