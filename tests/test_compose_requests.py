from datetime import datetime, timezone
from nefino_geosync.compose_requests import compose_layer_inputs
from types import SimpleNamespace


def layer(name, is_regional=False):
    return SimpleNamespace(name=name, is_regional=is_regional, last_update=datetime(2026, 1, 1, tzinfo=timezone.utc), pre_buffer=0)


def test_skip_layers_apply_to_regular_and_regional_layers(app):
    app.configure(skip_layers=['wind_speeds_150', ' regional_skipped'])
    layers = [layer('wind_speeds_150'), layer('aerodrome'), layer('regional_skipped', True), layer('regional_kept', True)]

    inputs = compose_layer_inputs(layers, {'regional_skipped', 'regional_kept'}, 'DE5', 'wind')

    assert [i.layer_name for i in inputs] == ['aerodrome', 'regional_kept']
