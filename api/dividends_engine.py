"""
api/dividends_engine.py
Unified 4-Market Institutional Dividends Calendar, Auto-Portfolio Credit & Notification Engine.

Markets covered:
  - EGX (Egypt — EGP & USD tickers like FAITA/EGBE/MOIL)
  - TADAWUL / TASI (Saudi Arabia — SAR)
  - QSE (Qatar — QAR)
  - UAE (DFM + ADX — AED)

Architecture (HF-First, 0 Vercel Active CPU):
  1. Tier 1 — TradingView Bulk Scanner API (1 request per market, < 1s):
     Captures ALL upcoming ex-dividend dates & amounts + recent dividend payouts across all 4 markets.
  2. Tier 2 — StockAnalysis `/dividend/` HTML parser (parallel bounded pool for upcoming/recent stocks):
     Enriches exact `record_date` (نهاية الحق), `pay_date` (تاريخ الصرف), and 5-year payout history.
  3. Storage (Dual-mode graceful):
     - Always persists compact market calendar payloads to `market_cache` (`dividends_calendar_{market}`)
       so Public API, Website Calendar Pages, Stock Detail pages, and ARTORO Chat work immediately.
     - Upserts structured rows into `stock_dividends` when migration `20261120140000` is applied.
  4. Portfolio Auto-Credit & Alerts (`process_portfolio_dividends`):
     - Matches open user `positions` bought before `ex_date`.
     - Sends idempotent in-app (`user_notifications`) + Telegram alerts ahead of `ex_date`.
     - Credits `profiles.cash_balance` on `pay_date` (strictly idempotent via `user_dividend_events` UNIQUE key).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("dividends_engine")
CAIRO_TZ = ZoneInfo("Africa/Cairo")

_TV_ENDPOINTS: Dict[str, Tuple[str, str, str]] = {
    # market_key -> (tv_region, default_exchange, default_currency)
    "egx": ("egypt", "EGX", "EGP"),
    "tasi": ("ksa", "TADAWUL", "SAR"),
    "qatar": ("qatar", "QSE", "QAR"),
    "uae": ("uae", "DFM", "AED"),
}

_SA_EXCHANGE_SLUG: Dict[str, str] = {
    "EGX": "egx",
    "TADAWUL": "tadawul",
    "TASI": "tadawul",
    "QSE": "qse",
    "DFM": "dfm",
    "ADX": "adx",
}

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_CURRENCY_AR_MAP = {
    "EGP": "ج.م",
    "USD": "$",
    "SAR": "ر.س",
    "QAR": "ر.ق",
    "AED": "د.إ",
    "KWD": "د.ك",
}

_COUNTRY_MAP = {
    "egx": "Egypt",
    "tasi": "Saudi Arabia",
    "qatar": "Qatar",
    "uae": "UAE",
}


def _today_cairo() -> dt.date:
    try:
        return dt.datetime.now(CAIRO_TZ).date()
    except Exception:
        return dt.datetime.now(dt.timezone.utc).date()


def _ts_to_iso_date(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    try:
        val = float(ts)
        if val <= 0:
            return None
        return dt.datetime.fromtimestamp(val, tz=dt.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def _safe_float(val: Any, decimals: int = 4) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return round(f, decimals)
    except Exception:
        return None


def _parse_iso_date(val: Any) -> Optional[dt.date]:
    if not val:
        return None
    s = str(val).strip()[:10]
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None


def _currency_ar(code: str) -> str:
    return _CURRENCY_AR_MAP.get(str(code or "").upper(), str(code or "EGP"))


def _get_primary_sb():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _get_gcc_sb():
    from supabase import create_client
    url = os.getenv("SAUDI_SUPABASE_URL")
    key = os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SAUDI_SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Tier 1: TradingView Bulk Scanner (Upcoming + Recent Dividends)
# ---------------------------------------------------------------------------
def fetch_tv_market_dividends(market_key: str) -> List[Dict[str, Any]]:
    """Fetch upcoming & recent dividend records for a market via TradingView bulk scanner."""
    if market_key not in _TV_ENDPOINTS:
        return []
    tv_region, default_exch, default_curr = _TV_ENDPOINTS[market_key]
    url = f"https://scanner.tradingview.com/{tv_region}/scan"
    cols = [
        "name",
        "description",
        "close",
        "currency",
        "exchange",
        "dividend_ex_date_upcoming",
        "dividend_amount_upcoming",
        "dividend_pay_date_upcoming",
        "dividend_ex_date_recent",
        "dividend_amount_recent",
        "dividend_pay_date_recent",
        "dividend_yield_recent",
        "dps_common_stock_prim_issue_fy",
    ]
    payload = json.dumps({
        "columns": cols,
        "range": [0, 450],
        "sort": {"sortBy": "dividend_ex_date_upcoming", "sortOrder": "desc"},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": _BROWSER_HEADERS["User-Agent"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as exc:
        logger.warning(f"[dividends_engine] TV fetch failed for {market_key}: {exc}")
        return []

    today = _today_cairo()
    cutoff_recent = today - dt.timedelta(days=240)
    out: List[Dict[str, Any]] = []

    for row in body.get("data") or []:
        full_ticker = str(row.get("s") or "")
        d = row.get("d") or []
        if len(d) < len(cols):
            continue
        sym = str(d[0] or "").strip().upper()
        if not sym:
            continue
        raw_exch = str(d[4] or (full_ticker.split(":")[0] if ":" in full_ticker else default_exch)).strip().upper()
        # Filter out foreign cross-listings (e.g. NDAQ on UAE scanner)
        if market_key == "uae" and raw_exch not in ("DFM", "ADX"):
            continue
        if market_key == "egx" and raw_exch != "EGX":
            continue
        if market_key == "tasi" and raw_exch not in ("TADAWUL", "TASI"):
            continue
        if market_key == "qatar" and raw_exch not in ("QSE", "QE"):
            continue
        exch = "TADAWUL" if raw_exch == "TASI" else ("QSE" if raw_exch == "QE" else raw_exch)

        name_en = str(d[1] or sym).strip()
        close = _safe_float(d[2], 4)
        curr = str(d[3] or default_curr).strip().upper()
        ex_up = _ts_to_iso_date(d[5])
        amt_up = _safe_float(d[6], 4)
        pay_up = _ts_to_iso_date(d[7])
        ex_rec = _ts_to_iso_date(d[8])
        amt_rec = _safe_float(d[9], 4)
        pay_rec = _ts_to_iso_date(d[10])
        ann_yield = _safe_float(d[11], 2)
        fy_dps = _safe_float(d[12], 4)

        # Prefer upcoming event if valid; otherwise capture recent dividend within 240 days
        chosen_ex = None
        chosen_amt = None
        chosen_pay = None
        is_upcoming = False

        if ex_up and amt_up and amt_up > 0:
            ex_d = _parse_iso_date(ex_up)
            if ex_d and ex_d >= today - dt.timedelta(days=7):
                chosen_ex = ex_up
                chosen_amt = amt_up
                chosen_pay = pay_up
                is_upcoming = ex_d >= today
        if not chosen_ex and ex_rec and amt_rec and amt_rec > 0:
            ex_d = _parse_iso_date(ex_rec)
            if ex_d and ex_d >= cutoff_recent:
                chosen_ex = ex_rec
                chosen_amt = amt_rec
                chosen_pay = pay_rec
                is_upcoming = ex_d >= today

        if not chosen_ex or not chosen_amt or chosen_amt <= 0:
            continue

        coupon_yield_pct = round((chosen_amt / close) * 100.0, 2) if (close and close > 0) else None
        out.append({
            "exchange": exch,
            "market": market_key,
            "symbol": sym,
            "name_en": name_en,
            "amount": round(chosen_amt, 4),
            "currency": curr,
            "currency_ar": _currency_ar(curr),
            "ex_date": chosen_ex,
            "record_date": None,
            "pay_date": chosen_pay,
            "close_price": round(close, 4) if close else None,
            "yield_pct": coupon_yield_pct,
            "annual_yield_pct": ann_yield,
            "fy_dps": fy_dps,
            "is_upcoming": is_upcoming,
            "source": "tradingview",
            "history": [],
        })

    return out


# ---------------------------------------------------------------------------
# Tier 2: StockAnalysis `/dividend/` Enricher (Exact Record Date, Pay Date, History)
# ---------------------------------------------------------------------------
_SA_HIST_OBJ_RE = re.compile(
    r'\{dt:"([^"]+)",amt:"([^"]+)",dec:"([^"]*)",record:"([^"]*)",pay:"([^"]*)"\}'
)


def fetch_stockanalysis_dividend_details(exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch exact ex_date, record_date, pay_date, and historical payouts from StockAnalysis."""
    slug = _SA_EXCHANGE_SLUG.get(str(exchange or "").upper())
    if not slug or not symbol:
        return None
    url = f"https://stockanalysis.com/quote/{slug}/{symbol.upper()}/dividend/"
    req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    matches = _SA_HIST_OBJ_RE.findall(html)
    if not matches:
        return None

    history: List[Dict[str, Any]] = []
    for dt_str, amt_str, _dec, rec_str, pay_str in matches[:8]:
        ex_iso = dt_str if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dt_str) else None
        rec_iso = rec_str if re.fullmatch(r"\d{4}-\d{2}-\d{2}", rec_str) else None
        pay_iso = pay_str if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pay_str) else None
        amt_m = re.match(r"([0-9.]+)\s*([A-Z]{3})?", amt_str.strip())
        amt_val = _safe_float(amt_m.group(1), 4) if amt_m else None
        amt_curr = amt_m.group(2) if (amt_m and amt_m.group(2)) else None
        if ex_iso and amt_val and amt_val > 0:
            history.append({
                "ex_date": ex_iso,
                "amount": amt_val,
                "currency": amt_curr,
                "record_date": rec_iso,
                "pay_date": pay_iso,
            })

    if not history:
        return None
    return {"latest": history[0], "history": history}


def _enrich_arabic_names(items: List[Dict[str, Any]], market_key: str) -> None:
    """Attach canonical Arabic stock names without extra DB queries when possible."""
    ar_map: Dict[str, str] = {}
    try:
        from api.stock_aliases import ARABIC_STOCK_MAPPINGS
        if market_key == "egx":
            for ar_name, sym in ARABIC_STOCK_MAPPINGS.items():
                u = str(sym).upper()
                if u not in ar_map or len(ar_name) > len(ar_map[u]):
                    ar_map[u] = ar_name
    except Exception:
        pass
    try:
        from api.routers.offload_public import CANONICAL_EGX_STOCK_NAMES, SAUDI_STOCK_NAMES_AR
        if market_key == "egx":
            for sym, info in CANONICAL_EGX_STOCK_NAMES.items():
                if info.get("name_ar"):
                    ar_map[sym.upper()] = info["name_ar"]
        elif market_key == "tasi":
            for sym, nm in SAUDI_STOCK_NAMES_AR.items():
                if nm:
                    ar_map[str(sym).upper()] = nm
    except Exception:
        pass

    # Fill remaining Arabic names from DB `stocks` table (1 bounded query per market)
    missing = [x["symbol"] for x in items if x["symbol"] not in ar_map]
    if missing:
        sb = _get_primary_sb() if market_key == "egx" else _get_gcc_sb()
        if sb is not None:
            try:
                exchs = ["EGX"] if market_key == "egx" else (
                    ["TADAWUL", "TASI"] if market_key == "tasi" else (
                        ["QSE"] if market_key == "qatar" else ["DFM", "ADX"]
                    )
                )
                rows = (
                    sb.table("stocks")
                    .select("symbol,name_ar,name")
                    .in_("exchange", exchs)
                    .in_("symbol", missing[:200])
                    .limit(250)
                    .execute()
                    .data
                    or []
                )
                for r in rows:
                    s = str(r.get("symbol") or "").upper()
                    if s and r.get("name_ar"):
                        ar_map[s] = str(r["name_ar"]).split(",")[0].strip()
            except Exception:
                pass

    for item in items:
        sym = item["symbol"]
        item["name_ar"] = ar_map.get(sym) or item.get("name_en") or sym


def _estimate_record_and_pay_dates(item: Dict[str, Any]) -> None:
    """Ensure clean status + fallback record_date/pay_date flags when exact dates are missing."""
    today = _today_cairo()
    ex_d = _parse_iso_date(item.get("ex_date"))
    rec_d = _parse_iso_date(item.get("record_date"))
    pay_d = _parse_iso_date(item.get("pay_date"))

    if ex_d:
        item["days_until_ex"] = (ex_d - today).days
    else:
        item["days_until_ex"] = None

    if pay_d:
        item["days_until_pay"] = (pay_d - today).days
    else:
        item["days_until_pay"] = None

    if ex_d and ex_d >= today:
        item["status"] = "upcoming"
    elif pay_d and pay_d >= today:
        item["status"] = "pending_pay"
    elif ex_d and (today - ex_d).days <= 5 and not pay_d:
        item["status"] = "pending_pay"
    else:
        item["status"] = "paid"

    item["dates_estimated"] = False
    if ex_d and not rec_d:
        # Standard T+1 / next business day record date hint (clearly flagged as estimated if needed)
        item["record_date"] = (ex_d + dt.timedelta(days=1)).isoformat()
        item["dates_estimated"] = True


def sync_market_dividends(
    market_key: str,
    enrich_limit: int = 35,
    save_to_db: bool = True,
) -> Dict[str, Any]:
    """Sync upcoming + recent dividends for one market and persist to market_cache & stock_dividends."""
    norm = market_key.strip().lower()
    if norm not in _TV_ENDPOINTS:
        raise ValueError(f"Unsupported market: {market_key}")

    items = fetch_tv_market_dividends(norm)
    if not items:
        return {"market": norm, "total": 0, "upcoming": 0, "items": []}

    _enrich_arabic_names(items, norm)

    # Prioritize ALL upcoming items + top recent items for StockAnalysis exact pay_date/record_date enrichment
    upcoming_items = [x for x in items if x.get("is_upcoming")]
    recent_items = sorted(
        [x for x in items if not x.get("is_upcoming")],
        key=lambda x: x.get("ex_date") or "",
        reverse=True,
    )
    to_enrich = upcoming_items + recent_items[: max(0, enrich_limit - len(upcoming_items))]

    def _enrich_one(item: Dict[str, Any]) -> None:
        sa = fetch_stockanalysis_dividend_details(item["exchange"], item["symbol"])
        if not sa:
            return
        hist = sa.get("history") or []
        item["history"] = hist[:6]
        # Match by closest ex_date within +/- 10 days or take latest if matching upcoming
        ex_d = _parse_iso_date(item.get("ex_date"))
        matched = None
        for h in hist:
            hd = _parse_iso_date(h.get("ex_date"))
            if ex_d and hd and abs((hd - ex_d).days) <= 10:
                matched = h
                break
        if matched is None and hist:
            matched = hist[0]
        if matched:
            if matched.get("record_date"):
                item["record_date"] = matched["record_date"]
            if matched.get("pay_date"):
                item["pay_date"] = matched["pay_date"]
            if matched.get("amount") and abs(matched["amount"] - item["amount"]) / max(item["amount"], 1e-6) < 0.25:
                item["amount"] = round(matched["amount"], 4)
            item["source"] = "tradingview+stockanalysis"

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(_enrich_one, it) for it in to_enrich]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception:
                pass

    for it in items:
        _estimate_record_and_pay_dates(it)

    # Sort: upcoming soonest first, then pending_pay, then paid newest first
    def _sort_key(x: Dict[str, Any]):
        st = x.get("status")
        ex = x.get("ex_date") or "1970-01-01"
        if st == "upcoming":
            return (0, ex)
        if st == "pending_pay":
            return (1, ex)
        # Paid: reverse chronological
        rev = "".join(chr(ord("9") - ord(c) + ord("0")) if c.isdigit() else c for c in ex)
        return (2, rev)

    items.sort(key=_sort_key)

    upcoming_cnt = sum(1 for x in items if x["status"] == "upcoming")
    pending_cnt = sum(1 for x in items if x["status"] == "pending_pay")
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    payload = {
        "market": norm,
        "updatedAt": now_iso,
        "summary": {
            "total": len(items),
            "upcomingCount": upcoming_cnt,
            "pendingPayCount": pending_cnt,
            "paidRecentCount": len(items) - upcoming_cnt - pending_cnt,
        },
        "dividends": items,
    }

    if save_to_db:
        sb = _get_primary_sb()
        if sb is not None:
            # 1. Always persist to market_cache (instant zero-DDL availability)
            try:
                sb.table("market_cache").upsert({
                    "cache_key": f"dividends_calendar_{norm}",
                    "country": _COUNTRY_MAP.get(norm, "Egypt"),
                    "payload": payload,
                    "computed_at": now_iso,
                }, on_conflict="cache_key,country").execute()
            except Exception as exc:
                logger.warning(f"[dividends_engine] market_cache upsert failed ({norm}): {exc}")

            # 2. Upsert into normalized stock_dividends table if migration has been applied
            try:
                db_rows = [
                    {
                        "exchange": x["exchange"],
                        "symbol": x["symbol"],
                        "name_ar": x.get("name_ar"),
                        "name_en": x.get("name_en"),
                        "amount": x["amount"],
                        "currency": x["currency"],
                        "ex_date": x["ex_date"],
                        "record_date": x.get("record_date"),
                        "pay_date": x.get("pay_date"),
                        "close_price": x.get("close_price"),
                        "yield_pct": x.get("yield_pct"),
                        "status": x["status"],
                        "source": x.get("source", "tradingview"),
                        "metadata": {
                            "annual_yield_pct": x.get("annual_yield_pct"),
                            "fy_dps": x.get("fy_dps"),
                            "dates_estimated": x.get("dates_estimated", False),
                            "history": x.get("history") or [],
                        },
                        "updated_at": now_iso,
                    }
                    for x in items
                ]
                for i in range(0, len(db_rows), 100):
                    sb.table("stock_dividends").upsert(
                        db_rows[i : i + 100],
                        on_conflict="exchange,symbol,ex_date",
                    ).execute()
            except Exception as exc:
                # Graceful when stock_dividends table is not migrated yet
                logger.info(f"[dividends_engine] stock_dividends table upsert skipped ({norm}): {str(exc)[:120]}")

    return payload


def sync_all_markets_dividends(save_to_db: bool = True) -> Dict[str, Any]:
    """Sync upcoming & recent dividends across EGX, TADAWUL, QSE, and UAE."""
    results: Dict[str, Any] = {}
    for mkt in ("egx", "tasi", "qatar", "uae"):
        try:
            res = sync_market_dividends(mkt, save_to_db=save_to_db)
            results[mkt] = res.get("summary", {})
        except Exception as exc:
            logger.error(f"[dividends_engine] sync failed for {mkt}: {exc}")
            results[mkt] = {"error": str(exc)}
    return results


# ---------------------------------------------------------------------------
# Portfolio Auto-Credit & Notifications (In-App + Telegram)
# ---------------------------------------------------------------------------
def _send_telegram_dm(chat_id: str, text: str) -> bool:
    token = (
        os.getenv("ARTORO_AI_BOT")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("SUPPORT_BOT_TOKEN")
        or ""
    ).strip()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def process_portfolio_dividends(dry_run: bool = False) -> Dict[str, Any]:
    """
    Match open user holdings (`positions`) against `stock_dividends`:
      1. Notify holders ahead of `ex_date` (1..14 days before) via `user_notifications` + Telegram.
      2. Credit `profiles.cash_balance` on/after `pay_date` (strictly idempotent via `user_dividend_events`).
    """
    sb = _get_primary_sb()
    if sb is None:
        return {"ok": False, "error": "supabase_unconfigured"}

    today = _today_cairo()
    window_start = (today - dt.timedelta(days=14)).isoformat()
    window_end = (today + dt.timedelta(days=21)).isoformat()

    try:
        divs = (
            sb.table("stock_dividends")
            .select("id,exchange,symbol,name_ar,amount,currency,ex_date,record_date,pay_date,status")
            .gte("ex_date", window_start)
            .lte("ex_date", window_end)
            .limit(200)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        return {
            "ok": False,
            "skipped": True,
            "reason": "stock_dividends_table_not_migrated",
            "detail": str(exc)[:160],
        }

    if not divs:
        return {"ok": True, "matched": 0, "notified_upcoming": 0, "credited": 0}

    div_by_sym: Dict[str, List[Dict[str, Any]]] = {}
    for d in divs:
        s = str(d.get("symbol") or "").upper()
        if s:
            div_by_sym.setdefault(s, []).append(d)

    held_syms = list(div_by_sym.keys())
    positions = (
        sb.table("positions")
        .select("id,user_id,symbol,quantity,entry_at,created_at,status")
        .eq("status", "open")
        .in_("symbol", held_syms)
        .limit(1000)
        .execute()
        .data
        or []
    )
    if not positions:
        return {"ok": True, "matched": 0, "notified_upcoming": 0, "credited": 0}

    # Aggregate shares per (user_id, symbol) where position was opened before ex_date
    user_ids = list({p["user_id"] for p in positions if p.get("user_id")})
    prof_map: Dict[str, Dict[str, Any]] = {}
    if user_ids:
        for p in (
            sb.table("profiles")
            .select("id,cash_balance,telegram_chat_id")
            .in_("id", user_ids[:500])
            .limit(500)
            .execute()
            .data
            or []
        ):
            prof_map[p["id"]] = p

    existing_events: Dict[Tuple[str, str], Dict[str, Any]] = {}
    try:
        ev_rows = (
            sb.table("user_dividend_events")
            .select("id,user_id,dividend_id,credited_to_cash,notified_upcoming_at,notified_paid_at,status")
            .in_("user_id", user_ids[:500])
            .limit(1000)
            .execute()
            .data
            or []
        )
        for ev in ev_rows:
            existing_events[(ev["user_id"], ev["dividend_id"])] = ev
    except Exception:
        pass

    matched = 0
    notified_upcoming = 0
    credited = 0
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    # Group positions by (user_id, symbol)
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for pos in positions:
        qty = _safe_float(pos.get("quantity"), 4) or 0.0
        if qty <= 0 or not pos.get("user_id") or not pos.get("symbol"):
            continue
        grouped.setdefault((pos["user_id"], str(pos["symbol"]).upper()), []).append(pos)

    for (uid, sym), pos_list in grouped.items():
        for div in div_by_sym.get(sym, []):
            ex_d = _parse_iso_date(div.get("ex_date"))
            pay_d = _parse_iso_date(div.get("pay_date"))
            if not ex_d:
                continue

            # Eligible shares = positions entered strictly before ex_date (holding through record date)
            eligible_shares = 0.0
            for pos in pos_list:
                raw_dt = pos.get("entry_at") or pos.get("created_at")
                pos_d = _parse_iso_date(raw_dt)
                if pos_d is None or pos_d < ex_d:
                    eligible_shares += float(pos.get("quantity") or 0.0)
            if eligible_shares <= 0:
                continue

            matched += 1
            amt = float(div["amount"])
            gross = round(eligible_shares * amt, 2)
            tax_pct = 5.0 if str(div.get("exchange")).upper() == "EGX" else 0.0
            net = round(gross * (1.0 - tax_pct / 100.0), 2)
            curr = str(div.get("currency") or "EGP").upper()
            curr_ar = _currency_ar(curr)
            name_ar = div.get("name_ar") or sym

            ev = existing_events.get((uid, div["id"]))
            prof = prof_map.get(uid) or {}
            tg_chat = prof.get("telegram_chat_id")

            # A) Upcoming notification (ex_date in 0..14 days, or pending pay before payout)
            days_to_ex = (ex_d - today).days
            is_payable_now = bool(pay_d and pay_d <= today)

            if not dry_run and (ev is None or not ev.get("notified_upcoming_at")) and not is_payable_now and -5 <= days_to_ex <= 14:
                title = f"💰 كوبون قادم في محفظتك: {name_ar} ({sym})"
                pay_txt = f" | الصرف: {div.get('pay_date')}" if div.get("pay_date") else ""
                tax_note = f" (صافي بعد 5% ضريبة ≈ {net:,.2f} {curr_ar})" if tax_pct > 0 else ""
                body = (
                    f"تمتلك {eligible_shares:,.0f} سهم في {name_ar} ({sym}). "
                    f"الكوبون: {amt:g} {curr_ar}/سهم = إجمالي {gross:,.2f} {curr_ar}{tax_note}. "
                    f"تاريخ التداول بدون كوبون: {div['ex_date']}{pay_txt}."
                )
                sb.table("user_dividend_events").upsert({
                    "user_id": uid,
                    "dividend_id": div["id"],
                    "exchange": div["exchange"],
                    "symbol": sym,
                    "shares_held": eligible_shares,
                    "coupon_per_share": amt,
                    "gross_amount": gross,
                    "net_amount": net,
                    "tax_rate_pct": tax_pct,
                    "currency": curr,
                    "ex_date": div["ex_date"],
                    "record_date": div.get("record_date"),
                    "pay_date": div.get("pay_date"),
                    "status": "upcoming" if days_to_ex >= 0 else "pending_pay",
                    "notified_upcoming_at": now_iso,
                    "updated_at": now_iso,
                }, on_conflict="user_id,dividend_id").execute()

                sb.table("user_notifications").upsert({
                    "user_id": uid,
                    "type": "dividend_upcoming",
                    "title": title,
                    "body": body,
                    "href": f"/stocks/{sym}",
                    "metadata": {
                        "symbol": sym,
                        "exchange": div["exchange"],
                        "amount": amt,
                        "gross_amount": gross,
                        "net_amount": net,
                        "currency": curr,
                        "ex_date": div["ex_date"],
                        "pay_date": div.get("pay_date"),
                    },
                    "dedupe_key": f"div_upcoming:{div['id']}",
                }, on_conflict="user_id,dedupe_key").execute()

                if tg_chat:
                    _send_telegram_dm(tg_chat, f"🎁 *{title}*\n\n{body}\n\n🔗 egxbots.com/portfolio")
                notified_upcoming += 1

            # B) Pay-date Auto-Credit to Portfolio Cash Balance (strictly idempotent!)
            if not dry_run and is_payable_now and (ev is None or not ev.get("credited_to_cash")):
                should_credit_cash = curr == "EGP"  # profiles.cash_balance is denominated in EGP
                if should_credit_cash:
                    cur_cash = float(prof.get("cash_balance") or 0.0)
                    new_cash = round(cur_cash + gross, 2)
                    sb.table("profiles").update({"cash_balance": new_cash}).eq("id", uid).execute()
                    prof["cash_balance"] = new_cash

                sb.table("user_dividend_events").upsert({
                    "user_id": uid,
                    "dividend_id": div["id"],
                    "exchange": div["exchange"],
                    "symbol": sym,
                    "shares_held": eligible_shares,
                    "coupon_per_share": amt,
                    "gross_amount": gross,
                    "net_amount": net,
                    "tax_rate_pct": tax_pct,
                    "currency": curr,
                    "ex_date": div["ex_date"],
                    "record_date": div.get("record_date"),
                    "pay_date": div.get("pay_date"),
                    "status": "credited",
                    "credited_to_cash": should_credit_cash,
                    "credited_at": now_iso,
                    "notified_paid_at": now_iso,
                    "updated_at": now_iso,
                }, on_conflict="user_id,dividend_id").execute()

                title = f"✅ تم صرف كوبون {name_ar} ({sym})!"
                cash_txt = (
                    f"وتم إضافة {gross:,.2f} {curr_ar} تلقائياً إلى رصيد الكاش في محفظتك"
                    if should_credit_cash
                    else f"بقيمة إجمالية {gross:,.2f} {curr_ar}"
                )
                body = (
                    f"تم صرف كوبون سهم {name_ar} ({sym}) عن {eligible_shares:,.0f} سهم "
                    f"({amt:g} {curr_ar}/سهم) {cash_txt}."
                )
                sb.table("user_notifications").upsert({
                    "user_id": uid,
                    "type": "dividend_credited",
                    "title": title,
                    "body": body,
                    "href": "/portfolio",
                    "metadata": {
                        "symbol": sym,
                        "exchange": div["exchange"],
                        "amount": amt,
                        "gross_amount": gross,
                        "net_amount": net,
                        "currency": curr,
                        "pay_date": div.get("pay_date"),
                        "credited_to_cash": should_credit_cash,
                    },
                    "dedupe_key": f"div_paid:{div['id']}",
                }, on_conflict="user_id,dedupe_key").execute()

                if tg_chat:
                    _send_telegram_dm(tg_chat, f"💸 *{title}*\n\n{body}\n\n🔗 egxbots.com/portfolio")
                credited += 1

    return {
        "ok": True,
        "matched": matched,
        "notified_upcoming": notified_upcoming,
        "credited": credited,
    }


def get_cached_market_dividends(market_key: str, symbol: Optional[str] = None) -> Dict[str, Any]:
    """Read cached 4-market dividends calendar from Supabase (`stock_dividends` -> `market_cache` fallback)."""
    norm = (market_key or "egx").strip().lower()
    if norm in ("tadawul", "sa", "saudi"):
        norm = "tasi"
    elif norm in ("qse", "qe"):
        norm = "qatar"
    elif norm in ("dfm", "adx"):
        norm = "uae"
    if norm not in _TV_ENDPOINTS:
        norm = "egx"

    sb = _get_primary_sb()
    payload: Optional[Dict[str, Any]] = None
    if sb is not None:
        try:
            res = (
                sb.table("market_cache")
                .select("payload,computed_at")
                .eq("cache_key", f"dividends_calendar_{norm}")
                .limit(1)
                .execute()
                .data
                or []
            )
            if res and isinstance(res[0].get("payload"), dict):
                payload = dict(res[0]["payload"])
        except Exception as exc:
            logger.warning(f"[dividends_engine] cache read failed ({norm}): {exc}")

    if not payload or not payload.get("dividends"):
        # Cold-start live sync once
        payload = sync_market_dividends(norm, enrich_limit=25, save_to_db=True)

    if symbol:
        sym_u = str(symbol).strip().upper().split(".")[0]
        all_items = payload.get("dividends") or []
        matched = [x for x in all_items if str(x.get("symbol") or "").upper() == sym_u]
        return {
            "market": norm,
            "symbol": sym_u,
            "updatedAt": payload.get("updatedAt"),
            "dividends": matched,
        }

    return payload


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(".env")
    load_dotenv("web/.env.local", override=False)
    print("Syncing all 4 markets dividends...")
    summary = sync_all_markets_dividends(save_to_db=True)
    print("SYNC SUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2))
    print("Running portfolio dividend check...")
    port_res = process_portfolio_dividends(dry_run=False)
    print("PORTFOLIO RESULT:", json.dumps(port_res, ensure_ascii=False, indent=2))
