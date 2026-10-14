import os
import pytest


@pytest.fixture(autouse=True)
def prevent_outbound_telegram(monkeypatch):
    """Enforce hermetic Telegram execution across all pytest suites."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    monkeypatch.setenv("TELEGRAM_TEST_MODE", "true")
