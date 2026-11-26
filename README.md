

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

## Running as an automated job

For scheduled jobs that should neither prompt nor block, the sync can be split into two runs, e.g. one in the evening that starts the analyses and one at night that downloads them:

```bash
nefino-geosync --non-interactive --no-wait            # start analyses, download what is already finished
nefino-geosync --non-interactive --no-wait --resume   # only download finished analyses
```

- `--no-wait` does not wait for running analyses; a later run downloads them. It also starts no second analysis for a federal state whose previous analysis has not been downloaded yet, i.e. is still `PENDING` or `RUNNING`, or finished and not downloaded. Every run first downloads the finished analyses of earlier runs.
- `--non-interactive` never prompts and raises errors instead of printing them. It needs an existing configuration (see below).
- `--federal-states DE1 DE2` only starts analyses for the given federal states (NUTS codes, not case-sensitive). When starting analyses, a code outside your account's analysis areas is an error.
- `--app-dir PATH` keeps the configuration and the journal in `PATH` instead of the default app directory. It also holds the session logs, the temporary `downloads/` folder and, for a new configuration, the default output folder `newestData`.

The results of an analysis can be downloaded for 7 days after it finished. If a download fails, e.g. because a split job downloaded too late, the run ends with an error and the next run without `--resume` requests its layers again.

Without a terminal, create the configuration file `config.json` in the app directory before the first run:

```json
{
    "output_path": "/data/nefino/newestData",
    "output_format": "GPKG",
    "crs": "EPSG_25832",
    "skip_layers": [],
    "api_key": "<your API key>",
    "join_layers": false
}
```

- `output_format`: `GPKG` or `SHP`
- `crs`: one of `EPSG_25832`, `EPSG_25833`, `EPSG_3035`, `EPSG_4326`, `EPSG_5243`
- `skip_layers`: names of layers that are never downloaded
- `join_layers` (optional, default `false`): join the per-state files of each layer into one file

The same is available from Python. Output is written through the standard `logging` module under the `nefino_geosync` logger, so it ends up in the application's logging:

```python
from nefino_geosync import SyncOptions, sync

result = sync(SyncOptions(wait=False, app_dir='/data/nefino'))
for analysis in result.failed:
    print(f'Analysis {analysis.pk} for {analysis.state} failed')
```

`sync()` always runs non-interactively: it never prompts and raises errors instead of exiting. A `GraphQLError` carries the raw `errors` list of the response in `errors`, e.g. to tell an invalid API key (`extensions.nefino_type == 'AuthTokenInvalid'`) from a server error.

The result lists the analyses this run started and downloaded, and which of the analyses of this run and of earlier runs not downloaded yet are still pending or have failed.

`sync()` uses process-wide state (the options, the configuration and the journal), so do not call it from two threads at the same time. Analyses that stay `PENDING` or `RUNNING` are not timed out by the client.

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
