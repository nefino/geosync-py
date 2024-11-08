

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

## Requirements

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
