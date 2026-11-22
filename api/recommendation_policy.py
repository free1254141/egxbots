"""Deterministic daily-bar evaluation shared by production and offline replay.

Policy changes are explicit and versioned. This is an execution policy, not a
claim that an old trained model was trained with identical labels or barriers.
"""
from datetime import date, timedelta
from math import isfinite

POLICY_VERSION = "fixed_barriers_v2"
MAX_ENTRY_CLOSE_MISMATCH = 0.02
MAX_STOP_LOSS_DISTANCE = 0.10
MAX_CORPORATE_ACTION_DROP = 0.25
CONFIRMED_ACTION_GAP = 0.08
MAX_CORPORATE_ACTION_JUMP = 0.35
CORPORATE_ACTION_LOOKBACK_DAYS = 120


class CorporateActionDiscontinuity(ValueError):
    """Raised when a session bar reflects an unadjusted corporate action gap."""

    def __init__(self, day, prior_close, opening, close, *, confirmed=False):
        self.day = day
        self.prior_close = prior_close
        self.opening = opening
        self.close = close
        self.confirmed = bool(confirmed)
        self.change_pct = ((close / prior_close) - 1.0) * 100.0 if prior_close else 0.0
        super().__init__(
            f"Unadjusted corporate action discontinuity on {day}: "
            f"prior_close={prior_close} -> open={opening}, close={close}"
        )


def corporate_action_confirmed(day: str, action_dates) -> bool:
    """Return True if any known corporate action date falls within [-120d, +1d] of day."""
    try:
        day_date = date.fromisoformat(str(day)[:10])
    except (ValueError, TypeError):
        return False
    min_date = day_date - timedelta(days=CORPORATE_ACTION_LOOKBACK_DAYS)
    max_date = day_date + timedelta(days=1)
    for raw in action_dates or ():
        try:
            action_date = date.fromisoformat(str(raw)[:10])
        except (ValueError, TypeError):
            continue
        if min_date <= action_date <= max_date:
            return True
    return False


def is_corporate_action_gap(
    prior_close,
    opening,
    close,
    *,
    confirmed: bool = False,
    drop_threshold: float = MAX_CORPORATE_ACTION_DROP,
) -> bool:
    """Detect session gaps caused by unadjusted corporate actions (rights, splits, etc.)."""
    prior_val = positive(prior_close)
    close_val = positive(close)
    if prior_val is None or close_val is None:
        return False
    open_val = positive(opening) if opening is not None else None
    close_chg = close_val / prior_val - 1.0
    open_chg = (open_val / prior_val - 1.0) if open_val is not None else None

    if (
        close_chg <= -drop_threshold
        or (open_chg is not None and open_chg <= -drop_threshold and close_chg <= -0.20)
        or close_chg >= MAX_CORPORATE_ACTION_JUMP
        or (open_chg is not None and open_chg >= MAX_CORPORATE_ACTION_JUMP)
    ):
        return True

    if confirmed:
        ref_chg = open_chg if open_chg is not None else close_chg
        if ref_chg <= -CONFIRMED_ACTION_GAP:
            return True
    return False


def corporate_action_rebase_factor(prior_close, opening, close) -> float:
    """Compute multiplicative price-adjustment factor (ref_after / prior_close)."""
    prior_val = positive(prior_close)
    close_val = positive(close)
    if prior_val is None or close_val is None:
        return 1.0
    open_val = positive(opening) if opening is not None else None
    ref_after = (
        close_val
        if (open_val is None or abs(close_val / open_val - 1.0) <= 0.03)
        else open_val
    )
    return ref_after / prior_val


def positive(value):
    try:
        number = float(value)
        return number if isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def valid_candidate(row, minimum_rr=1.5, max_stop_pct=MAX_STOP_LOSS_DISTANCE):
    return candidate_assessment(row, minimum_rr=minimum_rr, max_stop_pct=max_stop_pct)["accepted"]


def candidate_assessment(row, minimum_rr=1.5, max_stop_pct=MAX_STOP_LOSS_DISTANCE):
    entry, target, stop = (positive(row.get(key)) for key in ("last_close", "target_price", "stop_loss"))
    result = dict(symbol=row.get("symbol"), entry=entry, target=target, stop=stop,
                  minimum_rr=minimum_rr, risk_reward=None, accepted=False)
    if entry is None or target is None or stop is None or not stop < entry < target:
        return {**result, "reason": "invalid_price_geometry"}
    stop_dist = (entry - stop) / entry
    rr = (target - entry) / (entry - stop)
    result = {**result, "risk_reward": round(rr, 6), "stop_distance_pct": round(stop_dist * 100, 4)}
    if max_stop_pct is not None and stop_dist > max_stop_pct + 1e-6:
        return {**result, "accepted": False, "reason": "stop_loss_too_wide"}
    return {**result, "accepted": rr >= minimum_rr,
            "reason": "accepted" if rr >= minimum_rr else "risk_reward_below_minimum"}


def resolve_signal_reference(entry, bars, published_date, price_date=None, max_age_days=14, *, rebased=False, corporate_action_dates=None):
    """Use the latest actual session, not the timestamp of publication.

    Never search older matching prices when the latest reference disagrees.
    Never infer a corporate-action adjustment from a coincidental price match.
    """
    from datetime import date
    cutoff = str(price_date or published_date)[:10]
    prior = [b for b in bars if str(b.get("date", ""))[:10] <= cutoff]
    if not prior:
        return {"ok": False, "reason": "missing_signal_history"}
    reference = max(prior, key=lambda b: str(b["date"])[:10])
    day = str(reference["date"])[:10]
    if price_date and day != cutoff:
        return {"ok": False, "reason": "missing_explicit_signal_bar", "price_date": day}
    age = (date.fromisoformat(str(published_date)[:10]) - date.fromisoformat(day)).days
    if age < 0 or age > max_age_days:
        return {"ok": False, "reason": "stale_signal_reference", "price_date": day}
    if price_basis_matches(entry, reference.get("close")):
        return dict(ok=True, reason="verified_last_trading_session", price_date=day, close=reference.get("close"))
    if rebased:
        prev_close = positive(reference.get("close"))
        cum_factor = 1.0
        future_bars = sorted((b for b in bars if str(b.get("date", ""))[:10] > day), key=lambda b: str(b.get("date", ""))[:10])
        for bar in future_bars:
            b_close = positive(bar.get("close"))
            b_open = positive(bar.get("open")) if bar.get("open") is not None else None
            if b_close is None or prev_close is None:
                continue
            confirmed = corporate_action_confirmed(str(bar.get("date", ""))[:10], corporate_action_dates or ())
            if is_corporate_action_gap(prev_close, b_open, b_close, confirmed=confirmed):
                cum_factor *= corporate_action_rebase_factor(prev_close, b_open, b_close)
                ref_scaled = positive(reference.get("close")) * cum_factor
                if price_basis_matches(entry, ref_scaled, tolerance=0.03):
                    return dict(ok=True, reason="verified_rebased_signal_reference", price_date=day, close=reference.get("close"))
            prev_close = b_close
    return dict(ok=False, reason="incompatible_price_basis", price_date=day, close=reference.get("close"))


def profit_protection_stop(entry, stop, bars, day, policy):
    """ATR protection calculated with data available at this close only."""
    if not policy or day < str(policy.get("effective_from", "9999")):
        return None
    history = sorted((b for b in bars if str(b["date"])[:10] <= day), key=lambda b: str(b["date"]))
    window = int(policy.get("atr_window", 14))
    if len(history) < window + 1:
        return None
    last = history[-1]
    close = positive(last.get("close"))
    if not close or (last.get("volume") is not None and float(last["volume"]) <= 0):
        return None
    if (close / entry - 1) * 100 < float(policy.get("trigger_pct", 5)):
        return None
    ranges = []
    for previous, current in zip(history[-window-1:-1], history[-window:]):
        high, low, prior_close = (positive(v) for v in (current.get("high"), current.get("low"), previous.get("close")))
        if high is None or low is None or prior_close is None or high < low:
            return None
        ranges.append(max(high-low, abs(high-prior_close), abs(low-prior_close)))
    atr = sum(ranges) / window
    closes = [positive(b.get("close")) for b in history[-20:]]
    if any(c is None for c in closes):
        return None
    trending = len(closes) == 20 and close >= sum(closes) / len(closes)
    multiplier = float(policy.get("trend_atr_multiple", 2.5) if trending else policy.get("atr_multiple", 2))
    distance = max(multiplier * atr, close * float(policy.get("minimum_distance_pct", 3)) / 100)
    candidate = round(close - distance, 6)
    if not max(entry, stop or 0) < candidate < close:
        return None
    return dict(type="stop_raised", old_stop=stop, new_stop=candidate, current_price=close,
                pl_pct=(close/entry-1)*100, effective_after=day, timestamp=f"{day}T23:59:59",
                atr=round(atr, 6), atr_multiple=multiplier, policy_version=policy.get("version"),
                reason_ar="حماية الربح بوقف متحرك حسب التقلب والاتجاه؛ يسري من الجلسة التالية",
                reason_en="ATR profit protection effective from the next session")


def price_basis_matches(entry, signal_close, tolerance=MAX_ENTRY_CLOSE_MISMATCH):
    """Reject a mixed adjusted/raw price history before comparing barriers."""
    entry, signal_close = positive(entry), positive(signal_close)
    return (entry is not None and signal_close is not None and
            abs(signal_close / entry - 1) <= tolerance)


def evaluate_bars(*, entry, target, stop, bars, entry_date, cursor, max_sessions=None,
                  trail_pct=None, trail_trigger_pct=5.0, sector_risk_by_date=None,
                  recommendation_sector=None, recommendation_symbol=None,
                  weak_symbols_by_date=None, profit_protection=None,
                  max_corporate_action_drop=MAX_CORPORATE_ACTION_DROP,
                  corporate_action_dates=None,
                  rebase_corporate_actions=True):
    """Process new bars in order; adjustments take effect on the NEXT bar.

    A cursor is a market-data date, never a row's last modification timestamp.
    Legacy positions can have stop > entry after locking a profit. Missing or
    invalid OHLC makes evaluation fail closed, rather than inventing prices.
    """
    entry, target, stop = positive(entry), positive(target), positive(stop)
    if entry is None or target is None or stop is None:
        raise ValueError("Missing positive entry/target/stop")
    if max_sessions is not None and max_sessions < 1:
        raise ValueError("max_sessions must be positive")
    if trail_pct is not None and not 0 < trail_pct < 1:
        raise ValueError("trail_pct must be between zero and one")
    by_date = {str(bar.get("date", ""))[:10]: dict(bar) for bar in bars}
    scaled_bars = list(by_date.values())
    prior_bars = sorted((d for d in by_date if d <= entry_date), key=str)
    prior_close = positive(by_date[prior_bars[-1]].get("close")) if prior_bars else None
    if prior_close is None:
        prior_close = entry
    entry_ref_close = prior_close
    cum_bar_factor = 1.0
    session_dates = sorted(day for day in by_date if day > entry_date and
                           (by_date[day].get("volume") is None or float(by_date[day]["volume"]) > 0))
    result = dict(status="open", exit_price=None, exit_reason=None, closed_on=None,
                  entry_price=entry, target_price=target, stop_loss=stop,
                  cursor=cursor, last_close=None, sessions_held=0,
                  profit_loss_pct=None, adjustments=[], rebased=False, rebase_factor=1.0)
    for session, day in enumerate(session_dates, 1):
        bar = by_date[day]
        high, low, close = (positive(bar.get(key)) for key in ("high", "low", "close"))
        opening = positive(bar.get("open"))
        if high is None or low is None or close is None or not low <= close <= high:
            raise ValueError(f"Invalid OHLC on {day}")
        if bar.get("open") is not None and (opening is None or not low <= opening <= high):
            raise ValueError(f"Invalid opening price on {day}")
        if max_corporate_action_drop is not None and prior_close is not None and prior_close > 0:
            confirmed = corporate_action_confirmed(day, corporate_action_dates or ())
            if is_corporate_action_gap(
                prior_close,
                opening,
                close,
                confirmed=confirmed,
                drop_threshold=max_corporate_action_drop,
            ):
                if not rebase_corporate_actions or not confirmed:
                    raise CorporateActionDiscontinuity(
                        day, prior_close, opening, close, confirmed=confirmed
                    )
                factor = corporate_action_rebase_factor(prior_close, opening, close)
                unscaled_entry_ref = entry_ref_close * cum_bar_factor
                scaled_entry_ref = unscaled_entry_ref * factor
                needs_barrier_rebase = abs(entry / unscaled_entry_ref - 1.0) <= abs(entry / scaled_entry_ref - 1.0)
                cum_bar_factor *= factor
                for prev_day, prev_bar in by_date.items():
                    if prev_day < day:
                        for price_key in ("open", "high", "low", "close"):
                            val = positive(prev_bar.get(price_key))
                            if val is not None:
                                prev_bar[price_key] = val * factor
                if needs_barrier_rebase:
                    decimals = 3 if (entry * factor) < 2.0 else 2
                    old_entry, old_target, old_stop = entry, target, stop
                    entry = round(entry * factor, decimals)
                    target = round(target * factor, decimals)
                    stop = round(stop * factor, decimals)
                    result["entry_price"] = entry
                    result["target_price"] = target
                    result["stop_loss"] = stop
                    result["rebased"] = True
                    result["rebase_factor"] = round(result["rebase_factor"] * factor, 6)
                    result.setdefault("rebased_day", day)
                    if not any(
                        isinstance(adj, dict) and adj.get("type") == "corporate_action_rebase" and adj.get("effective_after") == day
                        for adj in result["adjustments"]
                    ):
                        result["adjustments"].append(dict(
                            type="corporate_action_rebase",
                            old_entry=old_entry,
                            new_entry=entry,
                            old_target=old_target,
                            new_target=target,
                            old_stop=old_stop,
                            new_stop=stop,
                            rebase_factor=round(factor, 6),
                            prior_close=prior_close,
                            current_price=close,
                            pl_pct=round((close / entry - 1.0) * 100.0, 2),
                            effective_after=day,
                            timestamp=f"{day}T23:59:59",
                            confirmed=confirmed,
                            reason_ar=f"تعديل تلقائي لمستويات التوصية بعد حدث رأسمالي / تقسيم (معامل {factor:.4f})",
                            reason_en=f"Automatic price rebase after corporate action / split (factor {factor:.4f})",
                        ))
        prior_close = close
        if day <= cursor:
            continue
        result.update(cursor=day, last_close=close, sessions_held=session)
        exit_price, reason = None, None
        if low <= stop:
            exit_price = min(opening, stop) if opening is not None else stop
            reason = "stop_hit"
        elif high >= target:
            exit_price, reason = target, "target_hit"
        elif max_sessions is not None and session >= max_sessions:
            exit_price, reason = close, "time_exit"
        # Sector risk is evaluated at the session close, after intraday barriers.
        # The caller only supplies dates where both broad-market weakness and
        # sector distribution were independently confirmed.
        risk = (sector_risk_by_date or {}).get(day, {})
        weak_symbols = (weak_symbols_by_date or {}).get(day, set())
        weak_stock = recommendation_symbol and recommendation_symbol in weak_symbols
        if exit_price is None and recommendation_sector and recommendation_sector in risk and weak_stock:
            exit_price, reason = close, "sector_distribution_exit"
        if exit_price is not None:
            pnl = (exit_price / entry - 1) * 100
            result.update(status="win" if pnl >= 0 else "loss", exit_price=exit_price,
                          profit_loss_pct=pnl, closed_on=day, exit_reason=reason)
            if reason == "sector_distribution_exit":
                result["sector_risk"] = risk[recommendation_sector]
            return result
        result["profit_loss_pct"] = (close / entry - 1) * 100
        if trail_pct is not None and result["profit_loss_pct"] >= trail_trigger_pct:
            candidate = close * (1 - trail_pct)
            if stop < candidate < close:
                result["adjustments"].append(dict(type="stop_raised", old_stop=stop,
                    new_stop=candidate, current_price=close,
                    pl_pct=result["profit_loss_pct"], effective_after=day,
                    timestamp=f"{day}T23:59:59", reason_ar="حماية الربح من الجلسة التالية",
                    reason_en="Profit protection from next session"))
                stop = candidate
                result["stop_loss"] = stop
        adjustment = profit_protection_stop(entry, stop, scaled_bars, day, profit_protection)
        if adjustment:
            result["adjustments"].append(adjustment)
            stop = adjustment["new_stop"]
            result["stop_loss"] = stop
    # Policy activation may happen after this session was already evaluated.
    # Raise tomorrow's stop without re-evaluating today's intraday barriers.
    if result["last_close"] is None and by_date and cursor in by_date:
        adjustment = profit_protection_stop(entry, stop, scaled_bars, cursor, profit_protection)
        if adjustment:
            result.update(last_close=adjustment["current_price"], stop_loss=adjustment["new_stop"],
                          profit_loss_pct=adjustment["pl_pct"], sessions_held=len([d for d in session_dates if d <= cursor]),
                          adjustments=result["adjustments"] + [adjustment])
    if result["last_close"] is None and result.get("rebased"):
        cursor_bar = by_date.get(cursor)
        if cursor_bar is None:
            prior_cursor_days = [d for d in session_dates if d <= cursor]
            if prior_cursor_days:
                cursor_bar = by_date.get(prior_cursor_days[-1])
        cursor_close = positive(cursor_bar.get("close")) if cursor_bar else None
        if cursor_close is not None:
            result.update(
                last_close=cursor_close,
                profit_loss_pct=(cursor_close / entry - 1.0) * 100.0,
                sessions_held=len([d for d in session_dates if d <= cursor]),
            )
    return result
