"""This is the main entry point of the application."""

import atexit
import os
from .access_rule_filter import accessible_layers
from .api_client import fetch_general_availability, fetch_local_availability, get_client
from .config import Config, join_enabled
from .download_completed_analyses import download_completed_analyses
from .layer_changelog import (
    record_layer_changes_since_last_run,
    record_successful_geosync_completion,
)
from .local_file_check import mark_outdated_local_files
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

        try:
            general_availability = fetch_general_availability(client)
            local_availability = fetch_local_availability(client, general_availability)
            accessible = accessible_layers(general_availability, local_availability)
        except Exception as e:
            if not args.resume:  # starting analyses needs the availability
                raise
            # resuming only downloads finished analyses, so it must not fail because of the availability
            print(f'⚠️  Fetching the layer availability failed, skipping the file check and joining: {e}')
            general_availability = local_availability = accessible = None

        # Check for layer changes since last run before starting new analyses
        changelog_result = record_layer_changes_since_last_run(client, general_availability)

        # Re-download files that do not match the configuration (CRS, output format, missing geom_id).
        # Resuming starts no analyses, so the check is left to the next regular run.
        if accessible is not None and not args.resume:
            try:
                mark_outdated_local_files(accessible)
            except Exception as e:  # a problem with the local files must not stop the sync itself
                print(f'⚠️  Checking the downloaded files failed: {e}')

        nothing_to_update = False
        if not args.resume:
            nothing_to_update = (
                start_analyses(client, changelog_result, general_availability, local_availability) is None
            )
        else:
            download_completed_analyses(client)

        if join_enabled() and accessible is not None:
            try:
                from .join import join_all_layers  # only loaded when joining is enabled

                join_all_layers(accessible)
            except Exception as e:  # joining must never make the sync itself fail
                print(f'⚠️  Joining layers failed: {e}')

        if not nothing_to_update:
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
