"""This is the main entry point of the application."""
from .api_client import get_client
from .start_analyses import start_analyses
from .download_completed_analyses import download_completed_analyses
from .config import Config

config = Config.singleton()
config.run_config_prompts()
exit(0)
client = get_client(api_host="http://api.nefino.local")
start_analyses(client)
download_completed_analyses(client)