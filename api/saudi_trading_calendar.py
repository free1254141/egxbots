"""Saudi Exchange (Tadawul / TASI) trading-day calendar checks."""
from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

SAUDI_TZ = ZoneInfo("Asia/Riyadh")

# Official Tadawul (Saudi Exchange) holidays — keep 2026 Founding / Eid / National Day
# dates configurable via SAUDI_HOLIDAY_DATES CSV env override.
CONFIRMED_SAUDI_CLOSURES = frozenset({
    "2026-02-22",  # Saudi Founding Day
    "2026-09-23",  # Saudi National Day
})


def _holiday_dates() -> frozenset[str]:
    configured = os.getenv("SAUDI_HOLIDAY_DATES", "")
    extra = {item.strip() for item in configured.split(",") if item.strip()}
    return CONFIRMED_SAUDI_CLOSURES | extra


def is_saudi_session(day: dt.datetime | dt.date | None = None) -> bool:
    """Return True when the Saudi Exchange (Tadawul) is open on that Asia/Riyadh day."""
    if day is None:
        target_day = dt.datetime.now(SAUDI_TZ).date()
    elif isinstance(day, dt.datetime):
        target_day = day.astimezone(SAUDI_TZ).date() if day.tzinfo else day.date()
    else:
        target_day = day

    # Tadawul operates Sunday..Thursday (Friday=4, Saturday=5 are weekend).
    if target_day.weekday() in {4, 5}:
        return False
    return target_day.isoformat() not in _holiday_dates()
