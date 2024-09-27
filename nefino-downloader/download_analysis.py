import os
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
    # subject to change as we eliminate the multi-scope analysis idea
    analyses = (os.path.join(download_dir, 'analyses'))
    return os.path.join(analyses, os.listdir(analyses)[0])


def unpack_items(zip_root: str, pk: str, started_at: datetime) -> None:
    """Unpacks the layers from the zip file."""
    journal = Journal.singleton()
    config = Config.singleton()
    if pk not in journal.analysis_states:
        print(f"Analysis {pk} not found in journal; skipping download")
        return
    state = journal.get_state_for_analysis(pk)
    for cluster in (f for f in os.listdir(zip_root) 
                    if f != 'analysis_area'
                    and os.path.isdir(os.path.join(zip_root, f))):
        cluster_dir = os.path.join(zip_root, cluster)
        layers = set()
        for file in os.listdir(cluster_dir):
            if journal.is_newer_than_saved(file, state, started_at):
                output_dir = config.output_path
                file_path = os.path.join(cluster_dir, file)
                if (os.path.exists(os.path.join(output_dir, file))):
                    os.remove(os.path.join(output_dir, file))
                move(file_path, output_dir)
                layer, ext = os.path.splitext(file)
                layers.add(layer)
        journal.record_layers_unpacked(layers, state, started_at)
    rmtree(zip_root)