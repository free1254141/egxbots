import pytest
from api.price_sync_policy import fetch_tradingview_history, bounded_setting


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Socket:
    def __init__(self, clock, *, completed=False):
        self.clock = clock
        self.completed = completed
        self.closed = False
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def send(self, *args):
        pass

    def recv(self, *args):
        self.clock.now += 3
        return 'series_completed' if self.completed else 'heartbeat'

    def close(self, timeout=0):
        self.closed = True


class Client:
    _TvDatafeed__ws_timeout = 15

    def __init__(self, socket):
        self.socket = socket
        self.calls = 0

    def _TvDatafeed__create_connection(self):
        self.ws = self.socket

    def get_hist(self, **kwargs):
        self._TvDatafeed__create_connection()
        self.ws.send('request')
        while True:
            self.calls += 1
            try:
                if self.ws.recv() == 'series_completed':
                    return 'complete dated bars'
            except Exception:
                # Model tvDatafeed swallowing receive errors and parsing partial data.
                return 'partial bars that must not reach the writer'


def test_heartbeats_cannot_extend_total_request_deadline(monkeypatch):
    monkeypatch.setenv('TRADINGVIEW_REQUEST_BUDGET', '10')
    clock = Clock()
    socket = Socket(clock)
    client = Client(socket)
    original = client._TvDatafeed__create_connection
    with pytest.raises(TimeoutError, match='total request deadline'):
        fetch_tradingview_history(client, clock=clock, symbol='COMI')
    assert client.calls == 4
    assert socket.closed and socket.timeouts[-1] == 1
    assert client._TvDatafeed__create_connection == original
    assert client._TvDatafeed__ws_timeout == 15


def test_completed_data_returns_and_socket_is_closed():
    clock = Clock()
    socket = Socket(clock, completed=True)
    assert fetch_tradingview_history(Client(socket), clock=clock) == 'complete dated bars'
    assert socket.closed


def test_failed_connection_restores_client():
    client = Client(None)
    def broken():
        raise ConnectionError('provider disconnected')
    client._TvDatafeed__create_connection = broken
    with pytest.raises(ConnectionError):
        fetch_tradingview_history(client)
    assert client._TvDatafeed__create_connection is broken


def test_fragmented_websocket_frame_cannot_bypass_deadline(monkeypatch):
    monkeypatch.setenv('TRADINGVIEW_REQUEST_BUDGET', '10')
    clock = Clock()
    raw = Socket(clock)
    class WebSocket:
        sock = raw
        def settimeout(self, value):
            self.sock.settimeout(value)
        def send(self, *args):
            self.sock.send(*args)
        def recv(self):
            # websocket-client may make several low-level reads per frame.
            while True:
                self.sock.recv(1024)
        def close(self, timeout=0):
            self.sock.close()
    with pytest.raises(TimeoutError):
        fetch_tradingview_history(Client(WebSocket()), clock=clock)
    assert clock.now == 12 and raw.closed


@pytest.mark.parametrize('value,expected', [('invalid', 4), ('nan', 4), ('999', 6), ('-1', 1)])
def test_concurrency_configuration_is_bounded(monkeypatch, value, expected):
    monkeypatch.setenv('SMART_SYNC_MAX_WORKERS', value)
    assert bounded_setting('SMART_SYNC_MAX_WORKERS', 4, 1, 6) == expected
