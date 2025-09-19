"""Module for querying and logging layer changelog information."""

from .api_client import general_availability_operation, layer_changelog_operation
from .graphql_errors import check_errors
from .journal import Journal
from datetime import timezone
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

        # Extract accessible cluster names
        accessible_clusters = set()
        if hasattr(general_availability, 'clusters') and general_availability.clusters:
            for cluster in general_availability.clusters:
                if hasattr(cluster, 'has_access') and cluster.has_access:
                    if hasattr(cluster, 'name'):
                        accessible_clusters.add(cluster.name)

        print(f'Found {len(accessible_clusters)} accessible clusters for changelog filtering')

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

        if len(filtered_entries) != len(changelog_entries):
            print(f'Filtered {len(changelog_entries)} entries to {len(filtered_entries)} based on accessible clusters')
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


def record_successful_geosync_completion() -> None:
    """Records that a geosync run completed successfully."""
    journal = Journal.singleton()
    journal.record_successful_geosync_run()
    print('✅ Geosync completed successfully')
