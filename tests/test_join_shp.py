import pytest
import shapefile
from conftest import make_shp, read_shp
from nefino_geosync import fuse, join_shp
from nefino_geosync.join_shp import join_layer
from nefino_geosync.layer_files import JoinSkipped
from shapely.geometry import Point, box


def test_fuses_pieces_and_widens_fields(tmp_path):
    de1 = make_shp(
        str(tmp_path / 'de1'),
        [{'geom': box(0, 0, 5, 10), 'geom_id': 1, 'name': 'Größe', 'value': 3}, {'geom': box(20, 0, 21, 1), 'geom_id': 2, 'name': 'x', 'value': 1}],
        fields=[('geom_id', 'N', 9, 0), ('name', 'C', 10, 0), ('value', 'N', 9, 0)],
    )
    de2 = make_shp(
        str(tmp_path / 'de2'),
        [{'geom': box(5, 0, 10, 10), 'geom_id': 1, 'name': 'Größe', 'value': 3.5}],
        fields=[('geom_id', 'N', 9, 0), ('name', 'C', 100, 0), ('value', 'N', 24, 15)],
    )
    out = str(tmp_path / 'joined')

    join_layer([('DE1', de1), ('DE2', de2)], out, fuse)

    shape_type, fields, rows = read_shp(out + '.shp')
    assert shape_type == shapefile.POLYGON
    assert [(f[0], f[2], f[3]) for f in fields] == [('geom_id', 9, 0), ('name', 100, 0), ('value', 24, 15)]
    assert sorted(r['geom_id'] for r in rows) == [1, 2]
    fused = next(r for r in rows if r['geom_id'] == 1)
    assert fused['name'] == 'Größe'
    assert fused['geom'].area == pytest.approx(100)
    assert fused['geom'].is_valid
    with open(out + '.cpg') as f:
        assert f.read() == 'ISO-8859-1'
    with open(out + '.prj') as f:
        assert f.read().startswith('PROJCS["ETRS_1989_UTM_Zone_32N"')


def test_points_are_deduplicated(tmp_path):
    de1 = make_shp(str(tmp_path / 'de1'), [{'geom': Point(1, 2), 'geom_id': 1}], shape_type=shapefile.POINT)
    de2 = make_shp(str(tmp_path / 'de2'), [{'geom': Point(1, 2), 'geom_id': 1}, {'geom': Point(3, 3), 'geom_id': 2}], shape_type=shapefile.POINT)
    out = str(tmp_path / 'joined')

    join_layer([('DE1', de1), ('DE2', de2)], out, fuse)

    shape_type, _, rows = read_shp(out + '.shp')
    assert shape_type == shapefile.POINT
    assert sorted((r['geom_id'], r['geom'].wkt) for r in rows) == [(1, 'POINT (1 2)'), (2, 'POINT (3 3)')]


def test_too_big_for_a_shapefile_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(join_shp, 'MAX_FILE_SIZE', 200)
    de1 = make_shp(str(tmp_path / 'de1'), [{'geom': box(0, 0, 1, 1), 'geom_id': i} for i in range(10)])

    with pytest.raises(JoinSkipped, match='limited to 2 GB'):
        join_layer([('DE1', de1)], str(tmp_path / 'joined'), fuse)


def test_different_crs_is_skipped(tmp_path):
    de1 = make_shp(str(tmp_path / 'de1'), [{'geom': box(0, 0, 1, 1), 'geom_id': 1}], crs='EPSG_25832')
    de4 = make_shp(str(tmp_path / 'de4'), [{'geom': box(0, 0, 1, 1), 'geom_id': 2}], crs='EPSG_25833')

    with pytest.raises(JoinSkipped, match='coordinate reference systems'):
        join_layer([('DE1', de1), ('DE4', de4)], str(tmp_path / 'joined'), fuse)
