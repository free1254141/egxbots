import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from api import daily_social_recovery as recovery


@pytest.fixture
def setup(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 11, 19, tzinfo=ZoneInfo('Africa/Cairo'))
    monkeypatch.setattr(recovery, 'datetime', Clock)
    steps = [{'step': 'sync_prices', 'status': 'failed', 'details': 'Synced 235/284 symbols'},
             {'step': 'calculate_indicators', 'status': 'success'}]
    job = {'id': 'job', 'status': 'completed', 'job_type': 'daily_bot',
           'started_at': '2026-10-11T14:00:00Z', 'steps': json.dumps(steps)}
    query = Mock()
    query.select.return_value = query; query.eq.return_value = query; query.limit.return_value = query
    query.execute.return_value = SimpleNamespace(data=[job])
    client = SimpleNamespace(table=lambda _: query)
    ledger = {}
    monkeypatch.setattr(recovery, 'read_checkpoint', lambda *args: ledger.get(args[1]))
    def claim(client, key, payload, expected):
        ledger[key] = {'payload': {**payload, '_version': str(payload.get('attempts'))}}
        return ledger[key]
    monkeypatch.setattr(recovery, 'replace_checkpoint', claim)
    monkeypatch.setattr(recovery, 'append_step', lambda *args: None)
    generator = Mock(return_value={'reports': {'stock': {'status': 'ready'}}})
    cache = Mock(return_value={'invalidated': ['daily-market-data']})
    monkeypatch.setattr('api.daily_social_reports.generate_daily_social_reports', generator)
    monkeypatch.setattr('api.cache_invalidation.invalidate_daily_cache', cache)
    return client, job, generator, cache


def test_continuation_only_generates_reports_once_and_refreshes_cache(setup):
    client, _, generator, cache = setup
    assert recovery.resume_daily_social_reports(client, 'job')['status'] == 'completed'
    assert recovery.resume_daily_social_reports(client, 'job')['status'] == 'already_claimed'
    generator.assert_called_once(); cache.assert_called_once()


def test_cache_failure_can_retry_once_before_any_report_starts(setup, monkeypatch):
    client, job, generator, cache = setup
    run_query = Mock()
    run_query.select.return_value = run_query; run_query.eq.return_value = run_query; run_query.limit.return_value = run_query
    run_query.execute.return_value = SimpleNamespace(data=[job])
    reports_query = Mock()
    reports_query.select.return_value = reports_query; reports_query.eq.return_value = reports_query; reports_query.limit.return_value = reports_query
    reports_query.execute.return_value = SimpleNamespace(data=[])
    client.table = lambda name: run_query if name == 'daily_job_runs' else reports_query
    key = 'daily_social_resume_job'
    ledger = {key: {'payload': {'status': 'failed', 'stage': 'cache_revalidation',
                                'attempts': 1, '_version': 'old'}}}
    monkeypatch.setattr(recovery, 'read_checkpoint', lambda *_: ledger[key])
    def claim(client, key, payload, expected):
        ledger[key] = {'payload': {**payload, '_version': str(payload.get('attempts'))}}
        return ledger[key]
    monkeypatch.setattr(recovery, 'replace_checkpoint', claim)
    cache.return_value = {'invalidated': ['daily-market-data']}
    assert recovery.resume_daily_social_reports(client, 'job')['status'] == 'completed'
    generator.assert_called_once(); cache.assert_called_once()


def test_cache_failure_is_not_retried_after_report_started(setup, monkeypatch):
    client, job, generator, cache = setup
    raw_steps = json.loads(job['steps'])
    raw_steps.append({'step': 'daily_social_reports', 'status': 'started'})
    job['steps'] = json.dumps(raw_steps)
    monkeypatch.setattr(recovery, 'read_checkpoint', lambda *_: {
        'payload': {'status': 'failed', 'stage': 'cache_revalidation', 'attempts': 1}})
    monkeypatch.setattr('api.daily_social_recovery.replace_checkpoint', lambda *args: pytest.fail('must not retry'))
    assert recovery.resume_daily_social_reports(client, 'job')['status'] == 'already_claimed'
    generator.assert_not_called(); cache.assert_not_called()


@pytest.mark.parametrize('patch', [{'status': 'running'}, {'job_type': 'daily_midday'},
    {'started_at': '2026-10-10T14:00:00Z'}])
def test_wrong_phase_unfinished_or_old_jobs_cannot_resume(setup, patch):
    client, job, generator, _ = setup
    job.update(patch)
    with pytest.raises(ValueError): recovery.resume_daily_social_reports(client, 'job')
    generator.assert_not_called()
