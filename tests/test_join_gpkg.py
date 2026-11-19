import pytest
import sqlite3
from contextlib import closing
from conftest import TABLE, make_gpkg, read_gpkg
from nefino_geosync import fuse
from nefino_geosync.join_gpkg import join_layer
from nefino_geosync.layer_files import JoinSkipped, quote
from shapely.geometry import LineString, MultiPoint, Point, box


def test_appends_states_and_fuses_pieces_cut_by_borders(tmp_path):
    # geom_id 1 is a 10x10 square cut into three strips: two of them lie in DE1 (cut twice by the
    # border within the same state), the middle one in DE2.
    de1 = make_gpkg(tmp_path / 'de1.gpkg', [
        {'geom': box(0, 0, 3, 10), 'geom_id': 1, 'name': 'Größe'},
        {'geom': box(20, 0, 21, 1), 'geom_id': 2, 'name': 'only DE1'},
        {'geom': box(7, 0, 10, 10), 'geom_id': 1, 'name': 'Größe'},
    ])
    de2 = make_gpkg(tmp_path / 'de2.gpkg', [
        {'geom': box(3, 0, 7, 10), 'geom_id': 1, 'name': 'Größe'},
        {'geom': box(30, 0, 31, 1), 'geom_id': 3, 'name': 'only DE2'},
    ])
    out = tmp_path / 'joined.gpkg'

    join_layer([('DE1', str(de1)), ('DE2', str(de2))], str(out), fuse)

    geometry_type, rows = read_gpkg(out)
    assert geometry_type == 'MULTIPOLYGON'
    assert sorted(r['geom_id'] for r in rows) == [1, 2, 3]
    assert all(r['geom'].geom_type == 'MultiPolygon' for r in rows)
    fused = next(r for r in rows if r['geom_id'] == 1)
    assert fused['name'] == 'Größe'
    assert len(fused['geom'].geoms) == 1
    assert fused['geom'].area == pytest.approx(100)

    with closing(sqlite3.connect(out)) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert con.execute(f'SELECT count(*) FROM {quote("rtree_" + TABLE + "_geom")}').fetchone()[0] == 3
        assert con.execute('SELECT feature_count FROM gpkg_ogr_contents').fetchone()[0] == 3
        extent = con.execute('SELECT min_x, min_y, max_x, max_y FROM gpkg_contents').fetchone()
        assert extent == (0, 0, 31, 10)
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name = 'geosync_tmp_geom_id'").fetchone()[0] == 0
        table_sql = con.execute('SELECT sql FROM sqlite_master WHERE name = ?', (TABLE,)).fetchone()[0]
        assert '"geom" MULTIPOLYGON' in table_sql


def test_points_are_deduplicated_and_stay_points(tmp_path):
    de1 = make_gpkg(tmp_path / 'de1.gpkg', [{'geom': Point(1, 2), 'geom_id': 1}, {'geom': Point(5, 5), 'geom_id': 2}], 'POINT')
    de2 = make_gpkg(tmp_path / 'de2.gpkg', [{'geom': Point(1, 2), 'geom_id': 1}], 'POINT')
    out = tmp_path / 'joined.gpkg'

    join_layer([('DE1', str(de1)), ('DE2', str(de2))], str(out), fuse)

    geometry_type, rows = read_gpkg(out)
    assert geometry_type == 'POINT'
    assert [(r['geom_id'], r['geom'].wkt) for r in rows] == [(1, 'POINT (1 2)'), (2, 'POINT (5 5)')]
    with closing(sqlite3.connect(out)) as con:
        rtree = con.execute(f'SELECT minx, maxx, miny, maxy FROM {quote("rtree_" + TABLE + "_geom")} ORDER BY id').fetchall()
    assert rtree == [(1, 1, 2, 2), (5, 5, 5, 5)]


def test_lines_are_merged(tmp_path):
    de1 = make_gpkg(tmp_path / 'de1.gpkg', [{'geom': LineString([(0, 0), (5, 0)]), 'geom_id': 1}], 'LINESTRING')
    de2 = make_gpkg(tmp_path / 'de2.gpkg', [{'geom': LineString([(5, 0), (10, 0)]), 'geom_id': 1}], 'LINESTRING')
    out = tmp_path / 'joined.gpkg'

    join_layer([('DE1', str(de1)), ('DE2', str(de2))], str(out), fuse)

    geometry_type, rows = read_gpkg(out)
    assert geometry_type == 'MULTILINESTRING'
    assert len(rows) == 1
    assert len(rows[0]['geom'].geoms) == 1
    assert rows[0]['geom'].length == pytest.approx(10)


def test_differing_columns_are_joined_with_a_warning(tmp_path, capsys):
    de1 = make_gpkg(tmp_path / 'de1.gpkg', [{'geom': box(0, 0, 1, 1), 'geom_id': 1, 'name': 'a'}])
    de2 = make_gpkg(
        tmp_path / 'de2.gpkg',
        [{'geom': box(2, 0, 3, 1), 'geom_id': 2, 'name': 'b', 'extra': 7}],
        columns={'geom_id': 'MEDIUMINT', 'name': 'TEXT', 'extra': 'INTEGER'},
    )
    out = tmp_path / 'joined.gpkg'

    join_layer([('DE1', str(de1)), ('DE2', str(de2))], str(out), fuse)

    _, rows = read_gpkg(out)
    assert [(r['geom_id'], r['extra']) for r in rows] == [(1, None), (2, 7)]
    assert 'different columns' in capsys.readouterr().out


def test_different_crs_is_skipped(tmp_path):
    de1 = make_gpkg(tmp_path / 'de1.gpkg', [{'geom': box(0, 0, 1, 1), 'geom_id': 1}], srs=25832)
    de4 = make_gpkg(tmp_path / 'de4.gpkg', [{'geom': box(0, 0, 1, 1), 'geom_id': 2}], srs=25833)

    with pytest.raises(JoinSkipped, match='EPSG_25833: DE4'):
        join_layer([('DE1', str(de1)), ('DE4', str(de4))], str(tmp_path / 'joined.gpkg'), fuse)


def test_floating_point_slivers_are_dropped_when_fusing():
    sliver = box(10, 0, 10 + 1e-10, 1e-10)  # left over from clipping, ~1e-10 m wide
    fused = fuse.fuse_group([box(0, 0, 5, 10), box(5, 0, 10, 10), sliver], fuse.POLYGON)
    assert len(fused.geoms) == 1
    assert fused.area == pytest.approx(100)

    only_slivers = fuse.fuse_group([sliver, box(20, 0, 20 + 1e-10, 1e-10)], fuse.POLYGON)
    assert len(only_slivers.geoms) == 2  # nothing bigger to keep, so they stay


def test_point_and_multipoint_states_fuse_pieces_instead_of_dropping_them(tmp_path):
    de1 = make_gpkg(tmp_path / 'de1.gpkg', [{'geom': Point(1, 2), 'geom_id': 1}], 'POINT')
    de2 = make_gpkg(tmp_path / 'de2.gpkg', [{'geom': MultiPoint([(8, 9), (10, 11)]), 'geom_id': 1}], 'MULTIPOINT')
    out = tmp_path / 'joined.gpkg'

    join_layer([('DE1', str(de1)), ('DE2', str(de2))], str(out), fuse)

    geometry_type, rows = read_gpkg(out)
    assert geometry_type == 'MULTIPOINT'
    assert len(rows) == 1
    assert rows[0]['geom'].equals(MultiPoint([(1, 2), (8, 9), (10, 11)]))
