from typing import Any
from .api_client import general_availability_operation, local_availability_operation, start_analyses_operation
from .compose_requests import compose_complete_requests
from .journal import Journal
from sgqlc.endpoint.http import HTTPEndpoint

AnalysesMutationResult = Any

def start_analyses(client: HTTPEndpoint) -> AnalysesMutationResult:
    """Starts the analyses for all updated data."""
    journal = Journal.singleton()
    # Get information about our permissions and the general availability of layers
    general_op = general_availability_operation()
    general_data = client(general_op)
    if ('errors' in general_data):
        raise Exception(f"Error in general availability operation: {general_data['errors']}")
    general_availability = (general_op + general_data)

    # Get information about the availability of layers in specific areas
    local_op = local_availability_operation(general_availability)
    local_data = client(local_op)
    local_availability = (local_op + local_data)

    # Start the analyses
    analysis_inputs = compose_complete_requests(general_availability, local_availability)
    # TODO: bail out if there are no analyses to start
    analyses_op = start_analyses_operation(analysis_inputs)
    analyses_data = client(analyses_op)
    if 'errors' in analyses_data:
        print(f"Error in starting analyses: {analyses_data['errors']}")
    analyses = (analyses_op + analyses_data)

    # Add the analyses to the journal
    journal.record_analyses_requested(analyses)
    
    return(analyses)