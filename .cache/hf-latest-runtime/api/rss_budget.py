"""Bound optional RSS sweeps and distinguish outages from empty coverage."""
import time
import urllib.request
import xml.etree.ElementTree as ET


class RSSUnavailable(RuntimeError):
    pass


class RSSBudget:
    def __init__(self, seconds=180, max_failures=6):
        self.deadline = time.monotonic() + seconds
        self.max_failures = max_failures
        self.failures = 0
        self.succeeded = 0
        self.attempted = 0
        self.last_error = ''

    @property
    def stopped(self):
        return self.failures >= self.max_failures or time.monotonic() >= self.deadline

    def fetch(self, request):
        if self.stopped:
            raise RSSUnavailable('RSS sweep deadline or outage circuit reached')
        self.attempted += 1
        try:
            timeout = min(6, max(0.1, self.deadline - time.monotonic()))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= self.deadline:
                        raise RSSUnavailable('RSS sweep deadline reached')
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        raise RSSUnavailable('RSS response exceeds size budget')
                    chunks.append(chunk)
            root = ET.fromstring(b''.join(chunks))
            if root.tag != 'rss' or root.find('channel') is None:
                raise RSSUnavailable('Response is not a valid RSS feed')
            self.failures = 0
            self.succeeded += 1
            return root
        except Exception as error:
            self.failures += 1
            self.last_error = type(error).__name__
            raise

    def summary(self):
        return {'rss_attempted': self.attempted, 'rss_succeeded': self.succeeded,
                'consecutive_failures': self.failures, 'stopped': self.stopped,
                'last_error': self.last_error}
