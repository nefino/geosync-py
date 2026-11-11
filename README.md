

# <img src="https://nefino.li/favicon.ico" alt="Nefino Logo" width="25" height="25"/> Nefino Geosync
[![PyPI version](https://img.shields.io/pypi/v/nefino-geosync.svg)](https://pypi.org/project/nefino-geosync/)
[![Python versions](https://img.shields.io/pypi/pyversions/nefino-geosync.svg)](https://pypi.org/project/nefino-geosync/)
[![License](https://img.shields.io/pypi/l/nefino-geosync.svg)](https://github.com/your-org/geosync-py/blob/main/LICENSE)

Python package to download geographical data from Nefino.LI Geo. It uses the Nefino.LI GraphQL API that is accessible through [api.nefino.li/external](https://api.nefino.li/external).

## Installation

```bash
pip install nefino-geosync
```

## Quick Start

1. Get your API key from [nefino.li/account/api-keys](https://nefino.li/account/api-keys)
2. Run to configure settings (they are then saved) and sync data:
   ```bash
   nefino-geosync
   ```
3. Resume interrupted downloads:
   ```bash
   nefino-geosync --resume
   ```
4. Set up a scheduled task to run nefino-geosync regularly

## Joining layers into one file

Layers are downloaded per federal state into `<output folder>/<state>/` (e.g. `DE1`, `DE2`, …). Optionally, geosync can also join the files of each layer into one file covering all your federal states:

1. Install the optional dependency (no GDAL needed):
   ```bash
   pip install "nefino-geosync[join]"
   ```
2. Enable joining in the configuration (`nefino-geosync --configure`), or join for a single run with `nefino-geosync --join`.

The joined files are written to `<output folder>/joined/` with the same file names as the per-state files, which are kept as they are. Features that were cut into several pieces by state boundaries (rows with the same `geom_id`) are fused back into one feature, so polygon and line layers are stored as multi-polygons and multi-lines. Joined files are only rebuilt when one of the per-state files has changed.

Joining works for both output formats. Shapefiles are limited to 2 GB, so very large layers are skipped with a warning when using the SHP format; use GPKG for those.

## Changing the output format or coordinate reference system

If you change the output format or the coordinate reference system with `nefino-geosync --configure`, the next run downloads the affected layers again in the new format or coordinate reference system. Files in the old format are kept, so you can delete them yourself once you no longer need them.

## Requirements

- Python 3.11 or newer (3.11, 3.12 and 3.13 are tested)
- Active Nefino.LI API contract
- Sufficient disk space for geodata storage

> **Note**: To conserve resources and prevent conflicts, run `nefino-geosync` on only one computer.

## Links

- [Nefino](https://nefino.de)
- [Nefino.LI](https://nefino.li)
- [Nefino.LI Documentation](https://docs.nefino.li)

## Help

- Open an [issue](https://github.com/nefino/geosync-py/issues) for bug reports or feature requests
- Contact [Nefino](https://www.nefino.de/kontakt) for account-related inquiries
