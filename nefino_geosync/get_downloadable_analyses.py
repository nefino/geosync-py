import logging
from .api_client import fetch_analyses
from .journal import Journal
from .options import get_options
from .schema import DateTime, Status
from sgqlc.endpoint.http import HTTPEndpoint
from time import sleep
from typing import Generator, Protocol

log = logging.getLogger(__name__)


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
    """Yields the analyses from the journal that are available for download.
    Polls for more analyses and yields them until none of them is pending or running anymore,
    or checks only once when running without waiting.
    Analyses of other clients using the same API key are ignored.
    """
    options = get_options()
    journal = Journal.singleton()
    reported_pks = set()
    log.info('Checking for analyses to download...')
    while True:
        found_outstanding_analysis = False

        for analysis in fetch_analyses(client):
            if analysis.pk not in journal.analysis_states:
                continue
            if analysis.status == Status('PENDING') or analysis.status == Status('RUNNING'):
                if options.verbose:
                    log.info(f'Analysis {analysis.pk} is still pending or running.')
                found_outstanding_analysis = True
            if analysis.status == Status('SUCCESS') and analysis.pk not in reported_pks:
                reported_pks.add(analysis.pk)
                yield analysis

        if not found_outstanding_analysis or not options.wait:
            break
        if options.verbose:
            log.info('Waiting for more analyses to finish...')
        sleep(10)
