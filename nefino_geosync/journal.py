import json
import os
import re
from .storage import get_app_directory
from datetime import datetime, timezone
from typing import Dict, Set


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

    def __init__(self) -> None:
        if Journal._instance:
            raise Exception('Journal is a singleton class. Use Journal.singleton() to get the instance.')
        # Mapping from analysis pk to the state where the analysis was started
        self.analysis_states: Dict[str, str] = dict()

        # Mapping from analysis pk to the layers that were requested
        self.analysis_requested_layers: Dict[str, Set[str]] = dict()

        # Mapping from layer name to where it was last updated and when
        self.layer_last_updates: Dict[str, Dict[str, datetime]] = dict()

        # Record which analyses have been successfully started
        self.synced_analyses: Set[str] = set()

        # Track the last successful geosync run for changelog queries
        self.last_geosync_run: datetime = None

        self.load_analysis_states()
        self.load_analysis_requested_layers()
        self.load_layer_last_updates()
        self.load_synced_analyses()
        self.load_last_geosync_run()

    def save_analysis_states(self) -> None:
        """Saves the analysis states to a file."""
        with open(os.path.join(get_app_directory(), 'analysis_states.json'), 'w') as f:
            json.dump(self.analysis_states, f)

    def load_analysis_states(self) -> None:
        """Loads the analysis states from a file."""
        try:
            with open(os.path.join(get_app_directory(), 'analysis_states.json'), 'r') as f:
                self.analysis_states = json.load(f)
        except FileNotFoundError:
            # we already have an empty dictionary as the field value
            print('No saved analysis states found.')

    def save_analysis_requested_layers(self) -> None:
        """Saves the analysis requested layers to a file."""
        # Convert sets to lists for JSON serialization
        serializable_data = {pk: list(layers) for pk, layers in self.analysis_requested_layers.items()}
        with open(os.path.join(get_app_directory(), 'analysis_requested_layers.json'), 'w') as f:
            json.dump(serializable_data, f)

    def load_analysis_requested_layers(self) -> None:
        """Loads the analysis requested layers from a file."""
        try:
            with open(os.path.join(get_app_directory(), 'analysis_requested_layers.json'), 'r') as f:
                data = json.load(f)
                # Convert lists back to sets
                self.analysis_requested_layers = {pk: set(layers) for pk, layers in data.items()}
        except FileNotFoundError:
            # we already have an empty dictionary as the field value
            print('No saved analysis requested layers found.')

    def save_layer_last_updates(self) -> None:
        """Saves the layer last updates to a file."""
        with open(os.path.join(get_app_directory(), 'layer_last_updates.json'), 'w') as f:
            json.dump(self.layer_last_updates, f, default=lambda x: x.isoformat())

    def load_layer_last_updates(self) -> None:
        """Loads the layer last updates from a file."""
        try:
            with open(os.path.join(get_app_directory(), 'layer_last_updates.json'), 'r') as f:
                self.layer_last_updates = json.load(f)
                for cluster in self.layer_last_updates.values():
                    for state, timestamp in cluster.items():
                        cluster[state] = datetime.fromisoformat(timestamp) if timestamp else None
        except FileNotFoundError:
            # we already have an empty dictionary as the field value
            print('No saved layer last updates found.')

    def save_synced_analyses(self) -> None:
        """Saves the list of processed analyses to a file."""
        with open(os.path.join(get_app_directory(), 'synced_analyses.json'), 'w') as f:
            json.dump(list(self.synced_analyses), f)

    def load_synced_analyses(self) -> None:
        """Loads the list of processed analyses from a file."""
        try:
            with open(os.path.join(get_app_directory(), 'synced_analyses.json'), 'r') as f:
                self.synced_analyses = set(json.load(f))
        except FileNotFoundError:
            # we already have an empty set as the field value
            print('No saved downloaded analyses found.')

    def save_last_geosync_run(self) -> None:
        """Saves the timestamp of the last successful geosync run."""
        with open(os.path.join(get_app_directory(), 'last_geosync_run.json'), 'w') as f:
            json.dump(self.last_geosync_run.isoformat() if self.last_geosync_run else None, f)

    def load_last_geosync_run(self) -> None:
        """Loads the timestamp of the last successful geosync run."""
        try:
            with open(os.path.join(get_app_directory(), 'last_geosync_run.json'), 'r') as f:
                timestamp_str = json.load(f)
                self.last_geosync_run = datetime.fromisoformat(timestamp_str) if timestamp_str else None
        except FileNotFoundError:
            # we already have None as the field value
            print('No saved last geosync run timestamp found.')

    def record_successful_geosync_run(self, start_time: datetime) -> None:
        """Records the current time as the last successful geosync run."""
        self.last_geosync_run = start_time
        self.save_last_geosync_run()

    def record_analyses_requested(self, start_analyses_result, analysis_inputs) -> None:
        """Records the analyses that have been started, where they were started, and which layers were requested."""
        pattern = r'^startAnalysis_(?P<state>DE[1-9A-G])$'
        for alias, analysis_metadata in start_analyses_result.__dict__.items():
            match = re.match(pattern, alias)
            if not match:
                continue
            state = match.group('state')
            # record where the analysis was started
            self.analysis_states[analysis_metadata.pk] = state
            # record which layers were requested
            requested_layers = set()
            for request in analysis_inputs[state].specs.requests:
                for layer in request.layers:
                    requested_layers.add(layer.layer_name)
            self.analysis_requested_layers[analysis_metadata.pk] = requested_layers
        self.save_analysis_states()
        self.save_analysis_requested_layers()

    def clear_analysis_requested_layers(self) -> None:
        """Clears all analysis requested layers at the start of a new run."""
        if self.analysis_requested_layers:
            print(
                f"Clearing {len(self.analysis_requested_layers)} old analysis metadata entries from previous runs"
            )
            self.analysis_requested_layers.clear()
            self.save_analysis_requested_layers()

    def record_layers_unpacked(self, layers: Set[str], state: str, started_at: datetime) -> None:
        """Records the layers that have been unpacked, and when they were last updated."""
        print(f'Recording layers {layers} as unpacked for state {state}')

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

        saved_timestamp = self.layer_last_updates[layer][state]

        # Handle timezone comparison issues by making both timezone-aware
        if saved_timestamp.tzinfo is None and timestamp.tzinfo is not None:
            # Assume saved timestamp is UTC if it has no timezone info
            saved_timestamp = saved_timestamp.replace(tzinfo=timezone.utc)
        elif saved_timestamp.tzinfo is not None and timestamp.tzinfo is None:
            # Make the API timestamp timezone-aware (assume UTC)
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return saved_timestamp < timestamp

    def record_analysis_synced(self, pk: str) -> None:
        """Records that the analysis has been downloaded and unpacked."""
        self.synced_analyses.add(pk)
        self.save_synced_analyses()
        # Clean up the requested layers for this analysis to prevent unbounded growth
        if pk in self.analysis_requested_layers:
            del self.analysis_requested_layers[pk]
            self.save_analysis_requested_layers()
