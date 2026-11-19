import os
from conftest import make_gpkg, make_shp
from datetime import datetime, timezone
from nefino_geosync.journal import Journal
from nefino_geosync.local_file_check import mark_outdated_local_files
from shapely.geometry import box

UPDATED = datetime(2026, 1, 1, tzinfo=timezone.utc)
SQUARE = [{'geom': box(0, 0, 1, 1), 'geom_id': 1}]


def record(states, layer='layer_a'):
    journal = Journal.singleton()
    journal.layer_last_updates[layer] = {state: UPDATED for state in states}
    journal.save_layer_last_updates()
    return journal


def setup_gpkg_states(app):
    make_gpkg(os.path.join(app.state_dir('DE1'), 'layer_a.gpkg'), SQUARE, srs=25832)  # fine
    make_gpkg(os.path.join(app.state_dir('DE2'), 'layer_a.gpkg'), SQUARE, srs=25833)  # wrong CRS
    make_shp(os.path.join(app.state_dir('DE3'), 'layer_a'), SQUARE)  # wrong format
    make_gpkg(os.path.join(app.state_dir('DE4'), 'layer_a.gpkg'), SQUARE, columns={'name': 'TEXT'})  # no geom_id
    app.state_dir('DE5')  # empty layer: recorded as updated, but no file
    return record(['DE1', 'DE2', 'DE3', 'DE4', 'DE5'])


ALL = {state: {'layer_a'} for state in ('DE1', 'DE2', 'DE3', 'DE4', 'DE5')}


def test_marks_wrong_crs_and_format_as_outdated(app):
    journal = setup_gpkg_states(app)

    mark_outdated_local_files(ALL)

    assert sorted(journal.layer_last_updates['layer_a']) == ['DE1', 'DE4', 'DE5']


def test_marks_missing_geom_id_only_when_joining(app):
    app.args(join=True)
    journal = setup_gpkg_states(app)

    mark_outdated_local_files(ALL)

    assert sorted(journal.layer_last_updates['layer_a']) == ['DE1', 'DE5']


def test_ignores_states_without_access(app):
    journal = setup_gpkg_states(app)

    mark_outdated_local_files({'DE1': {'layer_a'}, 'DE3': {'layer_a'}})

    # DE2 (wrong CRS) cannot be downloaded again, so it stays as it is
    assert sorted(journal.layer_last_updates['layer_a']) == ['DE1', 'DE2', 'DE4', 'DE5']


def test_shapefile_crs_is_read_from_prj(app):
    app.configure(output_format='SHP')
    make_shp(os.path.join(app.state_dir('DE1'), 'layer_a'), SQUARE, crs='EPSG_25832')
    make_shp(os.path.join(app.state_dir('DE2'), 'layer_a'), SQUARE, crs='EPSG_25833')
    make_gpkg(os.path.join(app.state_dir('DE3'), 'layer_a.gpkg'), SQUARE)
    journal = record(['DE1', 'DE2', 'DE3'])

    mark_outdated_local_files(ALL)

    assert sorted(journal.layer_last_updates['layer_a']) == ['DE1']
