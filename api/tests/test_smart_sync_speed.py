import threading
import time
from api.smart_sync import SmartSync


def test_parallel_sync_accounts_for_failures_and_progress(monkeypatch):
    monkeypatch.delenv('SMART_SYNC_MAX_WORKERS', raising=False)
    syncer = SmartSync(throttle_delay=0)
    barrier = threading.Barrier(4, timeout=2)
    calls = []
    progress = []

    def fetch(symbol, **kwargs):
        calls.append((symbol, kwargs))
        barrier.wait()
        if symbol == 'BROKEN.EGX':
            raise ValueError('DB write failed')
        return True, 'saved dated prices'

    monkeypatch.setattr(syncer, 'sync_symbol_prices', fetch)
    result = syncer.sync_exchange_prices('EGX', ['A.EGX', 'B.EGX', 'C.EGX', 'BROKEN.EGX', 'A.EGX'],
                                         refresh_latest=True, on_progress=progress.append)
    assert result['total'] == 4 and result['success'] == 3
    assert len(result['results']) == 4 and not result['results']['BROKEN.EGX']['success']
    assert len(calls) == 4 and all(kwargs['refresh_latest'] for _, kwargs in calls)
    assert progress[0]['processed'] == 0 and progress[-1]['processed'] == 4
    assert progress[-1]['success'] == 3


def test_progress_callback_failure_cannot_drop_prices(monkeypatch):
    syncer = SmartSync(throttle_delay=0)
    monkeypatch.setattr(syncer, 'sync_symbol_prices', lambda *args, **kwargs: (True, 'saved'))
    def broken(_):
        raise ConnectionError('ledger unavailable')
    result = syncer.sync_exchange_prices('EGX', ['A.EGX'], on_progress=broken)
    assert result['success'] == 1


def test_daily_defaults_allow_one_retry_and_four_workers(monkeypatch):
    monkeypatch.delenv('SMART_SYNC_MAX_WORKERS', raising=False)
    syncer = SmartSync()
    assert syncer.max_retries == 1 and syncer.max_workers == 4
    assert syncer.retry_delay == 2


def test_offline_benchmark_preserves_coverage(monkeypatch):
    monkeypatch.delenv('SMART_SYNC_MAX_WORKERS', raising=False)
    timings = []
    for workers in (2, 4):
        syncer = SmartSync(max_workers=workers, throttle_delay=0)
        def fetch(symbol, **kwargs):
            time.sleep(0.02)  # Same simulated provider latency in both configurations.
            return True, 'saved dated prices'
        monkeypatch.setattr(syncer, 'sync_symbol_prices', fetch)
        start = time.monotonic()
        result = syncer.sync_exchange_prices('EGX', [f'S{i}.EGX' for i in range(40)])
        timings.append(time.monotonic() - start)
        assert result['success'] == 40 and result['total'] == 40
    print(f'OFFLINE provider simulation: 2 workers={timings[0]:.3f}s, 4 workers={timings[1]:.3f}s')
    # No timing gate: correctness is independent of CI machine load.
