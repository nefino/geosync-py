"""Joins the per-state files of each layer into one file per layer in <output_path>/joined.

Pieces of a geometry that were cut by federal state boundaries share the same geom_id and are
fused back into one feature. Needs the optional shapely dependency: pip install "nefino-geosync[join]".
"""

import json
import os
from .config import Config
from .layer_files import (
    EXTENSIONS,
    JoinSkipped,
    component_files,
    list_layer_files,
    state_dirs,
)
from .parse_args import parse_args
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Increase when the join algorithm changes, so existing joined files are rebuilt.
JOIN_VERSION = 1
JOINED_DIR_NAME = 'joined'
STATE_FILE_NAME = '.join_state.json'
TMP_PREFIX = '.tmp_'


def join_all_layers(accessible: Dict[str, Set[str]]) -> None:
    """Builds or updates the joined file of every layer whose per-state files changed.

    Only files of layers the account can currently access in a state ({state: layers}) are joined.
    """
    try:
        from . import fuse
    except ImportError:
        print('❌ Joining layers needs shapely, which is not installed. Install it with: pip install "nefino-geosync[join]"')
        return

    config = Config.singleton()
    verbose = parse_args().verbose
    fmt = str(config.output_format)
    if fmt not in EXTENSIONS:
        print(f'❌ Joining layers is not supported for the output format {fmt}. Use GPKG or SHP.')
        return
    joined_dir = os.path.join(config.output_path, JOINED_DIR_NAME)

    # skipped layers are no longer updated, so their joined files are not updated either
    skip_layers = set(config.skip_layers)
    accessible = {state: layers - skip_layers for state, layers in accessible.items()}
    layers = collect_layers(config.output_path, fmt, accessible)

    os.makedirs(joined_dir, exist_ok=True)
    remove_temp_files(joined_dir)
    join_state = load_join_state(joined_dir)

    joined, skipped, up_to_date = 0, 0, 0
    for layer, sources in sorted(layers.items()):
        out_name = os.path.basename(sources[0][1])
        entry = {
            'format': fmt,
            'version': JOIN_VERSION,
            'files': {state: os.path.basename(path) for state, path in sources},
        }
        out_main = os.path.join(joined_dir, out_name)
        if join_state.get(layer) == entry and not is_stale(out_main, sources, fmt):
            up_to_date += 1
            if verbose:
                print(f'    ✅ {layer} is up to date')
            continue
        try:
            if len({os.path.basename(path) for _, path in sources}) > 1:
                raise JoinSkipped(
                    'the states were delivered with different pre-buffers (see the file names). '
                    'Please contact Nefino support: https://www.nefino.de/kontakt'
                )
            print(f'🧩 Joining {layer} from {len(sources)} state(s)...')
            build_layer(sources, joined_dir, out_name, fmt, fuse)
            join_state[layer] = entry
            save_join_state(joined_dir, join_state)
            joined += 1
        except Exception as e:
            reason = 'Skipped joining' if isinstance(e, JoinSkipped) else 'Could not join'
            # existing joined files are kept, but they are tried again in the next run
            join_state.pop(layer, None)
            save_join_state(joined_dir, join_state)
            kept = ' The existing joined file was kept but does not include the latest changes.'
            print(f'⚠️  {reason} {layer}: {e}' + (kept if os.path.exists(out_main) else ''))
            skipped += 1
        finally:
            remove_temp_files(joined_dir)

    print(f'🧩 Joined {joined} layer(s), {up_to_date} already up to date, {skipped} skipped. Files are in {joined_dir}')


def collect_layers(output_path: str, fmt: str, accessible: Dict[str, Set[str]]) -> Dict[str, List[Tuple[str, str]]]:
    """Returns {layer: [(state, main file), ...]} for all accessible layers, sorted by state."""
    layers: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for state, state_dir in state_dirs(output_path).items():
        for layer, path in list_layer_files(state_dir, fmt).items():
            if layer in accessible.get(state, ()):
                layers[layer].append((state, path))
    return dict(layers)


def is_stale(out_main: str, sources: List[Tuple[str, str]], fmt: str) -> bool:
    """True if the joined file is missing or older than any of the per-state files."""
    out_files = [os.path.splitext(out_main)[0] + ext for ext in EXTENSIONS[fmt][:3 if fmt == 'SHP' else 1]]
    if not all(os.path.exists(f) for f in out_files):
        return True
    built = min(os.path.getmtime(f) for f in out_files)
    newest_source = max(os.path.getmtime(f) for _, path in sources for f in {path, *component_files(path, fmt)})
    return newest_source > built


def build_layer(sources: List[Tuple[str, str]], joined_dir: str, out_name: str, fmt: str, fuse) -> None:
    """Joins into temporary files and moves them into place once complete."""
    base, _ = os.path.splitext(out_name)
    tmp_base = os.path.join(joined_dir, TMP_PREFIX + base)
    if fmt == 'GPKG':
        from .join_gpkg import join_layer

        join_layer(sources, tmp_base + '.gpkg', fuse)
    else:
        from .join_shp import join_layer

        join_layer(sources, tmp_base, fuse)
    for ext in EXTENSIONS[fmt]:
        target = os.path.join(joined_dir, base + ext)
        if os.path.exists(tmp_base + ext):
            os.replace(tmp_base + ext, target)
        elif os.path.exists(target):  # e.g. an older .cpg that would not match the new .dbf
            os.remove(target)


def remove_temp_files(joined_dir: str) -> None:
    for file_name in os.listdir(joined_dir):
        if file_name.startswith(TMP_PREFIX):
            try:
                os.remove(os.path.join(joined_dir, file_name))
            except OSError as e:  # e.g. locked on Windows; it is removed in a later run
                print(f'⚠️  Could not remove the temporary file {file_name}: {e}')


def load_join_state(joined_dir: str) -> dict:
    try:
        with open(os.path.join(joined_dir, STATE_FILE_NAME)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_join_state(joined_dir: str, join_state: dict) -> None:
    path = os.path.join(joined_dir, STATE_FILE_NAME)
    with open(path + '.new', 'w') as f:
        json.dump(join_state, f, indent=2, sort_keys=True)
    os.replace(path + '.new', path)
