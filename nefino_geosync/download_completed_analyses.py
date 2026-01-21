from .download_analysis import download_analysis
from .get_downloadable_analyses import get_downloadable_analyses
from .journal import Journal
from .parse_args import parse_args
from sgqlc.endpoint.http import HTTPEndpoint


def download_completed_analyses(client: HTTPEndpoint) -> None:
    """Downloads the analyses that have been completed."""
    journal = Journal.singleton()
    args = parse_args()
    for analysis in get_downloadable_analyses(client):
        if analysis.pk not in journal.synced_analyses:
            if analysis.pk in journal.analysis_states:
                if analysis.pk not in journal.analysis_requested_layers:
                    print(f'⚠️  Warning: Analysis {analysis.pk} found but has no recorded requested layers. Skipping.')
                    continue
                download_analysis(analysis)
                print(f'Downloaded analysis {analysis.pk}')
        elif args.verbose:
            print(f'Analysis {analysis.pk} already downloaded')
