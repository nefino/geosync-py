from typing import Dict, List, Set 
from .schema import CoordinateInput, GeoAnalysisInput, GeoAnalysisLayerInput, GeoAnalysisObjectInput, GeoAnalysisOutputFormatInput, GeoAnalysisRequestInput, GeoAnalysisScopeInput, ScopeType
from .api_client import GeneralAvailabilityResult, LocalAvailabilityResult, build_states_list
from .journal import Journal
from .config import Config

# Place analyses require a dummy coordinate. It will be ignored in calculations.
DUMMY_COORDINATE = CoordinateInput(lon=9.0, lat=52.0)
# The API requires input of combining operations, even if they are not used.
DUMMY_OPERATIONS = []

def compose_complete_requests(general_availability: GeneralAvailabilityResult,
                              local_availability: LocalAvailabilityResult
                              ) -> Dict[str, GeoAnalysisInput]:
    """Use fetched data to build the complete requests for all available layers."""
    available_states = build_states_list(general_availability)
    return {state: request for (state, request) in
            ((state, compose_single_request(state, general_availability, 
                                            local_availability)) 
              for state in available_states)
              if request is not None}

def compose_layer_inputs(layers: list, local_layers: Set[str], state: str) -> List[GeoAnalysisLayerInput]:
    """Build a list of layer inputs from output lists."""
    journal = Journal.singleton()
    return [GeoAnalysisLayerInput(layer_name=layer['name'], 
                                  buffer_m=[layer['pre_buffer']]) 
            for layer in layers 
            if ((not layer.is_regional) or (layer.name in local_layers)) 
            and journal.is_newer_than_saved(layer.name, state, layer.last_update)]

def compose_single_request(state: str,
                           general_availability: GeneralAvailabilityResult,
                           local_availability: LocalAvailabilityResult
                           ) -> GeoAnalysisInput:
    """Build a single request for a given state."""
    config = Config.singleton()
    # specify the data we want to add to the analysis
    state_local_layers = {layer.name for layer in 
                          local_availability[f'regionalLayers_{state}']}

    for skip_layer in config.skip_layers:
        state_local_layers.discard(skip_layer)

    requests =[GeoAnalysisRequestInput(cluster_name=cluster.name, layers=layers)
               for (cluster, layers) in 
               [(cluster, 
                 compose_layer_inputs(cluster.layers, state_local_layers, state)) 
                 for cluster in general_availability.clusters 
                 if cluster.has_access]
                  if len(layers) > 0]
    if len(requests) == 0:
        return None
    # Specify the output format
    # TODO: this should be configurable
    output = GeoAnalysisOutputFormatInput(template_name='default', 
                                          type=config.output_format,
                                          crs=config.crs)
    # specify where the analysis should be done
    scope = GeoAnalysisScopeInput(place=state, type=ScopeType('FEDERAL_STATE'))
    # put everything together into a specification for an analysis
    spec = GeoAnalysisObjectInput(coordinate=DUMMY_COORDINATE, 
                                  output=output, 
                                  scope=scope, 
                                  requests=requests, 
                                  operations=DUMMY_OPERATIONS)
    return GeoAnalysisInput(name=f'sync_{state}', specs=[spec])