from typing import Any
from .api_client import general_availability_operation, local_availability_operation, start_analyses_operation
from .compose_requests import compose_complete_requests
from .journal import Journal
from .graphql_errors import check_errors
from .parse_args import parse_args
from sgqlc.endpoint.http import HTTPEndpoint
import json

AnalysesMutationResult = Any

def start_analyses(client: HTTPEndpoint) -> AnalysesMutationResult:
    """Starts the analyses for all updated data."""
    journal = Journal.singleton()
    args = parse_args()
    # Get information about our permissions and the general availability of layers
    general_op = general_availability_operation()
    print("Checking for layers to update...")
    general_data = client(general_op)
    check_errors(general_data)
    general_availability = (general_op + general_data)

    # Get information about the availability of layers in specific areas
    local_op = local_availability_operation(general_availability)
    local_data = client(local_op)
    check_errors(local_data)
    local_availability = (local_op + local_data)

    # Start the analyses
    analysis_inputs = compose_complete_requests(general_availability, local_availability)
    if len(analysis_inputs) == 0:
        # We can only check for layer having been unpacked already.
        # So if we're here, we've already unpacked all latest layers.
        print("✅ No layers to update. Done.")
        exit(0)
    print("Starting analyses...")
    analyses_op = start_analyses_operation(analysis_inputs)
    analyses_data = client(analyses_op)
    check_errors(analyses_data)
    analyses = (analyses_op + analyses_data)

    # Add the analyses to the journal
    journal.record_analyses_requested(analyses)
    print("Analyses started.")
    
    return(analyses)