import json
import os
import sys
from conftest import make_gpkg, make_shp, read_gpkg
from nefino_geosync import join
from shapely.geometry import box


def setup_states(app, states=('DE1', 'DE2')):
    for i, state in enumerate(states):
        make_gpkg(os.path.join(app.state_dir(state), 'layer_a.gpkg'), [{'geom': box(i, 0, i + 1, 1), 'geom_id': i}])


def access(*states, layers=('layer_a', 'layer_b')):
    return {state: set(layers) for state in states}


def joined_path(app, name='layer_a.gpkg'):
    return os.path.join(app.output_path, 'joined', name)


def test_joins_once_and_rebuilds_only_when_a_state_changes(app):
    accessible = access('DE1', 'DE2')
    setup_states(app)

    join.join_all_layers(accessible)
    assert len(read_gpkg(joined_path(app))[1]) == 2
    with open(os.path.join(app.output_path, 'joined', join.STATE_FILE_NAME)) as f:
        assert json.load(f)['layer_a']['files'] == {'DE1': 'layer_a.gpkg', 'DE2': 'layer_a.gpkg'}

    # nothing changed -> not rebuilt
    os.utime(joined_path(app), (1_000_000_000, 1_000_000_000))
    for state in ('DE1', 'DE2'):
        os.utime(os.path.join(app.output_path, state, 'layer_a.gpkg'), (900_000_000, 900_000_000))
    join.join_all_layers(accessible)
    assert os.path.getmtime(joined_path(app)) == 1_000_000_000

    # a state file is newer -> rebuilt
    os.utime(os.path.join(app.output_path, 'DE2', 'layer_a.gpkg'), (1_100_000_000, 1_100_000_000))
    join.join_all_layers(accessible)
    assert os.path.getmtime(joined_path(app)) > 1_000_000_000


def test_only_accessible_states_are_joined(app):
    setup_states(app, ('DE1', 'DE2', 'DE3'))
    accessible = access('DE1', 'DE2', 'DE3')
    join.join_all_layers(accessible)
    assert len(read_gpkg(joined_path(app))[1]) == 3

    accessible = access('DE1', 'DE3')
    join.join_all_layers(accessible)
    assert sorted(r['geom_id'] for r in read_gpkg(joined_path(app))[1]) == [0, 2]

    # access rules can also limit single clusters (and thereby layers) to some states
    accessible = {'DE1': {'layer_a'}, 'DE2': {'layer_b'}, 'DE3': {'layer_a'}}
    join.join_all_layers(accessible)
    assert sorted(r['geom_id'] for r in read_gpkg(joined_path(app))[1]) == [0, 2]


def test_missing_shapely_prints_install_hint(app, monkeypatch, capsys):
    import nefino_geosync

    monkeypatch.setitem(sys.modules, 'nefino_geosync.fuse', None)  # simulates shapely not being installed
    monkeypatch.delattr(nefino_geosync, 'fuse', raising=False)
    setup_states(app)

    join.join_all_layers(access('DE1', 'DE2'))

    assert 'pip install "nefino-geosync[join]"' in capsys.readouterr().out
    assert not os.path.exists(joined_path(app))


def test_format_change_keeps_old_joined_files_and_removes_temp_files(app):
    accessible = access('DE1', 'DE2')
    setup_states(app)
    join.join_all_layers(accessible)
    assert os.path.exists(joined_path(app))

    app.configure(output_format='SHP')
    for state in ('DE1', 'DE2'):
        make_shp(os.path.join(app.state_dir(state), 'layer_a'), [{'geom': box(0, 0, 1, 1), 'geom_id': 1}])
    leftover = os.path.join(app.output_path, 'joined', join.TMP_PREFIX + 'layer_a.shp')
    open(leftover, 'w').close()

    join.join_all_layers(accessible)

    assert not os.path.exists(leftover)
    assert sorted(f for f in os.listdir(os.path.join(app.output_path, 'joined')) if not f.startswith('.')) == [
        'layer_a.cpg',
        'layer_a.dbf',
        'layer_a.gpkg',
        'layer_a.prj',
        'layer_a.shp',
        'layer_a.shx',
    ]


def test_problem_with_one_layer_does_not_stop_the_others(app, capsys):
    accessible = access('DE1', 'DE2')
    setup_states(app)
    make_gpkg(os.path.join(app.state_dir('DE1'), 'layer_b.gpkg'), [{'geom': box(0, 0, 1, 1), 'geom_id': 1}], srs=25832)
    make_gpkg(os.path.join(app.state_dir('DE2'), 'layer_b.gpkg'), [{'geom': box(0, 0, 1, 1), 'geom_id': 1}], srs=25833)

    join.join_all_layers(accessible)

    output = capsys.readouterr().out
    assert 'Skipped joining layer_b' in output
    assert os.path.exists(joined_path(app))
    assert not os.path.exists(joined_path(app, 'layer_b.gpkg'))


def test_skipping_a_previously_joined_layer_keeps_its_file_and_retries(app, capsys):
    accessible = access('DE1', 'DE2')
    setup_states(app)
    join.join_all_layers(accessible)
    assert os.path.exists(joined_path(app))

    # DE2 now has a different CRS (e.g. only partly re-downloaded after a CRS change)
    os.remove(os.path.join(app.state_dir('DE2'), 'layer_a.gpkg'))
    make_gpkg(os.path.join(app.state_dir('DE2'), 'layer_a.gpkg'), [{'geom': box(0, 0, 1, 1), 'geom_id': 1}], srs=25833)
    join.join_all_layers(accessible)

    assert 'The existing joined file was kept' in capsys.readouterr().out
    assert len(read_gpkg(joined_path(app))[1]) == 2

    # tried again in the next run, even though no per-state file changed since
    os.remove(os.path.join(app.state_dir('DE2'), 'layer_a.gpkg'))
    make_gpkg(os.path.join(app.state_dir('DE2'), 'layer_a.gpkg'), [{'geom': box(5, 0, 6, 1), 'geom_id': 7}])
    os.utime(os.path.join(app.state_dir('DE2'), 'layer_a.gpkg'), (900_000_000, 900_000_000))
    join.join_all_layers(accessible)
    assert sorted(r['geom_id'] for r in read_gpkg(joined_path(app))[1]) == [0, 7]


def test_skipped_layers_are_no_longer_joined_but_kept(app):
    accessible = access('DE1', 'DE2')
    setup_states(app)
    join.join_all_layers(accessible)
    assert os.path.exists(joined_path(app))

    app.configure(skip_layers=['layer_a'])
    os.utime(joined_path(app), (1_000_000_000, 1_000_000_000))
    join.join_all_layers(accessible)

    assert os.path.getmtime(joined_path(app)) == 1_000_000_000
