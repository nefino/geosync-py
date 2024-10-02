from .journal import Journal
from .get_downloadable_analyses import get_downloadable_analyses
from .download_analysis import download_analysis
from sgqlc.endpoint.http import HTTPEndpoint
from .parse_args import parse_args

def download_completed_analyses(client: HTTPEndpoint) -> None:
    """Downloads the analyses that have been completed."""
    journal = Journal.singleton()
    args = parse_args()
    for analysis in get_downloadable_analyses(client):
        if not analysis.pk in journal.synced_analyses:
            if analysis.pk in journal.analysis_states:
                download_analysis(analysis)
                print(f"Downloaded analysis {analysis.pk}")
            else:
                print(f"Analysis {analysis.pk} missing metadata; skipping download")
        elif args.verbose:
            print(f"Analysis {analysis.pk} already downloaded")