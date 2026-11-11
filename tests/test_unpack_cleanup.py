import os
from conftest import make_gpkg, make_shp
from datetime import datetime, timezone
from nefino_geosync.download_analysis import unpack_items
from nefino_geosync.journal import Journal
from shapely.geometry import box

SQUARE = [{'geom': box(0, 0, 1, 1), 'geom_id': 1}]


def test_unpacking_a_new_format_keeps_the_old_format_of_that_layer(app, tmp_path, capsys):
    app.configure(output_format='SHP')
    state_dir = app.state_dir('DE1')
    make_gpkg(os.path.join(state_dir, 'layer_a.gpkg'), SQUARE)
    make_gpkg(os.path.join(state_dir, 'layer_b.gpkg'), SQUARE)

    zip_root = tmp_path / 'zip'
    cluster = zip_root / 'cluster'
    cluster.mkdir(parents=True)
    (zip_root / 'analysis_summary.xlsx').write_bytes(b'')
    make_shp(str(cluster / 'layer_a'), SQUARE)

    journal = Journal.singleton()
    journal.analysis_states['pk1'] = 'DE1'
    journal.analysis_requested_layers['pk1'] = {'layer_a'}

    unpack_items(str(zip_root), 'pk1', datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert sorted(os.listdir(state_dir)) == [
        'layer_a.cpg',
        'layer_a.dbf',
        'layer_a.gpkg',
        'layer_a.prj',
        'layer_a.shp',
        'layer_a.shx',
        'layer_b.gpkg',
    ]
    assert 'layer_a in DE1 also has files in the GPKG format' in capsys.readouterr().out


def test_requested_layer_without_file_in_zip_keeps_its_old_files(app, tmp_path, capsys):
    state_dir = app.state_dir('DE1')
    make_gpkg(os.path.join(state_dir, 'now_empty.gpkg'), SQUARE)
    make_gpkg(os.path.join(state_dir, 'not_requested.gpkg'), SQUARE)

    zip_root = tmp_path / 'zip'
    (zip_root / 'cluster').mkdir(parents=True)
    (zip_root / 'analysis_summary.xlsx').write_bytes(b'')

    journal = Journal.singleton()
    journal.analysis_states['pk2'] = 'DE1'
    journal.analysis_requested_layers['pk2'] = {'now_empty'}

    unpack_items(str(zip_root), 'pk2', datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert sorted(os.listdir(state_dir)) == ['not_requested.gpkg', 'now_empty.gpkg']
    assert 'No file was delivered for now_empty in DE1' in capsys.readouterr().out
    assert not journal.is_newer_than_saved('now_empty', 'DE1', datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_older_analysis_does_not_replace_files_of_a_newer_one(app, tmp_path, capsys):
    state_dir = app.state_dir('DE1')
    make_gpkg(os.path.join(state_dir, 'layer_a.gpkg'), SQUARE)
    os.utime(os.path.join(state_dir, 'layer_a.gpkg'), (1_000_000_000, 1_000_000_000))

    zip_root = tmp_path / 'zip'
    (zip_root / 'cluster').mkdir(parents=True)
    (zip_root / 'analysis_summary.xlsx').write_bytes(b'')

    journal = Journal.singleton()
    journal.record_layers_unpacked({'layer_a'}, 'DE1', datetime(2026, 2, 1, tzinfo=timezone.utc))
    journal.analysis_states['pk3'] = 'DE1'
    journal.analysis_requested_layers['pk3'] = {'layer_a'}

    make_gpkg(str(zip_root / 'cluster' / 'layer_a.gpkg'), SQUARE)

    unpack_items(str(zip_root), 'pk3', datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert os.listdir(state_dir) == ['layer_a.gpkg']
    assert os.path.getmtime(os.path.join(state_dir, 'layer_a.gpkg')) == 1_000_000_000


def test_unpacking_removes_older_files_of_the_layer_the_new_delivery_does_not_have(app, tmp_path):
    app.configure(output_format='SHP')
    state_dir = app.state_dir('DE1')
    make_shp(os.path.join(state_dir, 'layer_a__50m'), SQUARE)
    make_shp(os.path.join(state_dir, 'layer_b'), SQUARE)

    zip_root = tmp_path / 'zip'
    cluster = zip_root / 'cluster'
    cluster.mkdir(parents=True)
    (zip_root / 'analysis_summary.xlsx').write_bytes(b'')
    make_shp(str(cluster / 'layer_a'), SQUARE)
    os.remove(cluster / 'layer_a.cpg')

    journal = Journal.singleton()
    journal.analysis_states['pk4'] = 'DE1'
    journal.analysis_requested_layers['pk4'] = {'layer_a'}

    unpack_items(str(zip_root), 'pk4', datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert sorted(os.listdir(state_dir)) == [
        'layer_a.dbf',
        'layer_a.prj',
        'layer_a.shp',
        'layer_a.shx',
        'layer_b.cpg',
        'layer_b.dbf',
        'layer_b.prj',
        'layer_b.shp',
        'layer_b.shx',
    ]
