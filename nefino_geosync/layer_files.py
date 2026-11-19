"""Helpers to find and inspect the per-state layer files in the output directory.

Only uses the standard library and pyshp, so it works without the optional join dependencies.
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

FILE_NAME_PATTERN = re.compile(r'(?P<layer>^.*?)(?P<buffer>__[0-9]+m)?(?P<ext>\..{3,4}$)')
STATE_DIR_PATTERN = re.compile(r'^DE[1-9A-G]$')

# All files that belong to one layer in the given output format. The first one is the main file.
EXTENSIONS: Dict[str, Tuple[str, ...]] = {
    'GPKG': ('.gpkg',),
    'SHP': ('.shp', '.shx', '.dbf', '.prj', '.cpg'),
}

# Name of the coordinate system in the .prj files written by the Nefino API (ESRI WKT, no EPSG code).
PRJ_NAMES: Dict[str, str] = {
    'ETRS_1989_UTM_Zone_32N': 'EPSG_25832',
    'ETRS_1989_UTM_Zone_33N': 'EPSG_25833',
    'ETRS_1989_LAEA': 'EPSG_3035',
    'GCS_WGS_1984': 'EPSG_4326',
    'ETRS_1989_LCC_Germany_E-N': 'EPSG_5243',
}
PRJ_NAME_PATTERN = re.compile(r'^\s*(?:PROJCS|GEOGCS)\["([^"]+)"')


def other_format(fmt: str) -> str:
    return 'SHP' if fmt == 'GPKG' else 'GPKG'


def parse_file_name(file_name: str) -> Optional[Tuple[str, str]]:
    """Returns (layer, extension) for a layer file name, or None if it does not look like one."""
    match = FILE_NAME_PATTERN.match(file_name)
    if not match:
        return None
    return match.group('layer'), match.group('ext').lower()


def state_dirs(output_path: str) -> Dict[str, str]:
    """Returns {state: directory} for all federal state folders in the output directory."""
    if not os.path.isdir(output_path):
        return {}
    return {
        name: os.path.join(output_path, name)
        for name in sorted(os.listdir(output_path))
        if STATE_DIR_PATTERN.match(name) and os.path.isdir(os.path.join(output_path, name))
    }


def list_layer_files(state_dir: str, fmt: str) -> Dict[str, str]:
    """Returns {layer: path of the main file} for all layers of the given format in a state folder."""
    main_ext = EXTENSIONS[fmt][0]
    result = {}
    for file_name in sorted(os.listdir(state_dir)):
        parsed = parse_file_name(file_name)
        if parsed and parsed[1] == main_ext:
            result[parsed[0]] = os.path.join(state_dir, file_name)
    return result


def component_files(main_file: str, fmt: str) -> List[str]:
    """Returns all existing files that belong to the layer of the given main file."""
    base = os.path.splitext(main_file)[0]
    return [base + ext for ext in EXTENSIONS[fmt] if os.path.exists(base + ext)]


class JoinSkipped(Exception):
    """Raised when a layer cannot be joined; the message is shown to the user."""


class GpkgInfo(NamedTuple):
    table: str
    geom_column: str
    geometry_type: str
    srs_id: int
    crs: Optional[Tuple[str, int]]  # (organization, code), e.g. ('EPSG', 25832)
    columns: List[str]


def open_gpkg_readonly(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f'{Path(os.path.abspath(path)).as_uri()}?mode=ro', uri=True)


def gpkg_info(path: str) -> GpkgInfo:
    """Reads the feature table name, geometry column, CRS and columns of a single-layer GeoPackage."""
    con = open_gpkg_readonly(path)
    try:
        table, geom_column, geometry_type, srs_id = con.execute(
            'SELECT table_name, column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns'
        ).fetchone()
        row = con.execute(
            'SELECT organization, organization_coordsys_id FROM gpkg_spatial_ref_sys WHERE srs_id = ?', (srs_id,)
        ).fetchone()
        crs = (row[0].upper(), int(row[1])) if row else None
        columns = [r[1] for r in con.execute(f'PRAGMA table_info({quote(table)})')]
        return GpkgInfo(table, geom_column, geometry_type.upper(), srs_id, crs, columns)
    finally:
        con.close()


def gpkg_crs_name(info: GpkgInfo) -> Optional[str]:
    """Returns the CRSType name (e.g. 'EPSG_25832') of a GeoPackage, or None if unknown."""
    if info.crs is None or info.crs[0] != 'EPSG':
        return None
    return f'EPSG_{info.crs[1]}'


def shp_crs_name(shp_path: str) -> Optional[str]:
    """Returns the CRSType name of a shapefile from its .prj, or None if it is missing or unknown."""
    prj = os.path.splitext(shp_path)[0] + '.prj'
    if not os.path.exists(prj):
        return None
    with open(prj, encoding='ascii', errors='replace') as f:
        match = PRJ_NAME_PATTERN.match(f.read())
    return PRJ_NAMES.get(match.group(1)) if match else None


def shp_field_names(shp_path: str) -> List[str]:
    """Returns the attribute field names of a shapefile."""
    import shapefile

    with shapefile.Reader(shp_path) as reader:
        return [field[0] for field in reader.fields[1:]]


def inspect_layer(main_file: str, fmt: str) -> Tuple[Optional[str], bool]:
    """Returns (CRSType name or None if unknown, whether it has a geom_id column) of a layer file."""
    if fmt == 'GPKG':
        info = gpkg_info(main_file)
        return gpkg_crs_name(info), 'geom_id' in info.columns
    return shp_crs_name(main_file), 'geom_id' in shp_field_names(main_file)


def quote(identifier: str) -> str:
    """Quotes an SQL identifier (table names contain spaces and umlauts)."""
    return '"' + identifier.replace('"', '""') + '"'
