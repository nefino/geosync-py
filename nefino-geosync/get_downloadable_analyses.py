from time import sleep
from typing import Generator, Protocol
from .api_client import get_analyses_operation
from .schema import DateTime, Status
from .graphql_errors import check_errors
from sgqlc.endpoint.http import HTTPEndpoint

# Let's give a quick description of what we want to be fetching.
# This does depend on what get_analysis_operation() actually does.
class AnalysisResult(Protocol):
    status: Status
    pk: str
    url: str
    started_at: DateTime


def get_downloadable_analyses(client: HTTPEndpoint) -> Generator[AnalysisResult, None, None]:
    """Yields analyses that are available for download.
    Polls for more analyses and yields them until no more are available.
    """
    op = get_analyses_operation()
    reported_pks = set()
    while True:
        data = client(op)
        check_errors(data)
        analyses = op + data
        found_outstanding_analysis = False

        for analysis in analyses.analysis_metadata:
            if analysis.status == Status("PENDING") or analysis.status == Status("RUNNING"):
                found_outstanding_analysis = True
            if analysis.status == Status("SUCCESS") and analysis.pk not in reported_pks:
                reported_pks.add(analysis.pk)
                yield analysis

        if not found_outstanding_analysis:
            break
        sleep(10)
