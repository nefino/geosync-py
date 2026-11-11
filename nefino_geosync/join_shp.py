"""Joins the per-state shapefiles of one layer into a single shapefile (using pyshp)."""

import os
import shapefile
import shutil
from .layer_files import JoinSkipped, shp_crs_name
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

# .shp and .dbf files use 32-bit offsets, so neither may exceed 2 GB.
MAX_FILE_SIZE = 2**31 - 1
MAX_TEXT_SIZE = 254


def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ''
    with open(path, encoding='ascii', errors='replace') as f:
        return f.read().strip()


def merged_fields(readers: List[Tuple[str, shapefile.Reader]]) -> List[Tuple[str, str, int, int]]:
    """Combines the field definitions of all states: widest size, most decimals, text capped at 254."""
    fields: Dict[str, List] = {}
    order: List[str] = []
    occurrences: Counter = Counter()
    for _, reader in readers:
        for name, field_type, size, decimal in (tuple(f) for f in reader.fields[1:]):
            field_type = getattr(field_type, 'value', field_type)  # pyshp 3 uses a FieldType enum
            occurrences[name] += 1
            if name not in fields:
                fields[name] = [field_type, size, decimal]
                order.append(name)
                continue
            current = fields[name]
            if current[0] != field_type:
                # different types (e.g. date and text): keep the values as text, wide enough for any of them
                current[0], size = 'C', MAX_TEXT_SIZE
            current[1] = max(current[1], size)
            current[2] = max(current[2], decimal)
    for name in order:
        if occurrences[name] < len(readers):
            print(f'⚠️  Field {name} only exists in some states; joining all fields.')
    result = []
    for name in order:
        field_type, size, decimal = fields[name]
        if field_type == 'C':
            size, decimal = min(size, MAX_TEXT_SIZE), 0
        result.append((name, field_type, size, decimal))
    return result


def check_size(sources: List[Tuple[str, str]], fields, record_count: int) -> None:
    """Raises JoinSkipped if the joined .shp or .dbf would exceed the 2 GB shapefile limit."""
    dbf_size = 32 + 32 * len(fields) + 1 + record_count * (1 + sum(f[2] for f in fields)) + 1
    shp_size = 100 + sum(max(os.path.getsize(path) - 100, 0) for _, path in sources)
    biggest = max(dbf_size, shp_size)
    if biggest > MAX_FILE_SIZE:
        raise JoinSkipped(
            f'the joined shapefile would be {biggest / 1e9:.1f} GB, but shapefiles are limited to 2 GB. '
            'Use the GPKG output format to join this layer.'
        )


def join_layer(sources: List[Tuple[str, str]], out_base: str, fuse) -> None:
    """Joins the shapefiles [(state, path to .shp), ...] into out_base(.shp/.shx/.dbf/.prj/.cpg).

    `fuse` is the fuse module (passed in so this module can be imported without shapely).
    """
    # compare the CRS names like the local file check does, so .prj files that only differ in their
    # formatting do not block joining; fall back to the raw .prj text for CRS names that are not known
    states_by_crs: Dict[str, List[str]] = defaultdict(list)
    for state, path in sources:
        crs = shp_crs_name(path)
        states_by_crs[crs or read_text(os.path.splitext(path)[0] + '.prj')].append(state)
    if len(states_by_crs) > 1:
        details = '; '.join(
            f'{crs if crs.startswith("EPSG_") else "unknown"}: {", ".join(states)}'
            for crs, states in sorted(states_by_crs.items())
        )
        raise JoinSkipped(f'the states use different coordinate reference systems ({details}). Run geosync again to re-download them.')

    shapefile.VERBOSE = False  # pyshp would print notes about clipped polygons that only consist of holes
    # pyshp reads the encoding from the .cpg file
    readers = []
    try:
        for state, path in sources:  # opened inside try, so a failing file does not leak the ones opened before
            readers.append((state, shapefile.Reader(path)))
        encoding = readers[0][1].encoding
        shape_types = {r.shapeType for _, r in readers if len(r) > 0} or {readers[0][1].shapeType}
        if len(shape_types) > 1:
            raise JoinSkipped('the states have different geometry types')
        shape_type = shape_types.pop()
        if shape_type not in (shapefile.NULL, shapefile.POINT, shapefile.POLYLINE, shapefile.POLYGON, shapefile.MULTIPOINT):
            raise JoinSkipped('shapefiles with Z or M values are not supported for joining')
        kind = fuse.geometry_kind(shapefile.SHAPETYPE_LOOKUP.get(shape_type, ''))
        fields = merged_fields(readers)
        check_size(sources, fields, sum(len(r) for _, r in readers))
        field_names = [f[0] for f in fields]

        # Pass 1: find geom_ids that occur more than once
        counts: Counter = Counter()
        if 'geom_id' in field_names:
            for _, reader in readers:
                if 'geom_id' in [f[0] for f in reader.fields[1:]]:
                    counts.update(rec[0] for rec in reader.iterRecords(fields=['geom_id']) if rec[0] is not None)
        duplicates = {gid for gid, n in counts.items() if n > 1}

        # Pass 2: write all rows, collecting the pieces of duplicated geom_ids
        pieces: Dict[object, List] = defaultdict(list)
        with shapefile.Writer(out_base, shapeType=shape_type, encoding=encoding) as writer:
            for name, field_type, size, decimal in fields:
                writer.field(name, field_type, size, decimal)
            for _, reader in readers:
                for shape_record in reader.iterShapeRecords():
                    record = shape_record.record.as_dict()
                    gid = record.get('geom_id')
                    if gid in duplicates:
                        pieces[gid].append((shape_record.shape, record))
                        continue
                    writer.shape(shape_record.shape)
                    writer.record(*[record.get(name) for name in field_names])

            for group in pieces.values():
                first_shape, first_record = group[0]
                if kind == fuse.POINT or kind == fuse.OTHER:
                    writer.shape(first_shape)
                else:
                    geoms = [None if shape.shapeType == shapefile.NULL else fuse.from_geo_interface(shape) for shape, _ in group]
                    fused = fuse.fuse_group(geoms, kind)
                    if fused is None or fused.is_empty:
                        writer.null()
                    else:
                        writer.shape(fuse.to_geo_interface(fused))  # pyshp fixes the ring orientation
                writer.record(*[first_record.get(name) for name in field_names])
    finally:
        for _, reader in readers:
            reader.close()

    for ext in ('.prj', '.cpg'):
        source = os.path.splitext(sources[0][1])[0] + ext
        if os.path.exists(source):
            shutil.copyfile(source, out_base + ext)

