import json
import os
from typing import List

import questionary
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
                self.skip_layers: List[str] = config['skip_layers']
                self.api_key: str = config['api_key']
    
    def save(self):
        """Saves the config to a file."""
        with open(self._config_file_path, "w") as f:
            json.dump({
                'output_path': self.output_path,
                'output_format': self.output_format,
                'skip_layers': self.skip_layers,
                'api_key': self.api_key,
                'crs': self.crs
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
                instruction="Changing this value after first run will require wiping the downloaded data.",
                choices=['GPKG', 'SHP'],
                default='GPKG' if missing_config else self.output_format
                ).ask())
        self.crs = CRSType(
            questionary.select(
                "What coordinate reference system do you want to use?",
                choices=[crs for crs in CRSType],
                default='EPSG_4326' if missing_config else self.crs
            ).ask())
        self.api_key = questionary.text(
            "Enter your API key:",
            default="" if missing_config else self.api_key).ask()
        skip_layer_string = questionary.text(
            "Enter the names of any layers you want to skip downloading, separated by commas.",
            instruction="Layer names can be found on https://docs.nefino.li/geo.",
            default="" if missing_config else ",".join(self.skip_layers)).ask()
        self.skip_layers = [] if skip_layer_string == "" else skip_layer_string.split(",")
        self.save()
        self.already_prompted = True
