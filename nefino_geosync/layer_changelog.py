"""Module for querying and logging layer changelog information."""

import csv
import logging
import os
from .api_client import GeneralAvailabilityResult, layer_changelog_operation
from .config import Config
from .graphql_errors import check_errors
from .journal import Journal
from .schema import LayerChangelogEntry
from datetime import datetime, timezone
from .access_rule_filter import accessible_clusters
from sgqlc.endpoint.http import HTTPEndpoint
from typing import Any

log = logging.getLogger(__name__)

LayerChangelogResult = Any


def query_layer_changelog(client: HTTPEndpoint, timestamp_start: str = None) -> LayerChangelogResult:
    """Queries the layer changelog from the GraphQL API."""
    changelog_op = layer_changelog_operation(timestamp_start)
    changelog_data = client(changelog_op)
    check_errors(changelog_data, 'Failed to fetch layer changelog')
    return changelog_op + changelog_data


def record_layer_changes_since_last_run(
    client: HTTPEndpoint, general_availability: GeneralAvailabilityResult
) -> LayerChangelogResult:
    """Logs all layer changes since the last successful geosync run and returns the changelog data."""
    journal = Journal.singleton()

    # Get the timestamp of the last successful run
    timestamp_start = None
    if journal.last_geosync_run:
        # Format timestamp as required: 2025-09-19T10:30:20.383210+00:00
        if journal.last_geosync_run.tzinfo is None:
            # If timezone-naive, assume UTC

            aware_timestamp = journal.last_geosync_run.replace(tzinfo=timezone.utc)
        else:
            aware_timestamp = journal.last_geosync_run

        timestamp_start = aware_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
        # Ensure the timezone format includes the colon (e.g., +00:00 not +0000)
        if len(timestamp_start) >= 4 and timestamp_start[-4:].isdigit():
            timestamp_start = timestamp_start[:-2] + ':' + timestamp_start[-2:]

        log.info(f'Checking for layer changes since last geosync run: {timestamp_start}')
    else:
        log.info('No previous geosync run found, skipping changelog check')
        return None

    # Get available clusters to filter changelog results
    try:
        if general_availability is None:  # fetching it failed while resuming
            raise ValueError('the layer availability is unknown')
        # Get all places from access rules to check against
        all_places = {place for rule in general_availability.access_rules for place in rule.places}
        accessible_cluster_names = {
            cluster.name for place in all_places for cluster in accessible_clusters(general_availability, place)
        }
        log.info(f'Accessible clusters: {accessible_cluster_names}')

    except Exception as e:
        log.warning(f'Failed to determine accessible clusters, showing all changelog entries: {e}')
        accessible_cluster_names = set()  # Empty set means show all

    # Query the changelog
    try:
        changelog_result = query_layer_changelog(client, timestamp_start)
        record_relevant_changes(changelog_result)
        log_changelog_entries(changelog_result, accessible_cluster_names)
        return changelog_result
    except Exception as e:
        log.warning(f'Failed to retrieve layer changelog: {e}')
        return None


def record_relevant_changes(changelog_result: LayerChangelogResult) -> None:
    """Records the relevant changes of all entries in the journal, so that each state requests the changed layers
    until it has newer files, also when this run does not process that state."""
    journal = Journal.singleton()
    for entry in getattr(changelog_result, 'layer_changelog', None) or []:
        if _get_relevant_changes(entry) and entry.timestamp is not None:
            journal.record_layer_change(entry.layer_name, entry.timestamp)


def log_changelog_entries(changelog_result: LayerChangelogResult, accessible_clusters: set = None) -> None:
    """Logs changelog entries, focusing on relevant changes and filtering by accessible clusters."""
    if not hasattr(changelog_result, 'layer_changelog'):
        log.info('No layer changelog data received')
        return

    changelog_entries = changelog_result.layer_changelog
    if not changelog_entries:
        log.info('✅ No layer changes detected for accessible clusters since last run')
        return

    # Filter entries by accessible clusters and collect those with relevant changes
    relevant_entries = []
    for entry in changelog_entries:
        # Skip if not in accessible clusters
        cluster_name = getattr(entry, 'cluster_name', None)
        if accessible_clusters and (not cluster_name or cluster_name not in accessible_clusters):
            continue

        # Check for relevant changes
        relevant_changes = _get_relevant_changes(entry)
        if relevant_changes:
            relevant_entries.append((entry, relevant_changes))

    # If no relevant changes found, show success message
    if not relevant_entries:
        log.info('✅ No layer changes detected for accessible clusters since last run')
        return

    log.info(f'📋 Found {len(relevant_entries)} layer change(s) for accessible clusters since last run:')

    for entry, relevant_changes in relevant_entries:
        _log_entry_details(entry, relevant_changes)

    # Save to CSV (use original filtered entries for CSV)
    filtered_entries = [entry for entry, _ in relevant_entries]
    save_changelog_to_csv(filtered_entries)


def _get_relevant_changes(entry: LayerChangelogEntry) -> list:
    """Extract relevant changes from a changelog entry."""
    relevant_changes = []
    if hasattr(entry, 'changed_fields') and entry.changed_fields:
        for field in entry.changed_fields:
            if field in ['attributes', 'layer_name', 'cluster_name']:
                relevant_changes.append(field)
    return relevant_changes


def _log_entry_details(entry: LayerChangelogEntry, relevant_changes: list) -> None:
    """Log details for a single changelog entry."""
    layer_name = getattr(entry, 'layer_name', 'Unknown')
    cluster_name = getattr(entry, 'cluster_name', 'Unknown')
    action = getattr(entry, 'action', 'Unknown')
    timestamp = getattr(entry, 'timestamp', 'Unknown')

    log.info(f"  📦 Layer '{layer_name}' (cluster: {cluster_name})")
    log.info(f'      Action: {action}')
    log.info(f'      Changed fields: {", ".join(relevant_changes)}')
    log.info(f'      Timestamp: {timestamp}')

    # If attributes changed, log the attributes
    if 'attributes' in relevant_changes and hasattr(entry, 'attributes') and entry.attributes:
        log.info(f'      New attributes: {", ".join(entry.attributes)}')

    log.info('')  # Empty line for readability


def save_changelog_to_csv(filtered_entries: list) -> None:
    """Saves changelog entries to a CSV file in the output directory."""
    if not filtered_entries:
        return

    config = Config.singleton()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'layer_changelog_{timestamp}.csv'
    csv_path = os.path.join(config.output_path, csv_filename)

    # Ensure output directory exists
    os.makedirs(config.output_path, exist_ok=True)

    # Define CSV headers
    headers = ['timestamp', 'layer_name', 'cluster_name', 'action', 'changed_fields', 'attributes']

    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()

            for entry in filtered_entries:
                # Filter for relevant changes
                relevant_changes = []
                if hasattr(entry, 'changed_fields') and entry.changed_fields:
                    for field in entry.changed_fields:
                        if field in ['attributes', 'layer_name', 'cluster_name']:
                            relevant_changes.append(field)

                if not relevant_changes:
                    continue  # Skip entries without relevant changes

                # Extract entry data
                layer_name = getattr(entry, 'layer_name', 'Unknown')
                cluster_name = getattr(entry, 'cluster_name', 'Unknown')
                action = getattr(entry, 'action', 'Unknown')
                timestamp_str = getattr(entry, 'timestamp', 'Unknown')
                attributes = ''
                if hasattr(entry, 'attributes') and entry.attributes:
                    attributes = ', '.join(entry.attributes)

                writer.writerow(
                    {
                        'timestamp': timestamp_str,
                        'layer_name': layer_name,
                        'cluster_name': cluster_name,
                        'action': action,
                        'changed_fields': ', '.join(relevant_changes),
                        'attributes': attributes,
                    }
                )

        log.info(f'📊 Changelog saved to CSV: {csv_path}')
    except Exception as e:
        log.warning(f'⚠️  Failed to save changelog to CSV: {e}')


def record_successful_geosync_completion(start_time: datetime) -> None:
    """Records that a geosync run completed successfully."""
    journal = Journal.singleton()
    journal.record_successful_geosync_run(start_time)
    log.info('✅ Geosync completed successfully')

