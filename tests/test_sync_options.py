import logging
import os
import pickle
import pytest
import sys
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
from nefino_geosync import compose_requests, layer_changelog, run, start_analyses
from nefino_geosync import get_downloadable_analyses as downloadable
from nefino_geosync.config import Config
from nefino_geosync.graphql_errors import GraphQLError, check_errors
from nefino_geosync.journal import Journal
from nefino_geosync.options import SyncOptions
from nefino_geosync.run import sync
from nefino_geosync.parse_args import parse_args
from nefino_geosync.schema import Status
from nefino_geosync.storage import get_app_directory
from types import SimpleNamespace

STARTED = datetime(2026, 11, 1, tzinfo=timezone.utc)
CHANGE = datetime(2026, 11, 10, tzinfo=timezone.utc)
DAY = timedelta(days=1)

# the module, not the function of the same name that the package's modules import
dca = sys.modules['nefino_geosync.download_completed_analyses']


def analysis(pk, status):
    return SimpleNamespace(pk=pk, status=Status(status), url=f'https://example.com/{pk}.zip', started_at=STARTED)


def analysis_input(*layers):
    return SimpleNamespace(specs=SimpleNamespace(requests=[SimpleNamespace(layers=[SimpleNamespace(layer_name=layer) for layer in layers])]))


def test_command_line_defaults_match_the_default_options():
    assert parse_args([]) == SyncOptions()


def test_command_line_flags_set_the_new_options():
    options = parse_args(['--no-wait', '--non-interactive', '--federal-states', 'DE1', 'DE2', '--app-dir', '/data'])

    assert options == SyncOptions(wait=False, interactive=False, federal_states=['DE1', 'DE2'], app_dir='/data')


def test_app_dir_option_is_used_for_config_and_journal(app, tmp_path):
    app.args(app_dir=str(tmp_path / 'custom'))

    assert get_app_directory() == str(tmp_path / 'custom')


def test_non_interactive_run_without_config_raises_instead_of_prompting(app, tmp_path):
    app.args(app_dir=str(tmp_path / 'empty'), interactive=False)
    Config._instance = None

    with pytest.raises(FileNotFoundError):
        Config.singleton()


def test_non_interactive_graphql_error_raises_instead_of_exiting(app):
    app.args(interactive=False)

    with pytest.raises(GraphQLError, match='Failed to fetch'):
        check_errors({'errors': [{'message': 'boom'}]}, 'Failed to fetch')


def test_polling_ignores_analyses_of_other_clients(app, monkeypatch):
    Journal.singleton().analysis_states.update({'own': 'DE1'})
    monkeypatch.setattr(downloadable, 'fetch_analyses', lambda client: [analysis('own', 'SUCCESS'), analysis('foreign', 'RUNNING')])
    monkeypatch.setattr(downloadable, 'sleep', lambda seconds: pytest.fail('must not wait for another client'))

    assert [a.pk for a in downloadable.get_downloadable_analyses(None)] == ['own']


def test_polling_without_waiting_checks_only_once(app, monkeypatch):
    app.args(wait=False)
    Journal.singleton().analysis_states.update({'done': 'DE1', 'running': 'DE2'})
    monkeypatch.setattr(downloadable, 'fetch_analyses', lambda client: [analysis('done', 'SUCCESS'), analysis('running', 'RUNNING')])
    monkeypatch.setattr(downloadable, 'sleep', lambda seconds: pytest.fail('must not wait'))

    assert [a.pk for a in downloadable.get_downloadable_analyses(None)] == ['done']


def start_with(monkeypatch, analyses, inputs, download=lambda: None, events=None):
    """Runs download_unfinished_analyses and start_analyses, as a run does, with the given existing analyses and
    composed requests; returns the started states. download is called for each download_completed_analyses call,
    events records the downloads and starts."""
    started = []
    events = events if events is not None else []

    def download_completed(client):
        events.append('download')
        download()

    class Operation:
        def __init__(self, states):
            self.states = states

        def __add__(self, data):
            return SimpleNamespace(**{f'startAnalysis_{state}': SimpleNamespace(pk=f'new_{state}') for state in self.states})

    def start_operation(state_inputs):
        started.extend(state_inputs)
        events.extend(state_inputs)
        return Operation(list(state_inputs))

    monkeypatch.setattr(start_analyses, 'fetch_analyses', lambda client: analyses)
    monkeypatch.setattr(start_analyses, 'compose_complete_requests', lambda *args: dict(inputs))
    monkeypatch.setattr(start_analyses, 'start_analyses_operation', start_operation)
    monkeypatch.setattr(start_analyses, 'download_completed_analyses', download_completed)
    start_analyses.download_unfinished_analyses(None)
    start_analyses.start_analyses(lambda op: {}, None, None)
    return started


def test_without_waiting_no_second_analysis_is_started_for_a_state_with_an_unfinished_one(app, monkeypatch):
    app.args(wait=False)
    journal = Journal.singleton()
    journal.analysis_states.update({'running': 'DE1', 'finished': 'DE2', 'failed': 'DE3'})
    journal.analysis_requested_layers.update({'running': {'a'}, 'finished': {'b'}, 'failed': {'c'}})
    analyses = [analysis('running', 'RUNNING'), analysis('finished', 'SUCCESS'), analysis('failed', 'ERROR')]
    inputs = {state: analysis_input('layer') for state in ['DE1', 'DE2', 'DE3', 'DE4']}

    started = start_with(monkeypatch, analyses, inputs)

    assert started == ['DE3', 'DE4']
    # the analyses that are still to be downloaded keep their requested layers
    assert set(journal.analysis_requested_layers) == {'running', 'finished', 'new_DE3', 'new_DE4'}


def test_by_default_analyses_are_started_for_all_states(app, monkeypatch):
    journal = Journal.singleton()
    journal.analysis_states.update({'old': 'DE1'})
    journal.analysis_requested_layers.update({'old': {'a'}})
    journal.synced_analyses.add('old')

    started = start_with(monkeypatch, [analysis('old', 'SUCCESS')], {'DE1': analysis_input('layer')})

    assert started == ['DE1']
    assert set(journal.analysis_requested_layers) == {'new_DE1'}


def test_result_summarizes_the_journals_analyses(app, monkeypatch):
    journal = Journal.singleton()
    journal.analysis_states.update({'old': 'DE1', 'new': 'DE2', 'downloaded': 'DE3', 'failed': 'DE4', 'both': 'DE5'})
    # 'both' was started and downloaded in this run, which removed its requested layers
    journal.synced_analyses.update({'old', 'downloaded', 'both'})
    analyses = [analysis(pk, status) for pk, status in
                [('old', 'SUCCESS'), ('new', 'RUNNING'), ('downloaded', 'SUCCESS'), ('failed', 'ERROR'),
                 ('foreign', 'ERROR'), ('both', 'SUCCESS')]]
    monkeypatch.setattr(run, 'fetch_analyses', lambda client: analyses)

    result = run.summarize(
        None, known_analyses={'old', 'downloaded', 'failed'}, synced_analyses={'old'}, tracked={'downloaded', 'failed'}
    )

    assert [a.pk for a in result.started] == ['new', 'both']
    assert [a.pk for a in result.downloaded] == ['downloaded', 'both']
    assert [(a.pk, a.state) for a in result.pending] == [('new', 'DE2')]
    assert [(a.pk, a.state, a.started_at) for a in result.failed] == [('failed', 'DE4', STARTED)]


def test_result_does_not_list_failed_analyses_of_earlier_cycles(app, monkeypatch):
    Journal.singleton().analysis_states.update({'old_failed': 'DE1'})
    monkeypatch.setattr(run, 'fetch_analyses', lambda client: [analysis('old_failed', 'ERROR')])

    result = run.summarize(None, known_analyses={'old_failed'}, synced_analyses=set(), tracked=set())

    assert result.failed == []


# A successful command line run must not fail afterwards


def test_command_line_run_sends_no_summary_request(app, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['nefino-geosync'])
    monkeypatch.setattr(run.atexit, 'register', lambda function: None)
    monkeypatch.setattr(run, '_run', lambda options: (None, set(), set(), set()))
    monkeypatch.setattr(run, 'summarize', lambda *args: pytest.fail('the command line must not send a summary request'))
    package_logger = logging.getLogger('nefino_geosync')
    handlers, level = list(package_logger.handlers), package_logger.level
    try:
        run.main()
    finally:
        package_logger.handlers = handlers
        package_logger.setLevel(level)
        run.stop_session_logging()


# Errors when running non-interactively


def test_non_interactive_http_error_raises_graphql_error(app):
    app.args(interactive=False)
    errors = [{'message': 'HTTP Error 502', 'exception': urllib.error.HTTPError('https://api', 502, 'Bad Gateway', {}, None), 'status': 502}]

    with pytest.raises(GraphQLError, match='502') as error:
        check_errors({'errors': errors}, 'Failed to fetch')

    assert error.value.errors is errors


def test_graphql_error_can_be_passed_between_processes():
    # the errors of an HTTP error hold the open response, which cannot be pickled
    error = pickle.loads(pickle.dumps(GraphQLError('Failed to fetch: 502', [{'exception': threading.Lock()}])))

    assert isinstance(error, GraphQLError)
    assert str(error) == 'Failed to fetch: 502'
    assert error.errors is None


def test_library_sync_without_config_raises_instead_of_prompting(app, tmp_path, monkeypatch):
    monkeypatch.setattr('questionary.text', lambda *args, **kwargs: pytest.fail('must not prompt'))
    monkeypatch.setattr('questionary.select', lambda *args, **kwargs: pytest.fail('must not prompt'))

    with pytest.raises(FileNotFoundError):
        sync(SyncOptions(app_dir=str(tmp_path / 'empty')))


def test_app_dir_is_expanded_and_absolute(app, tmp_path, monkeypatch):
    app.args(app_dir='~/custom')
    assert get_app_directory() == str(tmp_path / 'home' / 'custom')

    monkeypatch.chdir(tmp_path)
    app.args(app_dir='relative')
    assert get_app_directory() == str(tmp_path / 'relative')


# Failed downloads


def fake_downloads(monkeypatch, analyses, failing):
    """Lets download_completed_analyses see the given analyses; downloading the failing pks raises. Returns the
    downloaded pks."""
    downloaded = []

    def download(analysis):
        if analysis.pk in failing:
            raise urllib.error.HTTPError(analysis.url, 404, 'Not Found', {}, None)
        downloaded.append(analysis.pk)
        # not record_analysis_synced: it would also save the requested layers dropped by the failure
        journal = Journal.singleton()
        journal.synced_analyses.add(analysis.pk)
        journal.save_synced_analyses()

    monkeypatch.setattr(dca, 'get_downloadable_analyses', lambda client: analyses)
    monkeypatch.setattr(dca, 'download_analysis', download)
    return downloaded


def journal_with_finished_analyses():
    journal = Journal.singleton()
    journal.analysis_states.update({'broken': 'DE1', 'ok': 'DE2'})
    journal.analysis_requested_layers.update({'broken': {'a'}, 'ok': {'b'}})
    journal.save_analysis_states()
    journal.save_analysis_requested_layers()
    return [analysis('broken', 'SUCCESS'), analysis('ok', 'SUCCESS')]


def test_failed_download_is_dropped_and_the_other_analyses_are_still_downloaded(app, monkeypatch):
    analyses = journal_with_finished_analyses()
    downloaded = fake_downloads(monkeypatch, analyses, failing={'broken'})

    with pytest.raises(urllib.error.HTTPError, match='404'):
        dca.download_completed_analyses(None)

    assert downloaded == ['ok']
    assert 'broken' not in Journal.singleton().analysis_requested_layers
    Journal._instance = None
    assert 'broken' not in Journal.singleton().analysis_requested_layers


def test_run_after_a_failed_download_does_not_try_that_analysis_again(app, monkeypatch):
    analyses = journal_with_finished_analyses()
    fake_downloads(monkeypatch, analyses, failing={'broken'})
    with pytest.raises(urllib.error.HTTPError):
        dca.download_completed_analyses(None)

    Journal._instance = None
    downloaded = fake_downloads(monkeypatch, analyses, failing={'broken'})
    dca.download_completed_analyses(None)

    assert downloaded == []
    assert Journal.singleton().get_unfinished_analyses(analyses) == {}


# Earlier analyses are downloaded before new ones are started


def test_unfinished_analyses_are_downloaded_before_new_ones_are_started(app, monkeypatch):
    app.args(wait=False)
    journal = Journal.singleton()
    journal.analysis_states.update({'finished': 'DE1'})
    journal.analysis_requested_layers.update({'finished': {'a'}})
    events = []

    started = start_with(monkeypatch, [analysis('finished', 'SUCCESS')], {'DE1': analysis_input('layer')},
                         download=lambda: journal.record_analysis_synced('finished'), events=events)

    assert events == ['download', 'DE1']
    assert started == ['DE1']


def test_default_run_starts_no_second_analysis_for_a_state_with_a_running_one(app, monkeypatch):
    journal = Journal.singleton()
    journal.analysis_states.update({'running': 'DE1'})
    journal.analysis_requested_layers.update({'running': {'a'}})
    events = []

    # waiting for the running analysis downloads it
    started = start_with(monkeypatch, [analysis('running', 'RUNNING')], {'DE1': analysis_input('layer')},
                         download=lambda: journal.record_analysis_synced('running'), events=events)

    assert events[0] == 'download'
    assert 'running' in journal.synced_analyses
    assert started == ['DE1']


def test_nothing_is_downloaded_before_starting_without_unfinished_analyses(app, monkeypatch):
    journal = Journal.singleton()
    journal.analysis_states.update({'old': 'DE1', 'failed': 'DE2'})
    journal.analysis_requested_layers.update({'failed': {'a'}})
    journal.synced_analyses.add('old')
    events = []

    start_with(monkeypatch, [analysis('old', 'SUCCESS'), analysis('failed', 'ERROR')], {'DE1': analysis_input('layer')},
               events=events)

    # only the download after the start in wait mode
    assert events == ['DE1', 'download']


def test_run_downloads_unfinished_analyses_before_checking_the_local_files(app, monkeypatch):
    events = []
    monkeypatch.setattr(run, 'get_client', lambda api_host: None)
    monkeypatch.setattr(run, 'fetch_general_availability', lambda client: None)
    monkeypatch.setattr(run, 'fetch_local_availability', lambda client, general: None)
    monkeypatch.setattr(run, 'accessible_layers', lambda general, local: {})
    monkeypatch.setattr(run, 'record_layer_changes_since_last_run', lambda client, general: None)
    monkeypatch.setattr(run, 'download_unfinished_analyses', lambda client: events.append('download'))
    monkeypatch.setattr(run, 'mark_outdated_local_files', lambda accessible: events.append('file check'))
    monkeypatch.setattr(run, 'start_analyses', lambda *args: events.append('start'))
    monkeypatch.setattr(run, 'record_successful_geosync_completion', lambda start_time: None)

    run._run(SyncOptions())

    # a downloaded analysis may bring back files that the file check must mark as outdated
    assert events == ['download', 'file check', 'start']


def test_skipping_all_states_is_not_reported_as_up_to_date(app, monkeypatch, caplog):
    app.args(wait=False)
    journal = Journal.singleton()
    journal.analysis_states.update({'running': 'DE1'})
    journal.analysis_requested_layers.update({'running': {'a'}})

    with caplog.at_level(logging.INFO, logger='nefino_geosync'):
        started = start_with(monkeypatch, [analysis('running', 'RUNNING')], {'DE1': analysis_input('layer')})

    assert started == []
    assert 'No analyses started: earlier analyses are not downloaded yet.' in caplog.text
    assert 'No layers to update' not in caplog.text


# Changelog changes are kept per layer and compared per state


def test_changelog_change_reaches_a_state_that_this_run_did_not_process(app):
    journal = Journal.singleton()
    journal.record_layer_change('L', CHANGE)
    journal.record_layers_unpacked({'L'}, 'DE1', CHANGE + DAY)
    journal.record_layers_unpacked({'L'}, 'DE2', CHANGE - DAY)

    assert journal.has_unsynced_change('L', 'DE2')
    assert not journal.has_unsynced_change('L', 'DE1')


def test_changelog_change_seen_in_a_resume_run_is_requested_by_the_next_run(app, monkeypatch):
    journal = Journal.singleton()
    journal.record_successful_geosync_run(CHANGE - DAY)
    entries = [
        SimpleNamespace(layer_name='L', cluster_name='C', action='UPDATE', changed_fields=['attributes'], attributes=['x'], timestamp=CHANGE),
        SimpleNamespace(layer_name='M', cluster_name='C', action='UPDATE', changed_fields=['last_update'], attributes=[], timestamp=CHANGE),
    ]
    monkeypatch.setattr(layer_changelog, 'query_layer_changelog', lambda client, start: SimpleNamespace(layer_changelog=entries))
    monkeypatch.setattr(run, 'get_client', lambda api_host: None)
    monkeypatch.setattr(run, 'fetch_general_availability', lambda client: None)
    monkeypatch.setattr(run, 'fetch_local_availability', lambda client, general: None)
    monkeypatch.setattr(run, 'accessible_layers', lambda general, local: {})
    monkeypatch.setattr(run, 'download_completed_analyses', lambda client: None)

    run._run(SyncOptions(resume=True))

    Journal._instance = None
    journal = Journal.singleton()
    assert journal.layer_changes == {'L': CHANGE}
    assert journal.has_unsynced_change('L', 'DE1')


def test_layer_with_a_changelog_change_is_requested_only_in_states_with_older_files(app):
    journal = Journal.singleton()
    journal.record_layer_change('L', CHANGE)
    journal.record_layers_unpacked({'L'}, 'DE1', CHANGE + DAY)
    journal.record_layers_unpacked({'L'}, 'DE2', CHANGE - DAY)
    # the layer's data is older than both saved times, so only the changelog change can request it
    layer = SimpleNamespace(name='L', last_update=CHANGE - 2 * DAY, is_regional=False, pre_buffer=0)

    assert [i.layer_name for i in compose_requests.compose_layer_inputs([layer], set(), 'DE2', 'C')] == ['L']
    assert compose_requests.compose_layer_inputs([layer], set(), 'DE1', 'C') == []


def test_changelog_change_is_not_requested_again_after_a_newer_analysis_was_downloaded(app):
    journal = Journal.singleton()
    journal.record_layer_change('L', CHANGE)
    journal.record_layers_unpacked({'L'}, 'DE1', CHANGE + DAY)

    assert not journal.has_unsynced_change('L', 'DE1')


def test_analysis_started_before_the_change_does_not_hide_the_change(app):
    journal = Journal.singleton()
    journal.record_layer_change('L', CHANGE)
    journal.record_layers_unpacked({'L'}, 'DE1', CHANGE - DAY)

    assert journal.has_unsynced_change('L', 'DE1')


def test_older_changelog_entry_does_not_replace_a_newer_one(app):
    journal = Journal.singleton()
    journal.record_layer_change('L', CHANGE)
    journal.record_layer_change('L', (CHANGE - DAY).replace(tzinfo=None))

    assert journal.layer_changes == {'L': CHANGE}


# Federal states


def availability(*states):
    return SimpleNamespace(allowed_analysis_areas=SimpleNamespace(
        all_areas_enabled=False, enabled_states=[SimpleNamespace(place_id=state) for state in states]))


def compose(app, monkeypatch, federal_states):
    app.args(federal_states=federal_states)
    monkeypatch.setattr(compose_requests, 'compose_single_request', lambda state, *args: f'request {state}')
    return compose_requests.compose_complete_requests(availability('DE1', 'DE2'), None)


def test_unknown_federal_state_raises(app, monkeypatch):
    with pytest.raises(ValueError, match='XX9.*Available: DE1, DE2'):
        compose(app, monkeypatch, ['DE1', 'XX9'])


def test_federal_states_are_not_case_sensitive(app, monkeypatch):
    assert compose(app, monkeypatch, ['de1']) == {'DE1': 'request DE1'}


def test_empty_federal_states_selects_no_state(app, monkeypatch):
    assert compose(app, monkeypatch, []) == {}
