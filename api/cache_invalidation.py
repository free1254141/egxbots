"""Event-driven CDN cache invalidation for the daily job.

After the daily Python job finishes, the public Next.js routes that serve
daily data must stop serving yesterday's cached payloads. Each route tags its
CDN response with one of the `daily-*` cache tags; this module asks Vercel to
invalidate exactly the tags whose data was refreshed successfully.

Rules:
  * Nothing is invalidated when the essential price sync failed.
  * A tag is invalidated only when every step feeding it succeeded.
  * Network/HTTP failures are logged and never break the daily run.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

_COOLDOWN_LOCK = threading.Lock()
_LAST_INVALIDATED_AT: Dict[Tuple[str, str], float] = {}


def reset_revalidation_cooldown() -> None:
    """Clear per-tag invalidation timestamps (primarily for deterministic tests)."""
    with _COOLDOWN_LOCK:
        _LAST_INVALIDATED_AT.clear()


def _cooldown_seconds() -> float:
    raw = (os.getenv("REVALIDATE_COOLDOWN_SECONDS") or "900").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 900.0

TAG_MARKET = "daily-market-data"
TAG_NEWS = "daily-news-data"
TAG_RECOMMENDATIONS = "daily-recommendations"
TAG_SYMBOLS = "daily-symbols"
TAG_SHORT_SWINGS = "daily-short-swings"
TAG_DISCLOSURES = "daily-disclosures"

# Steps that must complete before a tag's data can be considered refreshed.
# `required_all` must every succeed; `required_any` needs at least one, which
# keeps invalidation working when a run performs only part of a pipeline.
TAG_STEP_REQUIREMENTS: Dict[str, Dict[str, tuple]] = {
    "daily-public-reports": {"required_all": ("social_reports_ready",), "required_any": ()},
    TAG_MARKET: {"required_all": ("sync_prices", "calculate_indicators"), "required_any": ()},
    TAG_NEWS: {"required_all": ("news_sentiment",), "required_any": ()},
    TAG_RECOMMENDATIONS: {"required_all": (), "required_any": ("generate_recommendations", "evaluate_recommendations")},
    TAG_SYMBOLS: {"required_all": ("sync_inventory",), "required_any": ()},
    TAG_SHORT_SWINGS: {"required_all": ("short_swings_daily",), "required_any": ()},
    TAG_DISCLOSURES: {"required_all": (), "required_any": ("egx_disclosures",)},
}

# Losing the price sync makes every downstream daily payload stale, so the run
# must not advertise fresh data at all.
ESSENTIAL_STEPS = ("sync_prices",)

_SUCCESS_STATUSES = {"success", "completed", "skipped"}


def _latest_step_status(steps: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    latest: Dict[str, str] = {}
    for step in steps or []:
        name = str(step.get("step") or step.get("name") or "").strip()
        if not name:
            continue
        latest[name] = str(step.get("status") or "").strip().lower()
    return latest


def select_cache_tags(steps: List[Dict[str, Any]], changed_steps=None) -> List[str]:
    """Return the cache tags that a completed run may safely invalidate."""
    from api.daily_job_outcome import effective_daily_steps
    from api.price_sync_policy import price_sync_usable
    effective = effective_daily_steps(steps)
    latest = _latest_step_status(effective)
    sync = next((s for s in effective if s.get('step') == 'sync_prices'), None)
    prices_usable = price_sync_usable(sync)

    for step in ESSENTIAL_STEPS:
        if not (prices_usable if step == 'sync_prices' else latest.get(step) == 'success'):
            return []

    tags = []
    for tag, requirements in TAG_STEP_REQUIREMENTS.items():
        if changed_steps is not None and not set(changed_steps).intersection(
                requirements.get('required_all', ()) + requirements.get('required_any', ())):
            continue
        required_all = requirements.get("required_all", ())
        required_any = requirements.get("required_any", ())
        all_ok = all(prices_usable if step == 'sync_prices' else latest.get(step) in _SUCCESS_STATUSES for step in required_all)
        any_ok = (not required_any) or any(latest.get(step) in _SUCCESS_STATUSES for step in required_any)
        if all_ok and any_ok:
            tags.append(tag)
    return tags


def _revalidate_endpoint() -> Optional[str]:
    explicit = (os.getenv("REVALIDATE_URL") or "").strip()
    if explicit:
        return explicit
    origin = (os.getenv("WEB_ORIGIN") or "").strip().rstrip("/")
    if not origin or "localhost" in origin or "127.0.0.1" in origin:
        return None
    return f"{origin}/api/revalidate"


def invalidate_daily_cache(steps: List[Dict[str, Any]], timeout: float = 310.0, force: bool = False) -> Dict[str, Any]:
    """Ask Vercel to invalidate the daily cache tags for a completed run."""
    tags = select_cache_tags(steps)
    if not tags:
        print("[CACHE] No cache tags to invalidate (essential step not successful).")
        return {"invalidated": [], "skipped": True}

    return invalidate_cache_tags(tags, timeout, force=force)


def _post_revalidate(endpoint: str, secret: str, tags: List[str], event_id: str, timeout: float) -> Tuple[Optional[int], Optional[str]]:
    payload = json.dumps({"tags": tags, "event_id": event_id}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
        },
    )
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="ignore")
            print(f"[CACHE] Invalidated {tags}: HTTP {response.status} {body[:200]}")
            return response.status, None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")[:200]
            print(f"[CACHE] Revalidation HTTP {error.code} for {tags}: {detail}")
            last_error = f"HTTP {error.code}"
            if error.code < 500 or attempt == 1:
                return None, last_error
        except Exception as error:  # network, DNS, timeout — never break the job
            print(f"[CACHE] Revalidation failed for {tags}: {error}")
            last_error = str(error)
            if attempt == 1:
                return None, last_error
        time.sleep(1.5)
    return None, last_error


def invalidate_local_hf_caches(tags: List[str]) -> List[str]:
    """Clear in-process HF memory caches for refreshed daily tags immediately on run completion."""
    cleared: List[str] = []
    try:
        from api.routers.offload import invalidate_offload_caches
        cleared.extend(invalidate_offload_caches(tags))
    except Exception as exc:
        print(f"[CACHE] Offload cache invalidation warning: {exc}")
    try:
        from api.routers.offload_public import invalidate_public_offload_caches
        cleared.extend(invalidate_public_offload_caches(tags))
    except Exception as exc:
        print(f"[CACHE] Public offload cache invalidation warning: {exc}")
    try:
        from api.routers.offload_user import invalidate_user_router_public_caches
        cleared.extend(invalidate_user_router_public_caches(tags))
    except Exception as exc:
        print(f"[CACHE] User offload cache invalidation warning: {exc}")
    if TAG_SHORT_SWINGS in tags:
        try:
            from api.routers.short_swings import clear_saudi_swings_cache
            clear_saudi_swings_cache()
            cleared.append("saudi_short_swings")
        except Exception as exc:
            print(f"[CACHE] Short swings cache invalidation warning: {exc}")
    return cleared


def invalidate_cache_tags(tags: List[str], timeout: float = 310.0, force: bool = False) -> Dict[str, Any]:
    """Refresh explicit datasets after independent successful scheduled jobs with cooldown dedup."""
    if not tags or any(tag not in TAG_STEP_REQUIREMENTS for tag in tags):
        return {"invalidated": [], "skipped": True}

    deduped_tags = list(dict.fromkeys(tags))
    local_cleared = invalidate_local_hf_caches(deduped_tags)
    if local_cleared:
        print(f"[CACHE] Cleared local HF caches {local_cleared} for tags {deduped_tags}")

    endpoint = _revalidate_endpoint()
    secret = (os.getenv("REVALIDATE_SECRET") or os.getenv("ADMIN_SECRET_KEY") or "").strip()
    if not endpoint or not secret:
        print("[CACHE] Revalidation skipped: REVALIDATE_URL/WEB_ORIGIN or REVALIDATE_SECRET not configured.")
        return {"invalidated": [], "skipped": True}
    cooldown = _cooldown_seconds()
    cooldown_skipped: List[str] = []
    if not force and cooldown > 0:
        now = time.monotonic()
        with _COOLDOWN_LOCK:
            active_tags = [
                t for t in deduped_tags
                if (now - _LAST_INVALIDATED_AT.get((endpoint, t), float("-inf"))) >= cooldown
            ]
            cooldown_skipped = [t for t in deduped_tags if t not in active_tags]
    else:
        active_tags = deduped_tags

    if not active_tags:
        print(f"[CACHE] Revalidation debounced by {int(cooldown)}s cooldown for {deduped_tags}")
        return {"invalidated": [], "skipped": True, "reason": "cooldown", "debounced": cooldown_skipped}

    def _record_success(succeeded_tags: List[str]) -> None:
        stamp = time.monotonic()
        with _COOLDOWN_LOCK:
            for t in succeeded_tags:
                _LAST_INVALIDATED_AT[(endpoint, t)] = stamp

    # Stable across HTTP retries: Vercel stages data before switching generation.
    event_id = datetime.now(timezone.utc).isoformat()
    status, error = _post_revalidate(endpoint, secret, active_tags, event_id, timeout)
    if not error:
        _record_success(active_tags)
        return {
            "invalidated": active_tags,
            "skipped": False,
            "status": status,
            **({"debounced": cooldown_skipped} if cooldown_skipped else {}),
        }

    # If a multi-tag batch hit a single-tag upstream glitch (e.g. HTTP 500 on one dataset),
    # fall back to invalidating each tag individually so healthy tags are never blocked.
    if len(active_tags) > 1:
        invalidated: List[str] = []
        tag_errors: List[str] = []
        for single_tag in active_tags:
            s_status, s_err = _post_revalidate(endpoint, secret, [single_tag], datetime.now(timezone.utc).isoformat(), timeout)
            if not s_err:
                invalidated.append(single_tag)
            else:
                tag_errors.append(f"{single_tag}:{s_err}")
        if invalidated:
            _record_success(invalidated)
        if invalidated and not tag_errors:
            return {"invalidated": invalidated, "skipped": False, "status": 200}
        return {
            "invalidated": invalidated,
            "skipped": False,
            **({"error": "; ".join(tag_errors)} if tag_errors else {}),
        }

    return {"invalidated": [], "skipped": False, "error": error}
