import json
import os
from typing import List

import questionary
from .parse_args import parse_args
from .schema import CRSType, OutputObjectType
from .storage import get_app_directory


class Config:
    """This class handles storing and retrieving user preferences."""
    # This is a singleton class. There should only be one instance of Config.
    _instance = None

    @classmethod
    def singleton(cls):
        """Returns the singleton instance of Journal."""
        if not cls._instance:
            cls._instance = Config()
        return cls._instance
    
    @property
    def _config_file_path(self) -> str:
        """Returns the path to the config file."""
        return os.path.join(get_app_directory(), "config.json")

    def __init__(self):
        if Config._instance:
            raise Exception("Config is a singleton class. Use Config.singleton() to get the instance.")
        self.already_prompted = False
        if not os.path.exists(self._config_file_path):
            self.run_config_prompts(missing_config=True)
        else:
            with open(self._config_file_path, "r") as f:
                config = json.load(f)
                self.output_path: str = config['output_path']
                self.output_format: OutputObjectType = OutputObjectType(
                    config['output_format'])
                self.crs: CRSType = CRSType(config['crs'])
                self.skip_layers: List[str] = [name.strip() for name in config['skip_layers'] if name.strip()]
                self.api_key: str = config['api_key']
                self.join_layers: bool = config.get('join_layers', False)
    
    def save(self):
        """Saves the config to a file."""
        with open(self._config_file_path, "w") as f:
            json.dump({
                'output_path': self.output_path,
                'output_format': self.output_format,
                'skip_layers': self.skip_layers,
                'api_key': self.api_key,
                'crs': self.crs,
                'join_layers': self.join_layers,
            }, f)

    def run_config_prompts(self, missing_config: bool = False):
        """Runs the configuration wizard."""
        self.output_path = questionary.text(
            "Where do you want to collect downloaded geodata files?",
            default=os.path.join(get_app_directory(), "newestData") \
                if missing_config else self.output_path).ask()
        self.output_format = OutputObjectType(
            questionary.select(
                "What format do you want to use for the output files?",
                choices=['GPKG', 'SHP'],
                default='GPKG' if missing_config else self.output_format
                ).ask())
        self.crs = CRSType(
            questionary.select(
                "What coordinate reference system do you want to use?",
                choices=[crs for crs in CRSType],
                default='EPSG_4326' if missing_config else self.crs
            ).ask())
        self.join_layers = questionary.confirm(
            "Do you want to join the per-state files of each layer into one file?",
            instruction="Joined files are written to the 'joined' folder. Requires: pip install \"nefino-geosync[join]\"",
            default=False if missing_config else self.join_layers).ask()
        if self.join_layers and not shapely_available():
            print('⚠️  Joining needs shapely. Please install it with: pip install "nefino-geosync[join]"')
        self.api_key = questionary.text(
            "Enter your API key:",
            default="" if missing_config else self.api_key).ask()
        skip_layer_string = questionary.text(
            "Enter the names of any layers you want to skip downloading, separated by commas.",
            instruction="Layer names can be found on https://docs.nefino.li/geo.",
            default="" if missing_config else ",".join(self.skip_layers)).ask()
        self.skip_layers = [name.strip() for name in skip_layer_string.split(",") if name.strip()]
        self.save()
        self.already_prompted = True


def shapely_available() -> bool:
    """Returns whether the optional shapely dependency needed for joining is installed."""
    try:
        import shapely  # noqa: F401
    except ImportError:
        return False
    return True


def join_enabled() -> bool:
    """Returns whether layers should be joined in this run (config setting or --join flag)."""
    return Config.singleton().join_layers or parse_args().join
