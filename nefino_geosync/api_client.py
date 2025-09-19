"""This module handles the API client for the Nefino API.
If you want to use the Nefino API for something other than fetching the latest geodata,
you can use this client to interact with the API directly.
"""

from .config import Config
from .schema import GeoAnalysisInput, PlaceTypeGeo, schema
from sgqlc.endpoint.http import HTTPEndpoint
from sgqlc.operation import Operation
from typing import Any, Dict, List


def get_client(api_host: str = 'https://api.nefino.li') -> HTTPEndpoint:
    """Returns an HTTP client for the Nefino API."""
    headers = {'Authorization': Config.singleton().api_key}
    return HTTPEndpoint(f'{api_host}/external', headers)


def general_availability_operation() -> Operation:
    """Returns the general availability of layers and access permissions from Nefino API."""
    operation = Operation(schema.Query)
    analysis_areas = operation.allowed_analysis_areas()
    analysis_areas.all_areas_enabled()
    analysis_areas.enabled_states().place_id()

    access_rules = operation.access_rules()
    access_rules.all_clusters_enabled()
    access_rules.clusters()
    access_rules.places()

    clusters = operation.clusters()
    clusters.name()
    clusters.has_access()
    layers = clusters.layers()
    layers.name()
    layers.last_update()
    layers.is_regional()
    layers.pre_buffer()
    return operation


# any is the most specific type we can write for the results from the availability query
# this is a limitation of sgqlc types
# GitHub issue: https://github.com/profusion/sgqlc/issues/129
GeneralAvailabilityResult = Any
LocalAvailabilityResult = Any


def local_availability_operation(
    availability_result: GeneralAvailabilityResult,
) -> Operation:
    """Builds an operation to determine location-specific details of all layers."""
    operation = Operation(schema.Query)
    for state in build_states_list(availability_result):
        regional_layers = operation.regional_layers(
            # if you request the same field multiple times with different arguments,
            # you need to give each copy a unique alias
            __alias__=f'regionalLayers_{state}',
            place_id=state,
            place_type=PlaceTypeGeo('FEDERAL_STATE_GEO'),
        )
        regional_layers.name()
        regional_layers.last_update()
    return operation


def build_states_list(availability_result: GeneralAvailabilityResult) -> List[str]:
    """Returns a list of states from the availability result."""
    if availability_result.allowed_analysis_areas is None:
        return []
    if availability_result.allowed_analysis_areas.all_areas_enabled:
        # DE1 to DEG are the place_ids for the German states (EU scheme)
        return [f'DE{i}' for i in list('123456789ABCDEFG')]
    return [state.place_id for state in availability_result.allowed_analysis_areas.enabled_states]


def start_analyses_operation(inputs: Dict[str, GeoAnalysisInput]) -> Operation:
    """Builds an operation to start analyses with the given inputs."""
    operation = Operation(schema.Mutation)
    for state, input_data in inputs.items():
        start_analysis = operation.start_analysis(inputs=input_data, __alias__=f'startAnalysis_{state}')
        start_analysis.pk()
        start_analysis.status()
        start_analysis.url()
    return operation


def get_analyses_operation() -> Operation:
    """Builds an operation to get all analyses."""
    operation = Operation(schema.Query)
    analyses = operation.analysis_metadata()
    analyses.pk()
    analyses.status()
    analyses.url()
    analyses.started_at()
    return operation


def layer_changelog_operation(timestamp_start: str = None) -> Operation:
    """Builds an operation to get layer changelog entries."""
    operation = Operation(schema.Query)

    # Build the input object for the changelog query
    changelog_input = {}
    if timestamp_start:
        changelog_input['timestampStart'] = timestamp_start

    changelog = operation.layer_changelog(inputs=changelog_input)
    changelog.layer_name()
    changelog.timestamp()
    changelog.action()
    changelog.changed_fields()
    changelog.attributes()
    changelog.layer_id()
    changelog.last_update()
    changelog.cluster_name()
    changelog.cluster_id()

    return operation
