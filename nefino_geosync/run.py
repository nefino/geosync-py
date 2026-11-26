"""This is the main entry point of the application."""

import atexit
import dataclasses
import logging
import os
import sys
from .access_rule_filter import accessible_layers
from .api_client import fetch_analyses, fetch_general_availability, fetch_local_availability, get_client
from .config import Config, join_enabled
from .download_completed_analyses import download_completed_analyses
from .journal import Journal
from .layer_changelog import (
    record_layer_changes_since_last_run,
    record_successful_geosync_completion,
)
from .local_file_check import mark_outdated_local_files
from .options import AnalysisInfo, SyncOptions, SyncResult, set_options
from .parse_args import parse_args
from .schema import Status
from .session_logger import start_session_logging, stop_session_logging
from .start_analyses import download_unfinished_analyses, start_analyses
from datetime import UTC, datetime
from sgqlc.endpoint.http import HTTPEndpoint
from typing import Optional, Set, Tuple

log = logging.getLogger(__name__)


def sync(options: Optional[SyncOptions] = None) -> SyncResult:
    """Starts analyses for updated layers and downloads finished ones, as configured by the options.

    Call it to run Nefino GeoSync from Python, e.g. in an automated job with SyncOptions(wait=False): one run
    starts the analyses, a later run with resume=True downloads them. It always runs non-interactively: it never
    prompts and raises errors instead of exiting, so it needs an existing configuration. Logging is left to the
    caller.
    """
    options = dataclasses.replace(options or SyncOptions(), interactive=False)
    client, known_analyses, synced_analyses, tracked = _run(options)
    return summarize(client, known_analyses, synced_analyses, tracked)


def _run(options: SyncOptions) -> Tuple[HTTPEndpoint, Set[str], Set[str], Set[str]]:
    """Runs the sync. Returns the client, and the known analyses, synced analyses and analyses with requested
    layers from before the run."""
    set_options(options)
    # the configuration and the journal are read from the app directory of these options
    Config._instance = None
    Journal._instance = None
    start_time = datetime.now(tz=UTC)

    if options.configure:
        if not options.interactive:
            raise ValueError('The configuration wizard cannot run non-interactively')
        config = Config.singleton()
        # if you are running with --configure on the first run (you don't need to)
        # you will be prompted to configure the app by the config singleton init.
        # In that case, don't prompt the user again.
        if not config.already_prompted:
            config.run_config_prompts()

    client = get_client(api_host=os.getenv('NEFINO_API_HOST', default='https://api.nefino.li'))
    journal = Journal.singleton()
    known_analyses = set(journal.analysis_states)
    synced_analyses = set(journal.synced_analyses)
    tracked = set(journal.analysis_requested_layers)

    try:
        general_availability = fetch_general_availability(client)
        local_availability = fetch_local_availability(client, general_availability)
        accessible = accessible_layers(general_availability, local_availability)
    except Exception as e:
        if not options.resume:  # starting analyses needs the availability
            raise
        # resuming only downloads finished analyses, so it must not fail because of the availability
        log.warning(f'⚠️  Fetching the layer availability failed, skipping the file check and joining: {e}')
        general_availability = local_availability = accessible = None

    # Check for layer changes since last run before starting new analyses
    record_layer_changes_since_last_run(client, general_availability)

    if options.resume:
        download_completed_analyses(client)
    else:
        # Download the analyses of earlier runs before the file check, which must see their files
        download_unfinished_analyses(client)

    # Re-download files that do not match the configuration (CRS, output format, missing geom_id).
    # Resuming starts no analyses, so the check is left to the next regular run.
    if accessible is not None and not options.resume:
        try:
            mark_outdated_local_files(accessible)
        except Exception as e:  # a problem with the local files must not stop the sync itself
            log.warning(f'⚠️  Checking the downloaded files failed: {e}')

    nothing_to_update = False
    if not options.resume:
        nothing_to_update = start_analyses(client, general_availability, local_availability) is None

    if join_enabled() and accessible is not None:
        try:
            from .join import join_all_layers  # only loaded when joining is enabled

            join_all_layers(accessible)
        except Exception as e:  # joining must never make the sync itself fail
            log.warning(f'⚠️  Joining layers failed: {e}')

    if not nothing_to_update:
        # Record successful completion
        record_successful_geosync_completion(start_time)

    return client, known_analyses, synced_analyses, tracked


def summarize(
    client: HTTPEndpoint, known_analyses: Set[str], synced_analyses: Set[str], tracked: Set[str]
) -> SyncResult:
    """Summarizes the analyses of this run, given the known analyses, synced analyses and analyses with requested
    layers from before the run. Analyses of earlier runs whose requested layers were cleared are left out."""
    journal = Journal.singleton()
    result = SyncResult()
    for analysis in fetch_analyses(client):
        if analysis.pk not in journal.analysis_states:
            continue
        in_this_run = (
            analysis.pk in tracked
            or analysis.pk in journal.analysis_requested_layers
            or analysis.pk not in known_analyses  # started in this run
        )
        if not in_this_run:
            continue
        info = AnalysisInfo(analysis.pk, journal.analysis_states[analysis.pk], analysis.started_at)
        if analysis.pk not in known_analyses:
            result.started.append(info)
        if analysis.pk in journal.synced_analyses:
            if analysis.pk not in synced_analyses:
                result.downloaded.append(info)
        elif analysis.status == Status('ERROR'):
            result.failed.append(info)
        else:
            result.pending.append(info)
    return result


class ConsoleHandler(logging.StreamHandler):
    """Writes log messages to the current sys.stdout, which the session logging may replace."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


def main() -> None:
    options = parse_args()
    set_options(options)  # the session log is written to the app directory of these options
    # Start session-wide logging
    print('Starting Nefino GeoSync...')
    start_session_logging()
    # Ensure logging stops when the program exits
    atexit.register(stop_session_logging)

    handler = ConsoleHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    package_logger = logging.getLogger('nefino_geosync')
    package_logger.addHandler(handler)
    package_logger.setLevel(logging.INFO)

    try:
        # not sync(): the command line may prompt, and sends no summary request
        _run(options)
    except Exception as e:
        log.error(f'Fatal error: {e}')
        raise
    finally:
        # Ensure logging stops even if there's an error
        stop_session_logging()


if __name__ == '__main__':
    main()
