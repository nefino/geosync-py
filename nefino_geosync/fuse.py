"""Fuses geometries that were cut apart by federal state boundaries back together.

This is the only module that needs the optional shapely dependency (pip install "nefino-geosync[join]").
"""

import shapely
import shapely.geometry
import struct
from .join_gpkg import wkb_offset
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from typing import List

POLYGON, LINE, MULTIPOINT, POINT, OTHER = 'polygon', 'line', 'multipoint', 'point', 'other'
SLIVER_RATIO = 1e-12


def geometry_kind(geometry_type_name: str) -> str:
    """Maps a geometry type name (GeoPackage or shapefile) to polygon/line/point/other."""
    name = geometry_type_name.upper()
    if 'POLYGON' in name:
        return POLYGON
    if 'LINE' in name or 'ARC' in name:
        return LINE
    if 'MULTIPOINT' in name:
        return MULTIPOINT
    if 'POINT' in name:
        return POINT
    return OTHER


def fuse_group(geoms: List[shapely.Geometry], kind: str) -> shapely.Geometry:
    """Fuses the pieces of one geom_id into one geometry."""
    geoms = [g for g in geoms if g is not None]
    if not geoms:
        return None
    if kind == POINT:
        return geoms[0]
    try:
        fused = shapely.union_all(geoms)
    except shapely.errors.GEOSException:
        fused = shapely.union_all([shapely.make_valid(g) for g in geoms])
    if kind == LINE:
        fused = shapely.line_merge(to_multi(fused, LINE)) if not fused.is_empty else fused
    return to_multi(fused, kind)


def to_multi(geom: shapely.Geometry, kind: str) -> shapely.Geometry:
    """Returns the geometry as MultiPolygon/MultiLineString/MultiPoint (points and others are returned unchanged)."""
    if kind == POLYGON:
        parts = _parts(geom, Polygon)
        # Clipping leaves floating point slivers (~1e-10 m wide). Their ring orientation is undefined,
        # which makes GDAL complain about the winding order, so drop parts that are negligibly small
        # compared to the largest part (relative, so it works for metres and degrees alike).
        largest = max((p.area for p in parts), default=0)
        return MultiPolygon([p for p in parts if p.area > largest * SLIVER_RATIO] or parts)
    if kind == LINE:
        return MultiLineString(_parts(geom, LineString))
    if kind == MULTIPOINT:
        return MultiPoint(_parts(geom, Point))
    return geom


def _parts(geom: shapely.Geometry, part_type) -> list:
    if isinstance(geom, part_type):
        return [] if geom.is_empty else [geom]
    if isinstance(geom, (MultiPolygon, MultiLineString, MultiPoint, GeometryCollection)):
        return [p for g in geom.geoms for p in _parts(g, part_type)]
    return []


def from_geo_interface(obj) -> shapely.Geometry:
    """Converts an object with __geo_interface__ (e.g. a pyshp Shape) to a shapely geometry."""
    return shapely.geometry.shape(obj)


def to_geo_interface(geom: shapely.Geometry) -> dict:
    """Converts a shapely geometry to a GeoJSON-like dict (accepted by pyshp)."""
    return shapely.geometry.mapping(geom)


# --- GeoPackage geometry blobs -------------------------------------------------------------

def gpkg_to_geom(blob: bytes) -> shapely.Geometry:
    """Reads a GeoPackage geometry blob."""
    if blob is None:
        return None
    return shapely.from_wkb(bytes(blob[wkb_offset(blob):]))


def geom_to_gpkg(geom: shapely.Geometry, srs_id: int) -> bytes:
    """Writes a GeoPackage geometry blob (little endian ISO WKB, as GeoPackage requires, with an XY envelope)."""
    if geom.is_empty:
        flags = 0b0001_0001  # empty, no envelope, little endian
        return b'GP\x00' + bytes([flags]) + struct.pack('<i', srs_id) + shapely.to_wkb(geom, byte_order=1, flavor='iso')
    minx, miny, maxx, maxy = geom.bounds
    flags = 0b0000_0011  # envelope [minx, maxx, miny, maxy], little endian
    header = b'GP\x00' + bytes([flags]) + struct.pack('<i', srs_id) + struct.pack('<4d', minx, maxx, miny, maxy)
    return header + shapely.to_wkb(geom, byte_order=1, flavor='iso')
