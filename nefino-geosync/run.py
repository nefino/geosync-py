"""This is the main entry point of the application."""
import os
from .api_client import get_client
from .start_analyses import start_analyses
from .download_completed_analyses import download_completed_analyses
from .config import Config
from .parse_args import parse_args

def main():
    args = parse_args()

    if args.configure:
        config = Config.singleton()
        # if you are running with --configure on the first run (you don't need to)
        # you will be prompted to configure the app by the config singleton init.
        # In that case, don't prompt the user again.
        if not config.already_prompted:
            config.run_config_prompts()

    client = get_client(api_host=os.getenv("NEFINO_API_HOST", default="https://api.nefino.li"))

    if not args.resume:
        start_analyses(client)
    else:
        download_completed_analyses(client)

if __name__ == "__main__":
    main()