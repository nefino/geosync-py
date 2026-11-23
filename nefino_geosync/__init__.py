"""Nefino GeoSync: download geodata from the Nefino API, from the command line or from Python."""

import logging
from .options import AnalysisInfo, SyncOptions, SyncResult
from .run import sync

__all__ = ['AnalysisInfo', 'SyncOptions', 'SyncResult', 'sync']

# a library leaves logging to the application; the command line sets up its own console output
logging.getLogger(__name__).addHandler(logging.NullHandler())
