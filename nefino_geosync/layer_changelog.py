"""Module for querying and logging layer changelog information."""

import csv
import os
from .api_client import general_availability_operation, layer_changelog_operation
from .config import Config
from .graphql_errors import check_errors
from .journal import Journal
from datetime import datetime, timezone
from nefino_geosync.access_rule_filter import AccessRuleFilter
from sgqlc.endpoint.http import HTTPEndpoint
from typing import Any

LayerChangelogResult = Any


def query_layer_changelog(client: HTTPEndpoint, timestamp_start: str = None) -> LayerChangelogResult:
    """Queries the layer changelog from the GraphQL API."""
    changelog_op = layer_changelog_operation(timestamp_start)
    changelog_data = client(changelog_op)
    check_errors(changelog_data, 'Failed to fetch layer changelog')
    return changelog_op + changelog_data


def log_layer_changes_since_last_run(client: HTTPEndpoint) -> None:
    """Logs all layer changes since the last successful geosync run."""
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

        print(f'Checking for layer changes since last geosync run: {timestamp_start}')
    else:
        print('No previous geosync run found, skipping changelog check')
        return

    # Get available clusters to filter changelog results
    try:
        # First get general availability to determine accessible clusters
        general_op = general_availability_operation()
        general_data = client(general_op)
        check_errors(general_data, 'Failed to fetch general availability for changelog filtering')
        general_availability = general_op + general_data

        # Use AccessRuleFilter to determine accessible clusters
        rules = AccessRuleFilter(general_availability.access_rules)

        # Get all places from access rules to check against
        all_places = set()
        for rule in general_availability.access_rules:
            all_places.update(rule.places)

        accessible_clusters = {
            cluster.name
            for cluster in general_availability.clusters
            if cluster.has_access and any(rules.check(place, cluster.name) for place in all_places)
        }
        print(f'Accessible clusters: {accessible_clusters}')

    except Exception as e:
        print(f'Failed to fetch accessible clusters, showing all changelog entries: {e}')
        accessible_clusters = set()  # Empty set means show all

    # Query the changelog
    try:
        changelog_result = query_layer_changelog(client, timestamp_start)
        log_changelog_entries(changelog_result, accessible_clusters)
    except Exception as e:
        print(f'Failed to retrieve layer changelog: {e}')


def log_changelog_entries(changelog_result: LayerChangelogResult, accessible_clusters: set = None) -> None:
    """Logs changelog entries, focusing on relevant changes and filtering by accessible clusters."""
    if not hasattr(changelog_result, 'layer_changelog'):
        print('No layer changelog data received')
        return

    changelog_entries = changelog_result.layer_changelog
    if not changelog_entries:
        print('✅ No layer changes detected since last run')
        return

    # Filter entries by accessible clusters if provided
    filtered_entries = []
    if accessible_clusters:
        for entry in changelog_entries:
            cluster_name = getattr(entry, 'cluster_name', None)
            if cluster_name and cluster_name in accessible_clusters:
                filtered_entries.append(entry)

    else:
        filtered_entries = changelog_entries

    if not filtered_entries:
        print('✅ No layer changes detected for accessible clusters since last run')
        return

    print(f'📋 Found {len(filtered_entries)} layer change(s) for accessible clusters since last run:')

    for entry in filtered_entries:
        # Filter for relevant changes (attributes, layer_name, cluster_name changes)
        relevant_changes = []
        if hasattr(entry, 'changed_fields') and entry.changed_fields:
            for field in entry.changed_fields:
                if field in ['attributes', 'layer_name', 'cluster_name']:
                    relevant_changes.append(field)

        if not relevant_changes:
            continue  # Skip entries without relevant changes

        # Log the change
        layer_name = getattr(entry, 'layer_name', 'Unknown')
        cluster_name = getattr(entry, 'cluster_name', 'Unknown')
        action = getattr(entry, 'action', 'Unknown')
        timestamp = getattr(entry, 'timestamp', 'Unknown')

        print(f"  📦 Layer '{layer_name}' (cluster: {cluster_name})")
        print(f'      Action: {action}')
        print(f'      Changed fields: {", ".join(relevant_changes)}')
        print(f'      Timestamp: {timestamp}')

        # If attributes changed, log the attributes
        if 'attributes' in relevant_changes and hasattr(entry, 'attributes') and entry.attributes:
            print(f'      New attributes: {", ".join(entry.attributes)}')

        print('')  # Empty line for readability

    # Save to CSV
    save_changelog_to_csv(filtered_entries)


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

        print(f'📊 Changelog saved to CSV: {csv_path}')
    except Exception as e:
        print(f'⚠️  Failed to save changelog to CSV: {e}')


def record_successful_geosync_completion() -> None:
    """Records that a geosync run completed successfully."""
    journal = Journal.singleton()
    journal.record_successful_geosync_run()
    print('✅ Geosync completed successfully')
