import sys
from .api_client import (
    general_availability_operation,
    local_availability_operation,
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


def start_analyses(client: HTTPEndpoint, changelog_result: LayerChangelogResult = None) -> AnalysesMutationResult:
    """Starts the analyses for all updated data."""
    journal = Journal.singleton()
    parse_args()
    # Get information about our permissions and the general availability of layers
    general_op = general_availability_operation()
    print('Checking for layers to update...')
    general_data = client(general_op)
    check_errors(general_data, 'Failed to fetch general layer availability')
    general_availability = general_op + general_data

    # Get information about the availability of layers in specific areas
    local_op = local_availability_operation(general_availability)
    local_data = client(local_op)
    check_errors(local_data, 'Failed to fetch regional layer availability')
    local_availability = local_op + local_data
    # Clear previous analysis requested layers
    journal.clear_analysis_requested_layers()
    # Start the analyses
    analysis_inputs = compose_complete_requests(general_availability, local_availability, changelog_result)
    if len(analysis_inputs) == 0:
        # We can only check for layer having been unpacked already.
        # So if we're here, we've already unpacked all latest layers.
        print('✅ No layers to update. Done.')
        sys.exit(0)
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
