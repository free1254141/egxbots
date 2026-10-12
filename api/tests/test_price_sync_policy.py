from api.price_sync_policy import configure_tradingview_client, retryable_price_failure, sync_with_retries


def test_timeout_with_fallback_404_can_recover():
    outcomes = iter([(False, 'TradingView error: Connection timed out (Yahoo fallback: 404 Not Found)'),
                     (True, 'saved dated candles')])
    calls, sleeps = [], []
    def fetch(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return next(outcomes)
    assert sync_with_retries(fetch, 'APPC.EGX', max_retries=2, retry_delay=1,
                            sleep=sleeps.append, refresh_latest=True) == (True, 'saved dated candles')
    assert len(calls) == 2 and calls[0][1]['refresh_latest'] is True
    assert sleeps == [1]


def test_empty_response_is_bounded_and_no_final_sleep():
    calls, sleeps = [], []
    def fetch(*args, **kwargs):
        calls.append(1)
        return False, 'No data found for APPC'
    ok, reason = sync_with_retries(fetch, 'APPC', max_retries=999, retry_delay=999, sleep=sleeps.append)
    assert not ok and '2 attempts' in reason
    assert len(calls) == 2 and sleeps == [30]


def test_terminal_failure_does_not_retry():
    calls = []
    def fetch(*args, **kwargs):
        calls.append(1)
        return False, 'Symbol not found on EGX'
    assert not sync_with_retries(fetch, 'INVALID', max_retries=3, retry_delay=1,
                                sleep=lambda _: (_ for _ in ()).throw(AssertionError('must not sleep')))[0]
    assert len(calls) == 1


def test_socket_timeout_is_clamped(monkeypatch):
    class Client:
        _TvDatafeed__ws_timeout = 5
    monkeypatch.setenv('TRADINGVIEW_SOCKET_TIMEOUT', '999')
    assert configure_tradingview_client(Client())._TvDatafeed__ws_timeout == 30
    monkeypatch.setenv('TRADINGVIEW_SOCKET_TIMEOUT', 'invalid')
    assert configure_tradingview_client(Client())._TvDatafeed__ws_timeout == 15


def test_primary_error_controls_retry():
    assert retryable_price_failure('Connection timed out (Yahoo fallback: symbol not found)')
    assert not retryable_price_failure('Invalid exchange: INVALID')
