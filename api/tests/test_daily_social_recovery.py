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
        ledger[key] = {'payload': payload}
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


@pytest.mark.parametrize('patch', [{'status': 'running'}, {'job_type': 'daily_midday'},
    {'started_at': '2026-10-10T14:00:00Z'}])
def test_wrong_phase_unfinished_or_old_jobs_cannot_resume(setup, patch):
    client, job, generator, _ = setup
    job.update(patch)
    with pytest.raises(ValueError): recovery.resume_daily_social_reports(client, 'job')
    generator.assert_not_called()
