from .api_client import (
    GeneralAvailabilityResult,
    LocalAvailabilityResult,
    start_analyses_operation,
)
from .compose_requests import compose_complete_requests
from .download_completed_analyses import download_completed_analyses
from .graphql_errors import check_errors
from .journal import Journal
from .layer_changelog import LayerChangelogResult
from .parse_args import parse_args
from sgqlc.endpoint.http import HTTPEndpoint
from typing import Any

AnalysesMutationResult = Any


def start_analyses(
    client: HTTPEndpoint,
    changelog_result: LayerChangelogResult,
    general_availability: GeneralAvailabilityResult,
    local_availability: LocalAvailabilityResult,
) -> AnalysesMutationResult:
    """Starts the analyses for all updated data. Returns None if there was nothing to update."""
    journal = Journal.singleton()
    parse_args()
    print('Checking for layers to update...')
    # Clear previous analysis requested layers
    journal.clear_analysis_requested_layers()
    # Start the analyses
    analysis_inputs = compose_complete_requests(general_availability, local_availability, changelog_result)
    if len(analysis_inputs) == 0:
        # We can only check for layer having been unpacked already.
        # So if we're here, we've already unpacked all latest layers.
        print('✅ No layers to update.')
        return None
    for federal_state_key in analysis_inputs:
        print(f'Starting analysis for {federal_state_key}')
        analyses_op = start_analyses_operation({federal_state_key: analysis_inputs[federal_state_key]})
        print(f'Started analysis for {federal_state_key}. Waiting for completion...')
        analyses_data = client(analyses_op)
        check_errors(analyses_data, f'Failed to start analysis for {federal_state_key}')
        analyses = analyses_op + analyses_data

        # Add the analyses to the journal
        journal.record_analyses_requested(analyses, analysis_inputs)
        print(f'Analysis for {federal_state_key} finished')
        download_completed_analyses(client)

    return analyses
