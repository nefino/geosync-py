import logging
from .download_analysis import download_analysis
from .get_downloadable_analyses import get_downloadable_analyses
from .journal import Journal
from .options import get_options
from sgqlc.endpoint.http import HTTPEndpoint

log = logging.getLogger(__name__)


def download_completed_analyses(client: HTTPEndpoint) -> None:
    """Downloads the analyses that have been completed."""
    journal = Journal.singleton()
    args = get_options()
    first_error = None
    for analysis in get_downloadable_analyses(client):
        if analysis.pk not in journal.synced_analyses:
            if analysis.pk in journal.analysis_states:
                if analysis.pk not in journal.analysis_requested_layers:
                    log.warning(f'⚠️  Warning: Analysis {analysis.pk} found but has no recorded requested layers. Skipping.')
                    continue
                try:
                    download_analysis(analysis)
                except Exception as e:
                    # shortcut: a temporary network failure also drops the analysis, so the state is computed again; keep it for a retry by error type if that becomes a cost
                    log.error(f'Downloading analysis {analysis.pk} failed, its layers are requested again by the next run: {e}')
                    journal.analysis_requested_layers.pop(analysis.pk, None)
                    journal.save_analysis_requested_layers()
                    first_error = first_error or e
                    continue
                log.info(f'Downloaded analysis {analysis.pk}')
        elif args.verbose:
            log.info(f'Analysis {analysis.pk} already downloaded')
    if first_error is not None:
        raise first_error
