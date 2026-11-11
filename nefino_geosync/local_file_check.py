"""Finds downloaded layer files that no longer match the configuration and marks them for re-download.

This covers files in a different CRS or output format than configured (e.g. after changing the
configuration) and, when joining is enabled, files without the geom_id column.
"""

from .config import Config, join_enabled, shapely_available
from .journal import Journal
from .layer_files import (
    EXTENSIONS,
    inspect_layer,
    list_layer_files,
    other_format,
    state_dirs,
)
from .parse_args import parse_args
from collections import defaultdict
from typing import Dict, Set

REASONS = {
    'format': 'they are stored in a different output format than configured',
    'crs': 'their coordinate reference system differs from the configured one',
    'geom_id': 'they have no geom_id column, which is needed for joining',
}


def mark_outdated_local_files(accessible: Dict[str, Set[str]]) -> None:
    """Marks layers whose local files do not match the configuration as outdated in the journal.

    Only layers the account can currently download in a state ({state: layers}) are considered,
    since others could not be downloaded again anyway.
    """
    config = Config.singleton()
    journal = Journal.singleton()
    verbose = parse_args().verbose
    fmt = str(config.output_format)
    if fmt not in EXTENSIONS:  # e.g. QGIS project formats, whose files are not checked
        return
    expected_crs = str(config.crs)
    # without shapely nothing is joined, so re-downloading for the geom_id would be in vain
    check_geom_id = join_enabled() and shapely_available()
    skip_layers = set(config.skip_layers)

    # reason -> state -> layers
    outdated: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

    for state, state_dir in state_dirs(config.output_path).items():
        downloadable = accessible.get(state, set()) - skip_layers
        current = {layer: path for layer, path in list_layer_files(state_dir, fmt).items() if layer in downloadable}
        for layer in list_layer_files(state_dir, other_format(fmt)):
            if layer in downloadable and layer not in current:
                outdated['format'][state].add(layer)

        for layer, path in current.items():
            try:
                crs, has_geom_id = inspect_layer(path, fmt)
                if crs is not None and crs != expected_crs:
                    outdated['crs'][state].add(layer)
                elif check_geom_id and not has_geom_id:
                    outdated['geom_id'][state].add(layer)
            except Exception as e:
                print(f'⚠️  Could not inspect {path}: {e}')

    if not outdated:
        return

    merged: Dict[str, Set[str]] = defaultdict(set)
    for reason, by_state in outdated.items():
        count = sum(len(layers) for layers in by_state.values())
        print(f'🔁 {count} layer file(s) in {", ".join(sorted(by_state))} will be downloaded again because {REASONS[reason]}.')
        for state, layers in by_state.items():
            merged[state] |= layers
            if verbose:
                for layer in sorted(layers):
                    print(f'    {state}: {layer}')
    journal.mark_layers_outdated(merged)
