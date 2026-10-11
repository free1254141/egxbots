"""Bounded recovery for provider failures; never invent missing market bars."""
import os


def configure_tradingview_client(client):
    # tvdatafeed's five-second default is too short for intermittent EGX feeds.
    # Clamp overrides so a misconfigured environment cannot hang the daily job.
    try:
        timeout = float(os.getenv('TRADINGVIEW_SOCKET_TIMEOUT', '15'))
    except (TypeError, ValueError):
        timeout = 15.0
    timeout = min(30.0, max(5.0, timeout))
    if hasattr(client, '_TvDatafeed__ws_timeout'):
        client._TvDatafeed__ws_timeout = timeout
    return client


def retryable_price_failure(message):
    # A Yahoo 404 must not turn a TradingView timeout into a terminal symbol error.
    primary = str(message).lower().split('(yahoo fallback:', 1)[0]
    if any(term in primary for term in ('404', 'symbol not found', 'invalid exchange', 'delisted',
                                        'library not installed')):
        return False
    return any(term in primary for term in ('timeout', 'timed out', 'connection', 'rate limit',
                                           '429', 'error', 'no data found'))


def sync_with_retries(fetch, symbol, *, max_retries, retry_delay, sleep, **kwargs):
    last_error = ''
    # Even an accidental configuration override cannot trigger unbounded retries.
    retries = min(3, max(0, int(max_retries)))
    delay = min(30, max(0, float(retry_delay)))
    for attempt in range(retries + 1):
        try:
            success, message = fetch(symbol, **kwargs)
            if success:
                return True, message
            last_error = str(message)
        except Exception as error:
            last_error = f'{type(error).__name__}: {error}'
        if not retryable_price_failure(last_error):
            return False, last_error
        if attempt < retries:
            sleep(delay)
    return False, f'Failed after {retries + 1} attempts. Last error: {last_error}'


def price_sync_usable(step, min_coverage=None):
    """True when prices are complete, or a provider gap leaves enough symbols.

    A handful of EGX symbols (illiquid/suspended) routinely get no bar from the
    provider. Dependent stages work on the symbols that do have fresh prices,
    so a small gap must not be treated as a failed day. Never invents prices.
    """
    import re
    step = step or {}
    if step.get('status') == 'success':
        return True
    if step.get('status') not in {'failed', 'partial'}:
        return False
    if min_coverage is None:
        try:
            min_coverage = float(os.getenv('PRICE_SYNC_MIN_COVERAGE', '0.8'))
        except (TypeError, ValueError):
            min_coverage = 0.8
    match = re.search(r'Synced\s+(\d+)\s*/\s*(\d+)', str(step.get('details') or ''))
    if not match:
        return False
    done, total = int(match.group(1)), int(match.group(2))
    return 0 < min_coverage <= 1 and total > 0 and 0 <= done <= total and done / total >= min_coverage
