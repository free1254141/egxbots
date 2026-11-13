"""Compatibility import path for the subscription reminder job.

The canonical implementation lives in
``api.jobs.telegram_subscription_reminders``. This module only re-exports it so
the scheduler, the close job and older imports never run two different copies
of the same logic (which previously caused duplicate reminder deliveries).
"""
from __future__ import annotations

from api.jobs.telegram_subscription_reminders import (  # noqa: F401
    CAIRO,
    LIFETIME_KEYWORDS,
    SITE_URL,
    determine_reminder_stage,
    get_supabase_config,
    get_telegram_token,
    is_lifetime_plan,
    main,
    message_for,
    parse_chat_id,
    run_subscription_reminders,
    send_private_telegram,
)

__all__ = [
    "CAIRO",
    "LIFETIME_KEYWORDS",
    "SITE_URL",
    "determine_reminder_stage",
    "get_supabase_config",
    "get_telegram_token",
    "is_lifetime_plan",
    "main",
    "message_for",
    "parse_chat_id",
    "run_subscription_reminders",
    "send_private_telegram",
]


if __name__ == "__main__":
    raise SystemExit(main())
