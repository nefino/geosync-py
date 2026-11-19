"""Shared fixtures: an isolated app directory and generated GeoPackages / shapefiles.

The GeoPackage DDL mirrors what GDAL writes for the files delivered by the Nefino API
(feature table, R-tree index with its triggers, feature count triggers).
"""

import argparse
import json
import os
import pytest
import shapefile
import shapely
import sqlite3
import struct
from nefino_geosync import fuse
from nefino_geosync.config import Config
from nefino_geosync.join_gpkg import register_functions
from nefino_geosync.journal import Journal
from nefino_geosync.layer_files import quote
from nefino_geosync.parse_args import parse_args

PRJ = {
    'EPSG_25832': 'PROJCS["ETRS_1989_UTM_Zone_32N",GEOGCS["GCS_ETRS_1989",DATUM["D_ETRS_1989",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",9.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]',
    'EPSG_25833': 'PROJCS["ETRS_1989_UTM_Zone_33N",GEOGCS["GCS_ETRS_1989",DATUM["D_ETRS_1989",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",15.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]',
}

TABLE = 'Fläche mit Leerzeichen'


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Isolated app directory with a config; returns a helper to change config values and CLI args."""
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('APPDATA', str(home))
    output = tmp_path / 'output'
    output.mkdir()

    class App:
        output_path = str(output)

        def configure(self, **values):
            config = {
                'output_path': str(output),
                'output_format': 'GPKG',
                'crs': 'EPSG_25832',
                'skip_layers': [],
                'api_key': 'test',
                'join_layers': False,
            }
            config.update(values)
            from nefino_geosync.storage import get_app_directory

            with open(os.path.join(get_app_directory(), 'config.json'), 'w') as f:
                json.dump(config, f)
            Config._instance = None
            Journal._instance = None

        def args(self, **values):
            cache = parse_args.__defaults__[0]
            cache.clear()
            cache.append(argparse.Namespace(**{'configure': False, 'resume': False, 'join': False, 'verbose': False, **values}))

        def state_dir(self, state):
            path = os.path.join(str(output), state)
            os.makedirs(path, exist_ok=True)
            return path

    instance = App()
    instance.configure()
    instance.args()
    yield instance
    Config._instance = None
    Journal._instance = None
    parse_args.__defaults__[0].clear()


def blob(geom, srs_id):
    """GeoPackage blob as GDAL writes it: points without envelope, everything else with an XY envelope."""
    if geom is None:
        return None
    if geom.geom_type == 'Point':
        return b'GP\x00\x01' + struct.pack('<i', srs_id) + shapely.to_wkb(geom, byte_order=1)
    return fuse.geom_to_gpkg(geom, srs_id)


def make_gpkg(path, rows, geometry_type='POLYGON', srs=25832, columns=None, table=TABLE):
    """Writes a single-layer GeoPackage. rows: list of dicts with 'geom' (shapely) and attribute values."""
    columns = columns if columns is not None else {'geom_id': 'MEDIUMINT', 'name': 'TEXT'}
    con = sqlite3.connect(path)
    register_functions(con)
    t, r = quote(table), quote(f'rtree_{table}_geom')
    con.executescript(f"""
        PRAGMA application_id = 1196444487;
        PRAGMA user_version = 10200;
        CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY, organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
        CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER);
        CREATE TABLE gpkg_ogr_contents (table_name TEXT NOT NULL PRIMARY KEY, feature_count INTEGER DEFAULT NULL);
        CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL, CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name));
        CREATE TABLE gpkg_extensions (table_name TEXT, column_name TEXT, extension_name TEXT NOT NULL, definition TEXT NOT NULL, scope TEXT NOT NULL);
        CREATE TABLE {t} ("fid" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "geom" {geometry_type}{''.join(f', {quote(c)} {ty}' for c, ty in columns.items())});
        CREATE VIRTUAL TABLE {r} USING rtree("id", "minx", "maxx", "miny", "maxy");
        CREATE TRIGGER "rtree_insert" AFTER INSERT ON {t} WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom")) BEGIN INSERT OR REPLACE INTO {r} VALUES (NEW."fid",ST_MinX(NEW."geom"), ST_MaxX(NEW."geom"),ST_MinY(NEW."geom"), ST_MaxY(NEW."geom")); END;
        CREATE TRIGGER "rtree_update1" AFTER UPDATE OF "geom" ON {t} WHEN OLD."fid" = NEW."fid" AND (NEW."geom" NOTNULL AND NOT ST_IsEmpty(NEW."geom")) BEGIN INSERT OR REPLACE INTO {r} VALUES (NEW."fid",ST_MinX(NEW."geom"), ST_MaxX(NEW."geom"),ST_MinY(NEW."geom"), ST_MaxY(NEW."geom")); END;
        CREATE TRIGGER "rtree_update2" AFTER UPDATE OF "geom" ON {t} WHEN OLD."fid" = NEW."fid" AND (NEW."geom" ISNULL OR ST_IsEmpty(NEW."geom")) BEGIN DELETE FROM {r} WHERE id = OLD."fid"; END;
        CREATE TRIGGER "rtree_delete" AFTER DELETE ON {t} WHEN old."geom" NOT NULL BEGIN DELETE FROM {r} WHERE id = OLD."fid"; END;
        CREATE TRIGGER "count_insert" AFTER INSERT ON {t} BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count + 1 WHERE lower(table_name) = lower('{table}'); END;
        CREATE TRIGGER "count_delete" AFTER DELETE ON {t} BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count - 1 WHERE lower(table_name) = lower('{table}'); END;
    """)
    con.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, 'EPSG', ?, 'definition', NULL)", (f'EPSG:{srs}', srs, srs))
    con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES (?, 'features', ?, ?)", (table, table, srs))
    con.execute('INSERT INTO gpkg_ogr_contents VALUES (?, 0)', (table,))
    con.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)", (table, geometry_type, srs))
    con.execute(
        "INSERT INTO gpkg_extensions VALUES (?, 'geom', 'gpkg_rtree_index', 'http://www.geopackage.org/spec120/#extension_rtree', 'write-only')",
        (table,),
    )
    for row in rows:
        names = ['geom'] + [c for c in columns if c in row]
        values = [blob(row['geom'], srs)] + [row[c] for c in names[1:]]
        con.execute(f'INSERT INTO {t} ({", ".join(quote(n) for n in names)}) VALUES ({", ".join("?" * len(names))})', values)
    con.commit()
    con.close()
    return path


def read_gpkg(path, table=TABLE):
    """Returns (geometry type name, rows as dicts with shapely 'geom') of a joined GeoPackage."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    geometry_type = con.execute('SELECT geometry_type_name FROM gpkg_geometry_columns').fetchone()[0]
    rows = [dict(r) for r in con.execute(f'SELECT * FROM {quote(table)} ORDER BY fid')]
    for row in rows:
        row['geom'] = fuse.gpkg_to_geom(row['geom'])
    con.close()
    return geometry_type, rows


def make_shp(base, rows, shape_type=shapefile.POLYGON, fields=None, crs='EPSG_25832', cpg='ISO-8859-1'):
    """Writes a shapefile. rows: list of dicts with 'geom' (shapely) and attribute values."""
    fields = fields if fields is not None else [('geom_id', 'N', 9, 0), ('name', 'C', 80, 0)]
    with shapefile.Writer(base, shapeType=shape_type, encoding='latin1') as writer:
        for field in fields:
            writer.field(*field)
        for row in rows:
            geom = row['geom']
            if geom.geom_type == 'Point':
                writer.point(geom.x, geom.y)
            else:
                writer.shape(shapely.geometry.mapping(geom))
            writer.record(*[row.get(f[0]) for f in fields])
    with open(base + '.prj', 'w') as f:
        f.write(PRJ[crs])
    with open(base + '.cpg', 'w') as f:
        f.write(cpg)
    return base + '.shp'


def read_shp(path):
    with shapefile.Reader(path) as reader:
        fields = [tuple(f) for f in reader.fields[1:]]
        rows = []
        for shape_record in reader.iterShapeRecords():
            row = shape_record.record.as_dict()
            row['geom'] = shapely.geometry.shape(shape_record.shape.__geo_interface__)
            rows.append(row)
        return reader.shapeType, fields, rows
