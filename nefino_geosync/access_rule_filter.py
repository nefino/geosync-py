from .api_client import build_states_list
from typing import Dict, Set


class AccessRuleFilter:
    def __init__(self, access_rules):
        self.access_rules = access_rules

    def check(self, place, cluster):
        for access_rule in self.access_rules:
            if place in access_rule.places:
                if access_rule.all_clusters_enabled or cluster in access_rule.clusters:
                    return True
        return False


def accessible_clusters(general_availability, state: str) -> list:
    """Returns the clusters the account may download in the given state."""
    rules = AccessRuleFilter(general_availability.access_rules)
    return [c for c in general_availability.clusters if c.has_access and rules.check(state, c.name)]


def regional_layer_names(local_availability, state: str) -> Set[str]:
    """Returns the names of the regional layers that are available in the given state."""
    return {layer.name for layer in local_availability[f'regionalLayers_{state}']}


def is_layer_available(layer, regional_layers: Set[str]) -> bool:
    """Regional layers are only available in states where they exist; all other layers everywhere."""
    return not layer.is_regional or layer.name in regional_layers


def accessible_layers(general_availability, local_availability) -> Dict[str, Set[str]]:
    """Returns {state: layer names} the account can currently download, using the same rules as the requests."""
    accessible: Dict[str, Set[str]] = {}
    for state in build_states_list(general_availability):
        regional = regional_layer_names(local_availability, state)
        for cluster in accessible_clusters(general_availability, state):
            accessible.setdefault(state, set()).update(
                layer.name for layer in cluster.layers if is_layer_available(layer, regional)
            )
    return accessible
