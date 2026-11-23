import logging
from .api_client import (
    GeneralAvailabilityResult,
    LocalAvailabilityResult,
    fetch_analyses,
    start_analyses_operation,
)
from .compose_requests import compose_complete_requests
from .download_completed_analyses import download_completed_analyses
from .graphql_errors import check_errors
from .journal import Journal
from .layer_changelog import LayerChangelogResult
from .options import get_options
from sgqlc.endpoint.http import HTTPEndpoint
from typing import Any

log = logging.getLogger(__name__)

AnalysesMutationResult = Any


def start_analyses(
    client: HTTPEndpoint,
    changelog_result: LayerChangelogResult,
    general_availability: GeneralAvailabilityResult,
    local_availability: LocalAvailabilityResult,
) -> AnalysesMutationResult:
    """Starts the analyses for all updated data. Returns None if there was nothing to update."""
    journal = Journal.singleton()
    options = get_options()
    log.info('Checking for layers to update...')
    # Clear the requested layers of previous runs, except for analyses that are still to be downloaded
    unfinished_analyses = journal.get_unfinished_analyses(fetch_analyses(client))
    journal.clear_analysis_requested_layers(keep=set(unfinished_analyses))
    # Start the analyses
    analysis_inputs = compose_complete_requests(general_availability, local_availability, changelog_result)
    if not options.wait:
        # Without waiting, earlier analyses may still be running: do not start a second one for the same state
        for state in sorted(set(unfinished_analyses.values()) & set(analysis_inputs)):
            pks = [pk for pk, pk_state in unfinished_analyses.items() if pk_state == state]
            log.info(f'⏳ Skipping {state}: analyses {", ".join(pks)} have not been downloaded yet')
            del analysis_inputs[state]
    if len(analysis_inputs) == 0:
        # We can only check for layer having been unpacked already.
        # So if we're here, we've already unpacked all latest layers.
        log.info('✅ No layers to update.')
        return None
    for federal_state_key in analysis_inputs:
        log.info(f'Starting analysis for {federal_state_key}')
        analyses_op = start_analyses_operation({federal_state_key: analysis_inputs[federal_state_key]})
        if options.wait:
            log.info(f'Started analysis for {federal_state_key}. Waiting for completion...')
        analyses_data = client(analyses_op)
        check_errors(analyses_data, f'Failed to start analysis for {federal_state_key}')
        analyses = analyses_op + analyses_data

        # Add the analyses to the journal
        journal.record_analyses_requested(analyses, analysis_inputs)
        if options.wait:
            log.info(f'Analysis for {federal_state_key} finished')
            download_completed_analyses(client)
        else:
            log.info(f'Started analysis for {federal_state_key}')

    return analyses
