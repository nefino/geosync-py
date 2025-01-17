import os
import re
from shutil import move, rmtree
from urllib.request import urlretrieve
import zipfile
from .get_downloadable_analyses import AnalysisResult
from .journal import Journal
from .config import Config
from .storage import get_download_directory 
from datetime import datetime

def download_analysis(analysis: AnalysisResult) -> None:
    """Downloads the analysis to the local machine."""
    journal = Journal.singleton()
    download_dir = get_download_directory(analysis.pk)
    download_file = os.path.join(download_dir, "download.zip")
    if not os.path.exists(download_file):
        urlretrieve(analysis.url.replace(" ", "%20"), download_file)
    with zipfile.ZipFile(download_file, 'r') as zip_ref:
        zip_ref.extractall(download_dir)
    zip_root = get_zip_root(download_dir)
    unpack_items(zip_root, analysis.pk, analysis.started_at)
    journal.record_analysis_synced(analysis.pk)


def get_zip_root(download_dir: str) -> str:
    """Returns the root directory of the extracted zip file."""
    # earlier we had a heavily nested structure
    return download_dir


FILE_NAME_PATTERN = re.compile(r"(?P<layer>^.*?)(?P<buffer>__[0-9]+m)?(?P<ext>\..{3,4}$)")

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
        print(f"Analysis {pk} not found in journal; skipping download")
        return

    state = journal.get_state_for_analysis(pk)

    # Get the analysis subfolder name (first and only directory in zip_root)
    analysis_subfolder = next(
        f for f in os.listdir(zip_root) if os.path.isdir(os.path.join(zip_root, f))
    )
    base_path = os.path.join(zip_root, analysis_subfolder)

    # Iterate through cluster folders inside the analysis subfolder
    for cluster in (
        f
        for f in os.listdir(base_path)
        if f != "analysis_area" and os.path.isdir(os.path.join(base_path, f))
    ):
        cluster_dir = os.path.join(base_path, cluster)
        layers = set()

        for file in os.listdir(cluster_dir):
            if journal.is_newer_than_saved(file, state, started_at):
                output_dir = os.path.join(config.output_path, state)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                file_path = os.path.join(cluster_dir, file)
                match = re.match(FILE_NAME_PATTERN, file)
                layer, ext = (match.group("layer"), match.group("ext"))

                # Remove any existing files for the same layer
                # this is important to avoid confusion if the pre-buffer changes
                for matching_file in (
                    f for f in os.listdir(output_dir) if f.startswith(layer)
                ):
                    output_match = re.match(FILE_NAME_PATTERN, matching_file)
                    # only remove files that match the layer and extension
                    # otherwise, only the last extension to be unpacked would survive
                    # also, we are double-checking the layer name here in case we have
                    # a layer name which starts with a different layer's name
                    if (
                        output_match.group("layer") == layer
                        and output_match.group("ext") == ext
                    ):
                        os.remove(os.path.join(output_dir, matching_file))

                move(file_path, output_dir)
                layers.add(layer)

        journal.record_layers_unpacked(layers, state, started_at)

    rmtree(zip_root)