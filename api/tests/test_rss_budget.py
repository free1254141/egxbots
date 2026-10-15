import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from api.rss_budget import RSSBudget, RSSUnavailable
from api import news_sentiment_engine as news
from api import corporate_actions_engine as actions


def test_outage_circuit_bounds_requests_and_preserves_old_news(monkeypatch):
    provider = Mock(side_effect=TimeoutError('offline'))
    monkeypatch.setattr('urllib.request.urlopen', provider)
    db = Mock()
    monkeypatch.setitem(sys.modules, 'api.stock_ai', SimpleNamespace(_init_supabase=lambda: None, supabase=db))
    progress = []
    ok, count = news.process_exchange_news('EGX', ['A', 'B', 'C', 'D'], name_map={}, progress_callback=progress.append)
    assert not ok and count == 0
    assert provider.call_count == 6
    db.table.assert_not_called()
    assert progress[-1]['stopped']
    assert progress[-1]['rss_succeeded'] == 0


def test_corporate_outage_is_failed_not_successful_empty(monkeypatch):
    provider = Mock(side_effect=TimeoutError('offline'))
    monkeypatch.setattr('urllib.request.urlopen', provider)
    db = Mock()
    monkeypatch.setitem(sys.modules, 'api.stock_ai', SimpleNamespace(_init_supabase=lambda: None, supabase=db))
    monkeypatch.setattr(news, 'load_company_names', lambda _: {})
    progress = []
    assert actions.process_exchange_corporate_actions('EGX', ['A','B','C','D'], progress_callback=progress.append) == (False, 0)
    assert provider.call_count == 6
    db.table.assert_not_called()
    assert progress[-1]['stopped']


def test_expired_budget_never_contacts_provider(monkeypatch):
    provider = Mock()
    monkeypatch.setattr('urllib.request.urlopen', provider)
    with pytest.raises(RSSUnavailable):
        RSSBudget(seconds=-1).fetch('request')
    provider.assert_not_called()


def test_valid_empty_feed_is_distinct_from_unavailable(monkeypatch):
    response = Mock()
    response.read.side_effect = [b'<rss><channel/></rss>', b''] * 2
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    provider = Mock(return_value=response)
    monkeypatch.setattr('urllib.request.urlopen', provider)
    budget = RSSBudget()
    assert news.fetch_google_news('COMI', rss_budget=budget) == []
    assert budget.succeeded == 2
    assert provider.call_args.kwargs['timeout'] <= 6


def test_non_feed_response_is_not_valid_empty_coverage(monkeypatch):
    response = Mock()
    response.read.side_effect = [b'<html>upstream error</html>', b''] * 2
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr('urllib.request.urlopen', Mock(return_value=response))
    with pytest.raises(RSSUnavailable):
        news.fetch_google_news('COMI')


def test_bounded_sweep_with_successes_is_not_outage():
    budget = RSSBudget(seconds=180)
    budget.succeeded = 50
    budget.attempted = 50
    budget.failures = 0
    assert not budget.is_outage
    # When deadline expires, it stops, but is still not an outage
    budget.deadline = 0
    assert budget.stopped
    assert not budget.is_outage


def test_consecutive_failures_trips_outage():
    budget = RSSBudget(seconds=180, max_failures=6)
    budget.failures = 6
    budget.attempted = 6
    assert budget.stopped
    assert budget.is_outage

