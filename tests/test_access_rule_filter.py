from nefino_geosync.access_rule_filter import accessible_layers
from types import SimpleNamespace as NS


def test_accessible_layers_follow_cluster_rules_and_regional_availability():
    general = NS(
        allowed_analysis_areas=NS(all_areas_enabled=True, enabled_states=[]),
        access_rules=[NS(all_clusters_enabled=False, clusters=['wind', 'aviation'], places=['DE5', 'DE9'])],
        clusters=[
            NS(name='wind', has_access=True, layers=[NS(name='wind_speeds_150', is_regional=False), NS(name='regional_plan', is_regional=True)]),
            NS(name='aviation', has_access=False, layers=[NS(name='aerodrome', is_regional=False)]),
            NS(name='solar', has_access=True, layers=[NS(name='solar_potential', is_regional=False)]),
        ],
    )
    states = [f'DE{i}' for i in '123456789ABCDEFG']
    local = {f'regionalLayers_{state}': [NS(name='regional_plan')] if state == 'DE9' else [] for state in states}

    assert accessible_layers(general, local) == {
        'DE5': {'wind_speeds_150'},
        'DE9': {'wind_speeds_150', 'regional_plan'},
    }
