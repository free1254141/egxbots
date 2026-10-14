"""Scheduling and freshness rules for the slower fundamentals source."""

from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo


def is_fundamentals_refresh_due(
    oldest_updated_at: Any,
    now: Optional[datetime] = None,
    max_age_days: int = 90,
) -> bool:
    """Return true when the oldest fundamentals snapshot is missing or stale."""
    if not oldest_updated_at:
        return True
    try:
        parsed = datetime.fromisoformat(str(oldest_updated_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return (current - parsed).total_seconds() >= max_age_days * 86400
    except (TypeError, ValueError, OverflowError):
        return True


def should_run_quarterly_fundamentals(
    trigger: str = "manual",
    phase: str = "close",
    now: Optional[datetime] = None,
) -> bool:
    """Run the quarterly source refresh only in the Sunday close window."""
    if str(trigger or "").strip().lower() != "scheduled" or phase != "close":
        return False
    current = now or datetime.now(ZoneInfo("Africa/Cairo"))
    return current.weekday() == 6


def quarterly_fundamentals_due(client: Any) -> Tuple[bool, str]:
    """Check the oldest persisted snapshot with one narrow Supabase read."""
    try:
        result = (
            client.table("stock_fundamentals")
            .select("updated_at")
            .eq("exchange", "EGX")
            .order("updated_at", desc=False)
            .limit(1)
            .execute()
        )
        oldest = (result.data or [{}])[0].get("updated_at") if result.data else None
        due = is_fundamentals_refresh_due(oldest)
        return due, "missing snapshot" if not oldest else (
            "oldest snapshot older than 90 days" if due else "all snapshots within 90 days"
        )
    except Exception as error:
        # A failed freshness check must not trigger an expensive provider call.
        return False, f"freshness check failed: {error}"
