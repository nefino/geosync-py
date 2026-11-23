import argparse
from .options import SyncOptions
from typing import List, Optional


def parse_args(argv: Optional[List[str]] = None) -> SyncOptions:
    """Parses the command line arguments into the options of a sync run."""
    parser = argparse.ArgumentParser(
        prog="Nefino GeoSync",
        description='Download available geodata from the Nefino API.',
        epilog='If you have further questions please reach out to us! The maintainers for this tool can be found on https://github.com/nefino/geosync-py.')
    parser.add_argument('-c', '--configure', action='store_true', help='Edit your existing configuration. The first-run wizard will be shown again, with your existing configuration pre-filled.')
    parser.add_argument('-r', '--resume', action='store_true', help='Resume checking for completed analyses and downloading them. This will skip the analysis start step.')
    parser.add_argument('--join', action='store_true', help='Join the per-state files of each layer into one file in this run, even if joining is not enabled in your configuration. Requires: pip install "nefino-geosync[join]".')
    parser.add_argument('-v', '--verbose', action='store_true', help='Print more information to the console.')
    parser.add_argument('--no-wait', dest='wait', action='store_false', help='Do not wait for analyses to finish. Starts or downloads what is possible right now and exits; analyses that are still running are downloaded by a later run, e.g. with --resume.')
    parser.add_argument('--federal-states', nargs='+', metavar='NUTS_CODE', help='Only start analyses for these federal states, given as NUTS codes (e.g. DE1 DE2, see https://de.wikipedia.org/wiki/NUTS:DE).')
    parser.add_argument('--app-dir', help='Directory for the configuration and the journal of downloaded analyses, instead of the default app directory.')
    parser.add_argument('--non-interactive', dest='interactive', action='store_false', help='Never prompt and raise errors instead of printing them and exiting, e.g. when running as an automated job. Requires an existing configuration.')
    return SyncOptions(**vars(parser.parse_args(argv)))
