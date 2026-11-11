import os
import zipfile
from .config import Config
from .get_downloadable_analyses import AnalysisResult
from .journal import Journal
from .layer_files import EXTENSIONS, other_format, parse_file_name
from collections import defaultdict
from .storage import get_download_directory
from datetime import datetime
from shutil import move, rmtree
from urllib.request import urlretrieve


def download_analysis(analysis: AnalysisResult) -> None:
    """Downloads the analysis to the local machine."""
    journal = Journal.singleton()
    download_dir = get_download_directory(analysis.pk)
    download_file = os.path.join(download_dir, 'download.zip')
    if os.path.exists(download_file):
        # remove any failed download
        os.remove(download_file)
    urlretrieve(analysis.url.replace(' ', '%20'), download_file)
    with zipfile.ZipFile(download_file, 'r') as zip_ref:
        zip_ref.extractall(download_dir)
    zip_root = get_zip_root(download_dir)
    unpack_items(zip_root, analysis.pk, analysis.started_at)
    journal.record_analysis_synced(analysis.pk)


def get_zip_root(download_dir: str) -> str:
    """Returns the root directory of the extracted zip file."""
    # earlier we had a heavily nested structure
    return download_dir


def unpack_items(zip_root: str, pk: str, started_at: datetime) -> None:
    """
    Unpacks the layers from the zip file.

    Args:
        zip_root: Path to the root directory of the extracted zip
        pk: Primary key of the analysis
        started_at: Timestamp when the analysis started
    """
    journal = Journal.singleton()
    config = Config.singleton()

    if pk not in journal.analysis_states:
        print(f'Analysis {pk} not found in journal; skipping download')
        return

    state = journal.get_state_for_analysis(pk)
    base_path = get_base_path(zip_root)
    output_dir = os.path.join(config.output_path, state)
    unpacked_layers = {}  # layer -> output format of its unpacked files
    zip_layers = set()  # all layers with a file in the ZIP, unpacked or not

    # the files that were there before unpacking, by (layer, extension), so the folder is only listed once
    existing = defaultdict(list)
    if os.path.isdir(output_dir):
        for file_name in os.listdir(output_dir):
            parsed = parse_file_name(file_name)
            if parsed:
                existing[parsed].append(file_name)

    # Iterate through cluster folders inside the analysis subfolder
    for cluster in (
        f for f in os.listdir(base_path) if f != 'analysis_area' and os.path.isdir(os.path.join(base_path, f))
    ):
        cluster_dir = os.path.join(base_path, cluster)

        for file in os.listdir(cluster_dir):
            parsed = parse_file_name(file)
            if parsed is None:
                print(f'⚠️  Skipping {file} in {cluster}: not a layer file')
                continue
            layer, ext = parsed
            zip_layers.add(layer)
            if journal.is_newer_than_saved(layer, state, started_at):
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                file_path = os.path.join(cluster_dir, file)
                # only the main file decides the format; sidecar files like .prj must not
                fmt = next((fmt for fmt, extensions in EXTENSIONS.items() if ext == extensions[0]), None)
                if fmt or layer not in unpacked_layers:
                    unpacked_layers[layer] = fmt

                # Replace the existing files of the same layer and extension (any pre-buffer suffix)
                # this is important to avoid confusion if the pre-buffer changes; only the same extension
                # is replaced, otherwise only the last extension to be unpacked would survive
                for old_file in existing.pop((layer, ext), []):
                    os.remove(os.path.join(output_dir, old_file))
                # e.g. the same file in two cluster folders: the first copy was moved after the listing above
                if os.path.exists(os.path.join(output_dir, file)):
                    os.remove(os.path.join(output_dir, file))

                move(file_path, output_dir)

    for layer, fmt in sorted(unpacked_layers.items()):
        if not fmt:
            continue
        # Older files of the same layer and format that the new delivery does not have (e.g. a .cpg) belong to the
        # replaced version and would no longer match it, e.g. a .cpg with another encoding than the new .dbf
        for ext in EXTENSIONS[fmt]:
            for old_file in existing.pop((layer, ext), []):
                os.remove(os.path.join(output_dir, old_file))
        # Files in the other output format (left over from a format change) are kept; deleting them is up to the user
        if any((layer, ext) in existing for ext in EXTENSIONS[other_format(fmt)]):
            print(f'ℹ️  {layer} in {state} also has files in the {other_format(fmt)} format; delete them if not needed')

    # Requested layers without a file in the ZIP are probably empty in this state now. Their older files are kept,
    # since deleting them cannot be undone, but they are probably outdated.
    for layer in sorted(journal.analysis_requested_layers.get(pk, set()) - zip_layers):
        old_files = sorted(f for (old_layer, _), names in existing.items() if old_layer == layer for f in names)
        if old_files and journal.is_newer_than_saved(layer, state, started_at):
            print(
                f'⚠️  No file was delivered for {layer} in {state}, so it probably has no data there anymore. '
                f'The existing file(s) {", ".join(old_files)} were kept but are probably outdated.'
            )

    # Update the journal to mark layers as updated. We might have empty layers so we do set all requested layers as
    # updated.
    if pk in journal.analysis_requested_layers:
        layers_to_mark_updated = journal.analysis_requested_layers[pk]
    else:
        # Fallback: extract layer names from the ZIP file structure as a safety net
        print(f'⚠️  Warning: No recorded requested layers for analysis {pk}. Extracting from ZIP structure.')
        # the files were moved out of the cluster folders above, so use the layers found while unpacking
        layers_to_mark_updated = set(zip_layers)

    print(f'Recording {len(layers_to_mark_updated)} requested layers as updated for state {state}')

    journal.record_layers_unpacked(layers_to_mark_updated, state, started_at)
    rmtree(zip_root)


def get_base_path(zip_root: str) -> str:
    """
    Returns the base path for the analysis files in the ZIP structure.

    Handles two different ZIP structures:
    - Old structure: analysis_summary.xlsx and cluster folders directly in ZIP root
    - New structure: analysis_summary.xlsx and cluster folders inside a dedicated subfolder

    The presence of analysis_summary.xlsx in the root directory is used to determine
    which structure we're dealing with.

    Args:
        zip_root: Path to the root directory of the extracted ZIP file

    Returns:
        str: Path to the directory containing the cluster folders and analysis_summary.xlsx
    """
    if 'analysis_summary.xlsx' in os.listdir(zip_root):
        # Old structure - use zip_root
        return zip_root
    # Get the analysis subfolder name (first and only directory in zip_root)
    analysis_subfolder = next(f for f in os.listdir(zip_root) if os.path.isdir(os.path.join(zip_root, f)))
    return os.path.join(zip_root, analysis_subfolder)
