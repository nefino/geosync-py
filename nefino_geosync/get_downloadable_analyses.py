from .api_client import get_analyses_operation
from .graphql_errors import check_errors
from .parse_args import parse_args
from .schema import DateTime, Status
from sgqlc.endpoint.http import HTTPEndpoint
from time import sleep
from typing import Generator, Protocol


# Let's give a quick description of what we want to be fetching.
# This does depend on what get_analysis_operation() actually does.
class AnalysisResult(Protocol):
    status: Status
    pk: str
    url: str
    started_at: DateTime


def get_downloadable_analyses(
    client: HTTPEndpoint,
) -> Generator[AnalysisResult, None, None]:
    """Yields analyses that are available for download.
    Polls for more analyses and yields them until no more are available.
    """
    verbose = parse_args().verbose
    op = get_analyses_operation()
    reported_pks = set()
    print('Checking for analyses to download...')
    while True:
        data = client(op)
        check_errors(data, 'Failed to fetch analysis status')
        analyses = op + data
        found_outstanding_analysis = False

        for analysis in analyses.analysis_metadata:
            if analysis.status == Status('PENDING') or analysis.status == Status('RUNNING'):
                if verbose:
                    print(f'Analysis {analysis.pk} is still pending or running.')
                found_outstanding_analysis = True
            if analysis.status == Status('SUCCESS') and analysis.pk not in reported_pks:
                reported_pks.add(analysis.pk)
                yield analysis

        if not found_outstanding_analysis:
            break
        if verbose:
            print('Waiting for more analyses to finish...')
        sleep(10)
