"""This is the main entry point of the application."""

import atexit
import os
from .api_client import get_client
from .config import Config
from .download_completed_analyses import download_completed_analyses
from .layer_changelog import (
    record_layer_changes_since_last_run,
    record_successful_geosync_completion,
)
from .parse_args import parse_args
from .session_logger import start_session_logging, stop_session_logging
from .start_analyses import start_analyses
from datetime import UTC, datetime


def main() -> None:
    # Start session-wide logging
    print('Starting Nefino GeoSync...')
    start_session_logging()
    start_time = datetime.now(tz=UTC)
    # Ensure logging stops when the program exits
    atexit.register(stop_session_logging)

    try:
        args = parse_args()

        if args.configure:
            config = Config.singleton()
            # if you are running with --configure on the first run (you don't need to)
            # you will be prompted to configure the app by the config singleton init.
            # In that case, don't prompt the user again.
            if not config.already_prompted:
                config.run_config_prompts()

        client = get_client(api_host=os.getenv('NEFINO_API_HOST', default='https://api.nefino.li'))

        # Check for layer changes since last run before starting new analyses
        changelog_result = record_layer_changes_since_last_run(client)

        if not args.resume:
            start_analyses(client, changelog_result)
        else:
            download_completed_analyses(client)

        # Record successful completion
        record_successful_geosync_completion(start_time)

    except Exception as e:
        print(f'Fatal error: {e}')
        raise
    finally:
        # Ensure logging stops even if there's an error
        stop_session_logging()


if __name__ == '__main__':
    main()
