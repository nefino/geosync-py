import pytest
from datetime import datetime, timezone
from nefino_geosync import get_downloadable_analyses as downloadable
from nefino_geosync import run, start_analyses
from nefino_geosync.config import Config
from nefino_geosync.graphql_errors import GraphQLError, check_errors
from nefino_geosync.journal import Journal
from nefino_geosync.options import SyncOptions
from nefino_geosync.parse_args import parse_args
from nefino_geosync.schema import Status
from nefino_geosync.storage import get_app_directory
from types import SimpleNamespace

STARTED = datetime(2026, 11, 1, tzinfo=timezone.utc)


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


def start_with(monkeypatch, analyses, inputs):
    """Runs start_analyses with the given existing analyses and composed requests; returns the started states."""
    started = []

    class Operation:
        def __init__(self, states):
            self.states = states

        def __add__(self, data):
            return SimpleNamespace(**{f'startAnalysis_{state}': SimpleNamespace(pk=f'new_{state}') for state in self.states})

    def start_operation(state_inputs):
        started.extend(state_inputs)
        return Operation(list(state_inputs))

    monkeypatch.setattr(start_analyses, 'fetch_analyses', lambda client: analyses)
    monkeypatch.setattr(start_analyses, 'compose_complete_requests', lambda *args: dict(inputs))
    monkeypatch.setattr(start_analyses, 'start_analyses_operation', start_operation)
    monkeypatch.setattr(start_analyses, 'download_completed_analyses', lambda client: None)
    start_analyses.start_analyses(lambda op: {}, None, None, None)
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
    journal.analysis_states.update({'old': 'DE1', 'new': 'DE2', 'downloaded': 'DE3', 'failed': 'DE4'})
    journal.synced_analyses.update({'old', 'downloaded'})
    analyses = [analysis(pk, status) for pk, status in
                [('old', 'SUCCESS'), ('new', 'RUNNING'), ('downloaded', 'SUCCESS'), ('failed', 'ERROR'), ('foreign', 'ERROR')]]
    monkeypatch.setattr(run, 'fetch_analyses', lambda client: analyses)

    result = run.summarize(None, known_analyses={'old', 'downloaded', 'failed'}, synced_analyses={'old'})

    assert [a.pk for a in result.started] == ['new']
    assert [a.pk for a in result.downloaded] == ['downloaded']
    assert [(a.pk, a.state) for a in result.pending] == [('new', 'DE2')]
    assert [(a.pk, a.state, a.started_at) for a in result.failed] == [('failed', 'DE4', STARTED)]
