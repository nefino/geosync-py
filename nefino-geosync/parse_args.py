import argparse

def parse_args(cached=[]):
    if len(cached) > 0:
        return cached[0]
    parser = argparse.ArgumentParser(
        prog="Nefino GeoSync",
        description='Download available geodata from the Nefino API.',
        epilog='If you have further questions please reach out to us! The maintainers for this tool can be found on https://github.com/nefino/geosync-py.')
    parser.add_argument('-c', '--configure', action='store_true', help='Edit your existing configuration. The first-run wizard will be shown again, with your existing configuration pre-filled.')
    parser.add_argument('-r', '--resume', action='store_true', help='Resume checking for completed analyses and downloading them. This will skip the analysis start step.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Print more information to the console.')
    args = parser.parse_args()
    cached.append(args)
    return args