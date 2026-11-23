"""Options of a sync run and its result, shared by the command line and the library interface."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class SyncOptions:
    """Options of a sync run. The defaults match running `nefino-geosync` without any flags."""

    # Show the configuration wizard again
    configure: bool = False
    # Only download finished analyses, do not start new ones
    resume: bool = False
    # Join the per-state files of each layer into one file in this run
    join: bool = False
    # Log more details
    verbose: bool = False
    # Wait until all started analyses have finished. If False, a run starts or downloads what is possible
    # right now and returns; analyses that are still running are downloaded by a later run.
    wait: bool = True
    # Only start analyses for these federal states (NUTS codes, e.g. DE1); None means all available states
    federal_states: Optional[List[str]] = None
    # Directory for the configuration and the journal; None means the platform's default app directory
    app_dir: Optional[str] = None
    # If False, never prompt and raise exceptions instead of printing errors and exiting
    interactive: bool = True


@dataclass
class AnalysisInfo:
    pk: str
    state: str
    started_at: Optional[datetime] = None


@dataclass
class SyncResult:
    """What a sync run did, and the state of the analyses in the journal afterwards."""

    started: List[AnalysisInfo] = field(default_factory=list)
    downloaded: List[AnalysisInfo] = field(default_factory=list)
    # Started analyses that are not finished yet or have not been downloaded yet
    pending: List[AnalysisInfo] = field(default_factory=list)
    # Started analyses that failed and were never downloaded
    failed: List[AnalysisInfo] = field(default_factory=list)


_current = SyncOptions()


def get_options() -> SyncOptions:
    """Returns the options of the current run."""
    return _current


def set_options(options: SyncOptions) -> None:
    """Sets the options of the current run."""
    global _current
    _current = options
