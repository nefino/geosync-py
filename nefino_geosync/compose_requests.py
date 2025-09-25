from .access_rule_filter import AccessRuleFilter
from .api_client import (
    GeneralAvailabilityResult,
    LocalAvailabilityResult,
    build_states_list,
)
from .config import Config
from .journal import Journal
from .layer_changelog import LayerChangelogResult, layer_has_relevant_changes_in_changelog
from .parse_args import parse_args
from .schema import (
    CoordinateInput,
    GeoAnalysisInput,
    GeoAnalysisLayerInput,
    GeoAnalysisObjectInput,
    GeoAnalysisOutputFormatInput,
    GeoAnalysisRequestInput,
    GeoAnalysisScopeInput,
    ScopeType,
)
from typing import Dict, List, Set

# Place analyses require a dummy coordinate. It will be ignored in calculations.
DUMMY_COORDINATE = CoordinateInput(lon=9.0, lat=52.0)
# The API requires input of combining operations, even if they are not used.
DUMMY_OPERATIONS = []


def compose_complete_requests(
    general_availability: GeneralAvailabilityResult,
    local_availability: LocalAvailabilityResult,
    changelog_result: LayerChangelogResult = None,
) -> Dict[str, GeoAnalysisInput]:
    """Use fetched data to build the complete requests for all available layers."""
    available_states = build_states_list(general_availability)

    # Log the list of available federal states
    if available_states:
        print(f'📍 Checking {len(available_states)} available federal state(s): {", ".join(sorted(available_states))}')
    else:
        print('⚠️ No federal states available for your account')
        return {}

    requests_as_tuples = [
        (state, compose_single_request(state, general_availability, local_availability, changelog_result))
        for state in available_states
    ]

    # Filter out None requests and notify user about up-to-date states
    result = {}
    for state, request in requests_as_tuples:
        if request is not None:
            result[state] = request
        else:
            print(f'✅ {state} is up-to-date')

    return result


def compose_layer_inputs(
    layers: list, local_layers: Set[str], state: str, cluster_name: str, changelog_result: LayerChangelogResult = None
) -> List[GeoAnalysisLayerInput]:
    """Build a list of layer inputs from output lists."""
    args = parse_args()
    journal = Journal.singleton()
    updated_layers = []

    print(f'  🔍 Checking layers in cluster {cluster_name} for {state}...')

    for layer in layers:
        # Check if layer should be processed
        is_available = (not layer.is_regional) or (layer.name in local_layers)
        needs_update = journal.is_newer_than_saved(layer.name, state, layer.last_update)
        has_relevant_changes = layer_has_relevant_changes_in_changelog(changelog_result, layer.name, cluster_name)

        if is_available and (needs_update or has_relevant_changes):
            updated_layers.append(layer)
            if args.verbose:
                reason = 'last update' if needs_update else 'relevant changes'
                print(f'    📄 {layer.name} needs update ({reason}: {layer.last_update})')

    if updated_layers:
        print(f'    ⚡ Found {len(updated_layers)} in cluster {cluster_name} layers to update for {state}')
    else:
        print(f'    ✅ All layers are up-to-date in cluster {cluster_name} for {state}')

    return [GeoAnalysisLayerInput(layer_name=layer.name, buffer_m=[layer.pre_buffer]) for layer in updated_layers]


def compose_single_request(
    state: str,
    general_availability: GeneralAvailabilityResult,
    local_availability: LocalAvailabilityResult,
    changelog_result: LayerChangelogResult = None,
) -> GeoAnalysisInput:
    """Build a single request for a given state."""
    print(f'🔍 Checking layers for {state}...')

    config = Config.singleton()
    rules = AccessRuleFilter(general_availability.access_rules)
    # specify the data we want to add to the analysis
    state_local_layers = {layer.name for layer in local_availability[f'regionalLayers_{state}']}

    for skip_layer in config.skip_layers:
        state_local_layers.discard(skip_layer)

    requests_as_tuples = [
        (cluster, compose_layer_inputs(cluster.layers, state_local_layers, state, cluster.name, changelog_result))
        for cluster in general_availability.clusters
        if cluster.has_access and rules.check(state, cluster.name)
    ]

    requests = [
        GeoAnalysisRequestInput(cluster_name=cluster.name, layers=layers)
        for (cluster, layers) in requests_as_tuples
        if len(layers) > 0
    ]

    if len(requests) == 0:
        return None
    # Specify the output format
    # TODO: this should be configurable
    output = GeoAnalysisOutputFormatInput(template_name='default', type=config.output_format, crs=config.crs)
    # specify where the analysis should be done
    scope = GeoAnalysisScopeInput(place=state, type=ScopeType('FEDERAL_STATE'))
    # put everything together into a specification for an analysis
    spec = GeoAnalysisObjectInput(
        coordinate=DUMMY_COORDINATE,
        output=output,
        scope=scope,
        requests=requests,
        operations=DUMMY_OPERATIONS,
    )
    return GeoAnalysisInput(name=f'sync_{state}', specs=spec)
