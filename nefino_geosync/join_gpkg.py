"""Joins the per-state GeoPackages of one layer into a single GeoPackage.

Appending rows only needs the standard library (sqlite3). Fusing the pieces of each geom_id uses
the fuse module (shapely).
"""

import re
import shutil
import sqlite3
import struct
from .layer_files import GpkgInfo, JoinSkipped, gpkg_crs_name, gpkg_info, quote
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

ENVELOPE_SIZES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
SINGLE_TO_MULTI = {1: 4, 2: 5, 3: 6}  # Point -> MultiPoint, LineString -> MultiLineString, Polygon -> MultiPolygon
MULTI_TYPE_NAMES = {'POINT': 'MULTIPOINT', 'POLYGON': 'MULTIPOLYGON', 'LINESTRING': 'MULTILINESTRING'}


def join_layer(sources: List[Tuple[str, str]], out_path: str, fuse) -> None:
    """Joins the GeoPackages [(state, path), ...] into out_path and fuses pieces with the same geom_id.

    `fuse` is the fuse module (passed in so this module can be imported without shapely).
    """
    infos = [(state, gpkg_info(path)) for state, path in sources]
    check_consistency(infos)
    first = infos[0][1]
    # a state may declare POINT while another declares MULTIPOINT; use the multi type then, so the
    # pieces of a multipoint are fused instead of all but the first being dropped as duplicate points
    geometry_type = max((info.geometry_type for _, info in infos), key=lambda t: t.startswith('MULTI'))
    kind = fuse.geometry_kind(geometry_type)

    shutil.copyfile(sources[0][1], out_path)
    con = sqlite3.connect(out_path)
    try:
        register_functions(con)
        table = quote(first.table)
        append_sources(con, first, sources[1:])
        if 'geom_id' in gpkg_info_columns(con, first.table):
            fuse_pieces(con, first, kind, fuse)
        if kind in (fuse.POLYGON, fuse.LINE, fuse.MULTIPOINT):
            promote_to_multi(con, first)
        if has_table(con, 'gpkg_ogr_contents'):
            con.execute(
                f'UPDATE gpkg_ogr_contents SET feature_count = (SELECT count(*) FROM {table}) WHERE table_name = ?',
                (first.table,),
            )
        update_extent(con, first)
        con.commit()
    finally:
        con.close()


def check_consistency(infos: List[Tuple[str, GpkgInfo]]) -> None:
    """Raises JoinSkipped if the files cannot be joined (different CRS, table or geometry type)."""
    states_by_crs: Dict[str, List[str]] = defaultdict(list)
    for state, info in infos:
        states_by_crs[gpkg_crs_name(info) or f'srs_id {info.srs_id}'].append(state)
    if len(states_by_crs) > 1:
        details = '; '.join(f'{crs}: {", ".join(states)}' for crs, states in sorted(states_by_crs.items()))
        raise JoinSkipped(f'the states use different coordinate reference systems ({details}). Run geosync again to re-download them.')
    if len({info.srs_id for _, info in infos}) > 1:
        # the appended geometry blobs keep their srs_id, which must exist in the joined file
        raise JoinSkipped('the states use different spatial reference ids for the same coordinate reference system')
    if len({info.table for _, info in infos}) > 1:
        raise JoinSkipped('the states contain differently named tables')
    if len({info.geom_column for _, info in infos}) > 1:
        raise JoinSkipped('the states contain differently named geometry columns')
    families = {info.geometry_type.replace('MULTI', '') for _, info in infos}
    if len(families) > 1:
        raise JoinSkipped(f'the states have different geometry types ({", ".join(sorted(families))})')


def append_sources(con: sqlite3.Connection, first: GpkgInfo, sources: List[Tuple[str, str]]) -> None:
    """Appends the rows of all other states to the copied first GeoPackage."""
    table = quote(first.table)
    target_columns = gpkg_info_columns(con, first.table)
    warned = False
    for _, path in sources:
        con.execute('ATTACH DATABASE ? AS src', (path,))
        try:
            source_columns = {
                r[1]: r[2] for r in con.execute(f'PRAGMA src.table_info({table})') if not r[5]
            }  # name -> declared type, without the primary key
            missing = [c for c in source_columns if c not in target_columns]
            if missing or set(source_columns) != set(target_columns):
                if not warned:
                    print(f'⚠️  The states have different columns in {first.table}; joining all columns.')
                    warned = True
                for column in missing:
                    con.execute(f'ALTER TABLE {table} ADD COLUMN {quote(column)} {source_columns[column]}')
                    target_columns.append(column)
            columns = ', '.join(quote(c) for c in source_columns)
            con.execute(f'INSERT INTO {table} ({columns}) SELECT {columns} FROM src.{table}')
            con.commit()
        finally:
            con.rollback()  # DETACH fails while a transaction is open (e.g. after a failed INSERT)
            con.execute('DETACH DATABASE src')


def fuse_pieces(con: sqlite3.Connection, info: GpkgInfo, kind: str, fuse) -> None:
    """Fuses all rows sharing a geom_id into the first of them."""
    table, geom = quote(info.table), quote(info.geom_column)
    con.execute(f'CREATE INDEX IF NOT EXISTS geosync_tmp_geom_id ON {table} (geom_id)')
    pk = primary_key(con, info.table)
    # only the duplicated geom_ids are held in memory; the geometries are loaded one group at a time
    geom_ids = [
        r[0]
        for r in con.execute(
            f'SELECT geom_id FROM {table} WHERE geom_id IS NOT NULL GROUP BY geom_id HAVING count(*) > 1'
        ).fetchall()
    ]
    for geom_id in geom_ids:
        group = con.execute(f'SELECT {pk}, {geom} FROM {table} WHERE geom_id = ? ORDER BY {pk}', (geom_id,)).fetchall()
        keep, drop = group[0][0], [(r[0],) for r in group[1:]]
        if kind != fuse.POINT:
            fused = fuse.fuse_group([fuse.gpkg_to_geom(r[1]) for r in group], kind)
            blob = fuse.geom_to_gpkg(fused, info.srs_id) if fused is not None else None
            con.execute(f'UPDATE {table} SET {geom} = ? WHERE {pk} = ?', (blob, keep))
        con.executemany(f'DELETE FROM {table} WHERE {pk} = ?', drop)
    con.execute('DROP INDEX geosync_tmp_geom_id')


def promote_to_multi(con: sqlite3.Connection, info: GpkgInfo) -> None:
    """Turns every Point/Polygon/LineString into a one-part Multi* geometry and declares the multi type."""
    table, geom = quote(info.table), quote(info.geom_column)
    con.execute(f'UPDATE {table} SET {geom} = ST_ToMulti({geom}) WHERE ST_IsSingle({geom})')
    base = info.geometry_type.replace('MULTI', '')
    if base in MULTI_TYPE_NAMES:
        multi = MULTI_TYPE_NAMES[base]
        con.execute(
            'UPDATE gpkg_geometry_columns SET geometry_type_name = ? WHERE table_name = ?',
            (multi, info.table),
        )
        set_declared_column_type(con, info.table, info.geom_column, base, multi)


def set_declared_column_type(con: sqlite3.Connection, table: str, column: str, old: str, new: str) -> None:
    """Changes the declared type of the geometry column in CREATE TABLE (GDAL warns if it differs from
    gpkg_geometry_columns). SQLite cannot alter column types, so the stored schema is edited like GDAL does."""
    sql = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()[0]
    pattern = re.compile(rf'({re.escape(quote(column))}\s+){old}\b', re.IGNORECASE)
    new_sql, count = pattern.subn(rf'\g<1>{new}', sql, count=1)
    if count == 0:
        return
    con.commit()
    if hasattr(con, 'setconfig'):  # Python 3.12+: make sure editing the schema is allowed
        con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, False)
    (schema_version,) = con.execute('PRAGMA schema_version').fetchone()
    con.execute('PRAGMA writable_schema = ON')
    try:
        con.execute("UPDATE sqlite_master SET sql = ? WHERE type = 'table' AND name = ?", (new_sql, table))
        con.execute(f'PRAGMA schema_version = {schema_version + 1}')
        con.commit()
    except sqlite3.DatabaseError:  # e.g. SQLite in defensive mode on Python 3.11 (no setconfig)
        con.rollback()
    finally:
        con.execute('PRAGMA writable_schema = OFF')


def update_extent(con: sqlite3.Connection, info: GpkgInfo) -> None:
    table, geom = quote(info.table), quote(info.geom_column)
    rtree = f'rtree_{info.table}_{info.geom_column}'
    if has_table(con, rtree):
        extent = con.execute(f'SELECT min(minx), min(miny), max(maxx), max(maxy) FROM {quote(rtree)}').fetchone()
    else:
        extent = con.execute(
            f'SELECT min(ST_MinX({geom})), min(ST_MinY({geom})), max(ST_MaxX({geom})), max(ST_MaxY({geom})) FROM {table}'
        ).fetchone()
    con.execute(
        "UPDATE gpkg_contents SET min_x = ?, min_y = ?, max_x = ?, max_y = ?, "
        "last_change = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE table_name = ?",
        (*extent, info.table),
    )


def gpkg_info_columns(con: sqlite3.Connection, table: str) -> List[str]:
    """Returns the non-primary-key columns of a table."""
    return [r[1] for r in con.execute(f'PRAGMA table_info({quote(table)})') if not r[5]]


def primary_key(con: sqlite3.Connection, table: str) -> str:
    return quote(next(r[1] for r in con.execute(f'PRAGMA table_info({quote(table)})') if r[5]))


def has_table(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


# --- SQL functions used by the GeoPackage R-tree triggers -----------------------------------
# GDAL's triggers call ST_IsEmpty and ST_Min/MaxX/Y, which plain sqlite3 does not provide.


def register_functions(con: sqlite3.Connection) -> None:
    con.create_function('ST_IsEmpty', 1, st_is_empty, deterministic=True)
    con.create_function('ST_MinX', 1, lambda b: _bound(b, 0), deterministic=True)
    con.create_function('ST_MaxX', 1, lambda b: _bound(b, 1), deterministic=True)
    con.create_function('ST_MinY', 1, lambda b: _bound(b, 2), deterministic=True)
    con.create_function('ST_MaxY', 1, lambda b: _bound(b, 3), deterministic=True)
    con.create_function('ST_IsSingle', 1, st_is_single, deterministic=True)
    con.create_function('ST_ToMulti', 1, st_to_multi, deterministic=True)


def st_is_empty(blob: Optional[bytes]) -> Optional[int]:
    if blob is None:
        return None
    return 1 if envelope(blob) is None else 0


def _bound(blob: Optional[bytes], index: int) -> Optional[float]:
    if blob is None:
        return None
    env = envelope(blob)
    return env[index] if env else None


def envelope(blob: bytes) -> Optional[Tuple[float, float, float, float]]:
    """Returns (minx, maxx, miny, maxy) of a GeoPackage geometry blob, or None if it is empty."""
    flags = blob[3]
    if flags & 0b1_0000:
        return None
    env_type = (flags >> 1) & 0b111
    if env_type:
        order = '<' if flags & 1 else '>'
        return struct.unpack_from(order + '4d', blob, 8)
    return wkb_bounds(blob, 8)


def wkb_bounds(blob: bytes, offset: int) -> Optional[Tuple[float, float, float, float]]:
    """Computes (minx, maxx, miny, maxy) from WKB, used when a blob has no envelope (e.g. points)."""
    xs, ys = [], []
    _collect_coords(blob, offset, xs, ys)
    xs = [x for x in xs if x == x]  # drop NaN (empty points)
    ys = [y for y in ys if y == y]
    if not xs or not ys:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _collect_coords(blob: bytes, offset: int, xs: list, ys: list) -> int:
    order = '<' if blob[offset] == 1 else '>'
    (wkb_type,) = struct.unpack_from(order + 'I', blob, offset + 1)
    offset += 5
    iso_type = wkb_type & 0x0FFF_FFFF  # without the EWKB Z/M flags
    has_z = bool(wkb_type & 0x8000_0000) or iso_type // 1000 in (1, 3)
    has_m = bool(wkb_type & 0x4000_0000) or iso_type // 1000 in (2, 3)
    base = iso_type % 1000
    dims = 2 + has_z + has_m

    def read_points(offset: int, count: int) -> int:
        for _ in range(count):
            x, y = struct.unpack_from(order + 'dd', blob, offset)
            xs.append(x)
            ys.append(y)
            offset += 8 * dims
        return offset

    if base == 1:
        return read_points(offset, 1)
    (count,) = struct.unpack_from(order + 'I', blob, offset)
    offset += 4
    if base == 2:
        return read_points(offset, count)
    if base == 3:
        for _ in range(count):
            (n,) = struct.unpack_from(order + 'I', blob, offset)
            offset = read_points(offset + 4, n)
        return offset
    if base in (4, 5, 6, 7):
        for _ in range(count):
            offset = _collect_coords(blob, offset, xs, ys)
        return offset
    raise ValueError(f'Unsupported WKB geometry type {wkb_type}')


def wkb_offset(blob: bytes) -> int:
    return 8 + ENVELOPE_SIZES[(blob[3] >> 1) & 0b111]


def _wkb_base_type(blob: bytes) -> Tuple[int, int]:
    """Returns (base type, full type) of the WKB in a GeoPackage blob."""
    offset = wkb_offset(blob)
    order = '<' if blob[offset] == 1 else '>'
    (wkb_type,) = struct.unpack_from(order + 'I', blob, offset + 1)
    return (wkb_type & 0x0FFF_FFFF) % 1000, wkb_type


def st_is_single(blob: Optional[bytes]) -> int:
    if blob is None:
        return 0
    return 1 if _wkb_base_type(blob)[0] in SINGLE_TO_MULTI else 0


def st_to_multi(blob: Optional[bytes]) -> Optional[bytes]:
    """Wraps a Point/Polygon/LineString WKB into a one-part Multi* WKB, keeping the GeoPackage header."""
    if blob is None:
        return None
    base, wkb_type = _wkb_base_type(blob)
    if base not in SINGLE_TO_MULTI:
        return blob
    offset = wkb_offset(blob)
    order_byte = blob[offset]
    order = '<' if order_byte == 1 else '>'
    multi_type = wkb_type - base + SINGLE_TO_MULTI[base]
    return bytes(blob[:offset]) + bytes([order_byte]) + struct.pack(order + 'II', multi_type, 1) + bytes(blob[offset:])
