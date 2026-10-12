from datetime import datetime
from io import BytesIO
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from api import daily_social_reports as reports


def test_recovered_input_reaches_web_and_records_safe_http_rejection(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 12, 20, tzinfo=ZoneInfo('Africa/Cairo'))
    monkeypatch.setattr(reports, 'datetime', Clock)
    monkeypatch.setenv('REVALIDATE_SECRET', 'private-secret')
    calls = []
    def opener(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 409, 'Rejected', {}, BytesIO(b'{"error":"Daily data job is not ready"}'))
    result = reports.generate_daily_social_reports('job', [
        {'step':'sync_prices','status':'failed','details':'Recovered 236/284 prices'},
        {'step':'calculate_indicators','status':'success'},
        {'step':'accumulation_scan','status':'success'},
        {'step':'refresh_market_status','status':'success'},
    ], opener=opener)
    assert len(calls) == 4
    assert all(r['error'] == 'HTTP 409: Daily data job is not ready' for r in result['reports'].values())
    assert 'private-secret' not in str(result)
