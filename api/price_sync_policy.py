"""Bounded recovery for provider failures; never invent missing market bars."""
import os
import time


def bounded_setting(name, default, minimum, maximum):
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = float(default)
    if not minimum <= value <= maximum:
        value = min(maximum, max(minimum, value)) if value == value else float(default)
    return value


class _DeadlineSocket:
    """Bound the whole response, including an endless stream of heartbeats."""
    def __init__(self, socket, deadline, clock, socket_timeout):
        self.socket = socket
        self.deadline = deadline
        self.clock = clock
        self.socket_timeout = socket_timeout
        self.expired = False

    def _remaining(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            self.expired = True
            raise TimeoutError('TradingView total request deadline exceeded')
        self.socket.settimeout(min(self.socket_timeout, remaining))

    def recv(self, *args, **kwargs):
        self._remaining()
        result = self.socket.recv(*args, **kwargs)
        # tvDatafeed catches receive errors and may parse partial bars. Mark a
        # deadline reached inside recv too, so those bars cannot be published.
        if self.clock() >= self.deadline:
            self.expired = True
            raise TimeoutError('TradingView total request deadline exceeded')
        return result

    def send(self, *args, **kwargs):
        self._remaining()
        return self.socket.send(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.socket, name)


def fetch_tradingview_history(client, *, clock=time.monotonic, **kwargs):
    """Per-client deadline; no global monkeypatches or abandoned worker threads."""
    budget = bounded_setting('TRADINGVIEW_REQUEST_BUDGET', 20, 5, 45)
    deadline = clock() + budget
    original_connect = client._TvDatafeed__create_connection
    original_timeout = client._TvDatafeed__ws_timeout
    guarded = None

    def connect():
        nonlocal guarded
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError('TradingView total request deadline exceeded')
        client._TvDatafeed__ws_timeout = min(original_timeout, remaining)
        original_connect()
        # Also bound low-level frame reads: fragmented frames must not reset
        # the overall budget inside websocket-client's recv loop.
        if getattr(client.ws, 'sock', None) is not None:
            client.ws.sock = _DeadlineSocket(client.ws.sock, deadline, clock, original_timeout)
        guarded = _DeadlineSocket(client.ws, deadline, clock, original_timeout)
        client.ws = guarded

    client._TvDatafeed__create_connection = connect
    try:
        result = client.get_hist(**kwargs)
        if clock() >= deadline or (guarded and guarded.expired):
            raise TimeoutError('TradingView total request deadline exceeded')
        return result
    finally:
        client._TvDatafeed__create_connection = original_connect
        client._TvDatafeed__ws_timeout = original_timeout
        socket = guarded or getattr(client, 'ws', None)
        if socket:
            try:
                socket.close(timeout=0)
            except Exception:
                pass


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
    retries = min(1, max(0, int(max_retries)))
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
