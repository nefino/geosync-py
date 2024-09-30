import json
import os
import re
from datetime import datetime
from typing import Dict, Set
from .storage import get_app_directory

class Journal:
    """Handles metadata about analyses for efficient downloading."""

    # This is a singleton class. There should only be one instance of Journal.
    _instance = None

    @classmethod
    def singleton(cls):
        """Returns the singleton instance of Journal."""
        if not cls._instance:
            cls._instance = Journal()
        return cls._instance

    def __init__(self):
        if Journal._instance:
            raise Exception("Journal is a singleton class. Use Journal.singleton() to get the instance.")
        # Mapping from analysis pk to the state where the analysis was started
        self.analysis_states: Dict[str, str] = dict()

        # Mapping from layer name to where it was last updated and when
        self.layer_last_updates: Dict[str, Dict[str, datetime]] = dict()

        # Record which analyses have been successfully started
        self.synced_analyses: Set[str] = set()

        self.load_analysis_states()
        self.load_layer_last_updates()
        self.load_synced_analyses()

    def save_analysis_states(self):
        """Saves the analysis states to a file."""
        with open(os.path.join(get_app_directory(), "analysis_states.json"), "w") as f:
            json.dump(self.analysis_states, f)
    
    def load_analysis_states(self):
        """Loads the analysis states from a file."""
        try:
            with open(os.path.join(get_app_directory(), "analysis_states.json"), "r") as f:
                self.analysis_states = json.load(f)
        except FileNotFoundError:
            # we already have an empty dictionary as the field value
            print("No saved analysis states found.")
    
    def save_layer_last_updates(self):
        """Saves the layer last updates to a file."""
        with open(os.path.join(get_app_directory(), "layer_last_updates.json"), "w") as f:
            json.dump(self.layer_last_updates, f, default=lambda x: x.isoformat())

    def load_layer_last_updates(self):
        """Loads the layer last updates from a file."""
        try:
            with open(os.path.join(get_app_directory(), "layer_last_updates.json"), "r") as f:
                self.layer_last_updates = json.load(f)
                for cluster in self.layer_last_updates.values():
                    for state, timestamp in cluster.items():
                        cluster[state] = datetime.fromisoformat(timestamp) if timestamp else None
        except FileNotFoundError:
            # we already have an empty dictionary as the field value
            print("No saved layer last updates found.")
    
    def save_synced_analyses(self):
        """Saves the list of processed analyses to a file."""
        with open(os.path.join(get_app_directory(), "synced_analyses.json"), "w") as f:
            json.dump(list(self.synced_analyses), f)
    
    def load_synced_analyses(self):
        """Loads the list of processed analyses from a file."""
        try:
            with open(os.path.join(get_app_directory(), "synced_analyses.json"), "r") as f:
                self.synced_analyses = set(json.load(f))
        except FileNotFoundError:
            # we already have an empty set as the field value
            print("No saved downloaded analyses found.")

    def record_analyses_requested(self, start_analyses_result):
        """Records the analyses that have been started, and where they were started."""
        pattern = r"^startAnalysis_(?P<state>DE[1-9A-G])$"
        for alias, analysis_metadata in start_analyses_result.__dict__.items(): 
            match = re.match(pattern, alias)
            if not match:
                continue
            state = match.group("state")
            # record where the analysis was started
            self.analysis_states[analysis_metadata.pk] = state
        self.save_analysis_states()
    
    def record_layers_unpacked(self, layers: Set[str], state: str, started_at: datetime):
        """Records the layers that have been unpacked, and when they were last updated."""
        print(f"Recording layers {layers} as unpacked for state {state}")
        for layer in layers:
            if layer not in self.layer_last_updates:
                self.layer_last_updates[layer] = dict()
            self.layer_last_updates[layer][state] = started_at
        self.save_layer_last_updates()
    
    def get_state_for_analysis(self, pk: str) -> str:
        """Returns the state where the analysis was started."""
        return self.analysis_states[pk]
    
    def is_newer_than_saved(self, layer: str, state: str, timestamp: datetime) -> bool:
        """Checks if the layer needs to be unpacked."""
        if layer not in self.layer_last_updates:
            return True
        if state not in self.layer_last_updates[layer]:
            return True
        if not self.layer_last_updates[layer][state]:
            return True
        return self.layer_last_updates[layer][state] < timestamp
    
    def record_analysis_synced(self, pk: str):
        """Records that the analysis has been downloaded and unpacked."""
        self.synced_analyses.add(pk)
        self.save_synced_analyses()
