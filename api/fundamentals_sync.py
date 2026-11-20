"""
api/fundamentals_sync.py
Unified 3-Tier Institutional Financial & Fundamental Data Engine for ALL 4 Markets:
  - EGX (Egypt — Primary Supabase)
  - TADAWUL / TASI (Saudi Arabia — GCC Supabase)
  - QSE (Qatar — GCC Supabase)
  - DFM & ADX (UAE — GCC Supabase)

Tier 1: TradingView Screener Bulk API (fast single-call sweep per market with TTM/FY/FQ fallback)
Tier 2: StockAnalysis.com institutional /statistics/ HTML parser (45+ ratios, statements, dividends, Z/F-scores)
Tier 3: Yahoo Finance (yfinance) statement gap-filler for any ticker still missing core metrics

Merges strictly non-null metrics into existing `stock_fundamentals.data` without erasing metadata
(`isin`, `name_ar`, `listingStatus`, `logoUrl`), computes derived ratios + `fund_score` (0-100),
and upserts in bounded batches.
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

logger = logging.getLogger("fundamentals_sync")

MARKET_SPECS: Dict[str, Dict[str, Any]] = {
    "EGX": {
        "exchange": "EGX",
        "country": "Egypt",
        "currency": "EGP",
        "tv_market": "egypt",
        "tv_exchange": "EGX",
        "sa_exchange": "egx",
        "yf_suffix": ".CA",
        "supabase_target": "primary",
    },
    "TADAWUL": {
        "exchange": "TADAWUL",
        "country": "Saudi Arabia",
        "currency": "SAR",
        "tv_market": "ksa",
        "tv_exchange": "TADAWUL",
        "sa_exchange": "tadawul",
        "yf_suffix": ".SR",
        "supabase_target": "gcc",
    },
    "QSE": {
        "exchange": "QSE",
        "country": "Qatar",
        "currency": "QAR",
        "tv_market": "qatar",
        "tv_exchange": "QSE",
        "sa_exchange": "qse",
        "yf_suffix": ".QA",
        "supabase_target": "gcc",
    },
    "DFM": {
        "exchange": "DFM",
        "country": "UAE",
        "currency": "AED",
        "tv_market": "uae",
        "tv_exchange": "DFM",
        "sa_exchange": "dfm",
        "yf_suffix": ".AE",
        "supabase_target": "gcc",
    },
    "ADX": {
        "exchange": "ADX",
        "country": "UAE",
        "currency": "AED",
        "tv_market": "uae",
        "tv_exchange": "ADX",
        "sa_exchange": "adx",
        "yf_suffix": ".AE",
        "supabase_target": "gcc",
    },
}

MARKET_GROUP_ALIASES: Dict[str, List[str]] = {
    "egx": ["EGX"],
    "egypt": ["EGX"],
    "tasi": ["TADAWUL"],
    "tadawul": ["TADAWUL"],
    "saudi": ["TADAWUL"],
    "ksa": ["TADAWUL"],
    "qse": ["QSE"],
    "qatar": ["QSE"],
    "uae": ["DFM", "ADX"],
    "dfm": ["DFM"],
    "adx": ["ADX"],
    "all": ["EGX", "TADAWUL", "QSE", "DFM", "ADX"],
}

# TradingView columns (rich TTM + FY + FQ fallbacks)
TV_FUNDAMENTAL_COLUMNS: List[str] = [
    "name",
    "description",
    "exchange",
    "sector",
    "industry",
    "logoid",
    "close",
    "market_cap_basic",
    "enterprise_value_current",
    "total_shares_outstanding_fundamental",
    "price_earnings_ttm",
    "earnings_per_share_basic_ttm",
    "earnings_per_share_diluted_ttm",
    "earnings_per_share_diluted_fy",
    "basic_eps_net_income",
    "book_value_per_share_fq",
    "book_value_per_share_fy",
    "price_book_fq",
    "price_book_ratio",
    "price_sales_current",
    "price_sales_ratio",
    "enterprise_value_ebitda_ttm",
    "return_on_equity",
    "return_on_equity_fy",
    "return_on_assets",
    "return_on_assets_fy",
    "return_on_invested_capital",
    "dividends_yield_current",
    "dividends_yield",
    "dps_common_stock_prim_issue_fy",
    "total_revenue",
    "total_revenue_fy",
    "total_revenue_fq",
    "total_revenue_yoy_growth_ttm",
    "total_revenue_yoy_growth_fy",
    "net_income",
    "net_income_fy",
    "net_income_fq",
    "net_income_yoy_growth_ttm",
    "net_income_yoy_growth_fy",
    "gross_margin",
    "gross_margin_fy",
    "operating_margin",
    "operating_margin_fy",
    "net_margin",
    "net_margin_fy",
    "ebitda",
    "ebitda_fy",
    "free_cash_flow",
    "free_cash_flow_fy",
    "total_assets",
    "total_assets_fy",
    "total_debt",
    "total_debt_fy",
    "total_equity_fq",
    "total_equity_fy",
    "debt_to_equity",
    "debt_to_equity_fy",
    "current_ratio",
    "current_ratio_fy",
    "price_52_week_high",
    "price_52_week_low",
    "beta_1_year",
]

# StockAnalysis.com /statistics/ table label -> canonical camelCase schema key
STOCKANALYSIS_NUMERIC_MAP: Dict[str, str] = {
    "Market Cap": "marketCap",
    "Enterprise Value": "enterpriseValue",
    "Shares Outstanding": "sharesOutstanding",
    "Float": "floatShares",
    "Owned by Insiders (%)": "insidersOwnershipPct",
    "Owned by Institutions (%)": "institutionsOwnershipPct",
    "PE Ratio": "peRatio",
    "Forward PE": "forwardPe",
    "PS Ratio": "priceToSales",
    "PB Ratio": "pbRatio",
    "P/FCF Ratio": "priceToFcf",
    "PEG Ratio": "pegRatio",
    "EV / EBITDA": "evToEbitda",
    "EV / Sales": "evToSales",
    "Current Ratio": "currentRatio",
    "Quick Ratio": "quickRatio",
    "Debt / Equity": "debtToEquity",
    "Interest Coverage": "interestCoverage",
    "Return on Equity (ROE)": "roe",
    "Return on Assets (ROA)": "roa",
    "Return on Invested Capital (ROIC)": "roic",
    "Return on Capital Employed (ROCE)": "roce",
    "Beta (5Y)": "beta",
    "Revenue": "revenue",
    "Gross Profit": "grossProfit",
    "Operating Income": "operatingIncome",
    "Net Income": "netIncome",
    "EBITDA": "ebitda",
    "Earnings Per Share (EPS)": "eps",
    "Cash & Cash Equivalents": "totalCash",
    "Total Debt": "totalDebt",
    "Net Cash": "netCash",
    "Equity (Book Value)": "totalEquity",
    "Book Value Per Share": "bookValuePerShare",
    "Working Capital": "workingCapital",
    "Operating Cash Flow": "operatingCashFlow",
    "Capital Expenditures": "capitalExpenditures",
    "Free Cash Flow": "freeCashFlow",
    "FCF Per Share": "fcfPerShare",
    "Gross Margin": "grossMargin",
    "Operating Margin": "operatingMargin",
    "Profit Margin": "netMargin",
    "EBITDA Margin": "ebitdaMargin",
    "FCF Margin": "fcfMargin",
    "Dividend Per Share": "dividendPerShare",
    "Dividend Yield": "dividendYield",
    "Dividend Growth (YoY)": "dividendGrowthYoY",
    "Payout Ratio": "payoutRatio",
    "Earnings Yield": "earningsYield",
    "FCF Yield": "fcfYield",
    "Altman Z-Score": "altmanZScore",
    "Piotroski F-Score": "piotroskiFScore",
    "52-Week Price Change": "priceChange52W",
}

STOCKANALYSIS_STRING_MAP: Dict[str, str] = {
    "Earnings Date": "earningsDate",
    "Ex-Dividend Date": "exDividendDate",
    "Analyst Consensus": "analystConsensus",
}

# Known local DB symbol -> TradingView / StockAnalysis ticker aliases across all 4 markets
TV_SYMBOL_ALIASES: Dict[str, str] = {
    "EKHOA": "EKHO",
    "ODHN": "ODIN",
    "EAND": "ETISALAT",
    "FERTIGLBE": "FERTIGLB",
    "PHOENIX": "PHX",
    "RAKCER": "RAKCEC",
    "YAHSAT": "SPACE42",
    "BEEMA": "BEMA",
}


def _clean_float(val: Any, *, digits: int = 4) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, digits)


def parse_human_number(raw: Any) -> Optional[float]:
    """Parse StockAnalysis / financial table numbers such as '434.16B', '39.41%', '-113.05B', 'n/a', 'Upgrade'."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return _clean_float(raw)
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    if low in {"n/a", "na", "-", "--", "—", "none", "null", "upgrade", "n.a."}:
        return None
    if "upgrade" in low:
        return None
    # Strip currency prefixes / whitespace / commas / percent sign
    s = re.sub(r"^(?:EGP|SAR|QAR|AED|USD|\$|£|€)\s*", "", s, flags=re.IGNORECASE)
    s = s.replace(",", "").replace(" ", "").replace("+", "")
    if s.endswith("%"):
        s = s[:-1]
    mult = 1.0
    if s and s[-1] in ("K", "k", "M", "m", "B", "b", "T", "t"):
        suffix = s[-1].upper()
        s = s[:-1]
        mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
    try:
        val = float(s) * mult
    except ValueError:
        return None
    if not math.isfinite(val):
        return None
    return round(val, 4) if abs(val) < 1e6 else round(val, 2)


def _first_finite(*vals: Any, digits: int = 4) -> Optional[float]:
    for v in vals:
        c = _clean_float(v, digits=digits)
        if c is not None:
            return c
    return None


def _build_http_session(pool_size: int = 16) -> requests.Session:
    sess = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=0)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    sess.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return sess


# ---------------------------------------------------------------------------
# Tier 1: TradingView Screener Bulk Fetch
# ---------------------------------------------------------------------------
def fetch_tradingview_market_fundamentals(exchanges: List[str]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Bulk-fetch fundamental metrics from TradingView Screener for one or more exchanges.
    Returns dict keyed by (EXCHANGE, SYMBOL) -> canonical camelCase metrics dict.
    """
    try:
        from tradingview_screener import Query
    except ImportError:
        logger.warning("[fundamentals_sync] tradingview_screener not installed; skipping Tier 1.")
        return {}

    tv_markets_needed: Dict[str, List[str]] = {}
    for ex in exchanges:
        spec = MARKET_SPECS.get(ex)
        if not spec:
            continue
        tv_markets_needed.setdefault(spec["tv_market"], []).append(ex)

    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for tv_mkt, ex_list in tv_markets_needed.items():
        try:
            _, df = (
                Query()
                .set_markets(tv_mkt)
                .select(*TV_FUNDAMENTAL_COLUMNS)
                .limit(600)
                .get_scanner_data()
            )
            if df is None or df.empty:
                continue
        except Exception as exc:
            logger.warning(f"[fundamentals_sync] Tier 1 TradingView failed for {tv_mkt}: {exc}")
            continue

        allowed_ex = set(ex_list)
        for _, row in df.iterrows():
            sym = str(row.get("name") or "").strip().upper()
            row_ex = str(row.get("exchange") or "").strip().upper()
            if not sym:
                continue
            if row_ex not in allowed_ex:
                # Single-exchange TV market fallback
                if len(ex_list) == 1:
                    row_ex = ex_list[0]
                else:
                    continue

            close_val = _clean_float(row.get("close"))
            shares = _clean_float(row.get("total_shares_outstanding_fundamental"), digits=2)
            mcap = _clean_float(row.get("market_cap_basic"), digits=2)
            revenue = _first_finite(row.get("total_revenue"), row.get("total_revenue_fy"), digits=2)
            net_inc = _first_finite(row.get("net_income"), row.get("net_income_fy"), digits=2)
            total_eq = _first_finite(row.get("total_equity_fq"), row.get("total_equity_fy"), digits=2)
            total_assets = _first_finite(row.get("total_assets"), row.get("total_assets_fy"), digits=2)
            total_debt = _first_finite(row.get("total_debt"), row.get("total_debt_fy"), digits=2)
            eps = _first_finite(
                row.get("earnings_per_share_basic_ttm"),
                row.get("earnings_per_share_diluted_ttm"),
                row.get("basic_eps_net_income"),
                row.get("earnings_per_share_diluted_fy"),
            )
            if eps is None and net_inc is not None and shares and shares > 0:
                eps = _clean_float(net_inc / shares)

            bvps = _first_finite(row.get("book_value_per_share_fq"), row.get("book_value_per_share_fy"))
            if bvps is None and total_eq is not None and shares and shares > 0:
                bvps = _clean_float(total_eq / shares)

            pe = _clean_float(row.get("price_earnings_ttm"), digits=2)
            if pe is None and close_val and close_val > 0 and eps and eps > 0:
                cand_pe = close_val / eps
                if 0.5 <= cand_pe <= 500:
                    pe = round(cand_pe, 2)

            pb = _first_finite(row.get("price_book_fq"), row.get("price_book_ratio"), digits=2)
            if pb is None and close_val and close_val > 0 and bvps and bvps > 0:
                cand_pb = close_val / bvps
                if 0.05 <= cand_pb <= 100:
                    pb = round(cand_pb, 2)

            roe = _first_finite(row.get("return_on_equity"), row.get("return_on_equity_fy"), digits=2)
            if roe is None and net_inc is not None and total_eq and total_eq > 0:
                cand_roe = (net_inc / total_eq) * 100.0
                if -200 <= cand_roe <= 300:
                    roe = round(cand_roe, 2)

            roa = _first_finite(row.get("return_on_assets"), row.get("return_on_assets_fy"), digits=2)
            if roa is None and net_inc is not None and total_assets and total_assets > 0:
                cand_roa = (net_inc / total_assets) * 100.0
                if -150 <= cand_roa <= 150:
                    roa = round(cand_roa, 2)

            div_yield = _first_finite(row.get("dividends_yield_current"), row.get("dividends_yield"), digits=2)
            if div_yield is not None and div_yield == 0.0:
                # TradingView uses 0.0 for non-dividend payers; preserve 0 only if explicitly confirmed or omit if dps is also 0
                pass

            metrics: Dict[str, Any] = {
                "name": str(row.get("description") or "").strip() or None,
                "sector": str(row.get("sector") or "").strip() or None,
                "industry": str(row.get("industry") or "").strip() or None,
                "logoUrl": (
                    f"https://s3-symbol-logo.tradingview.com/{row.get('logoid')}.svg"
                    if row.get("logoid")
                    else None
                ),
                "marketCap": mcap,
                "enterpriseValue": _clean_float(row.get("enterprise_value_current"), digits=2),
                "sharesOutstanding": shares,
                "peRatio": pe,
                "eps": eps,
                "bookValuePerShare": bvps,
                "pbRatio": pb,
                "priceToSales": _first_finite(row.get("price_sales_current"), row.get("price_sales_ratio"), digits=2),
                "evToEbitda": _clean_float(row.get("enterprise_value_ebitda_ttm"), digits=2),
                "roe": roe,
                "roa": roa,
                "roic": _clean_float(row.get("return_on_invested_capital"), digits=2),
                "dividendYield": div_yield if (div_yield is not None and div_yield > 0) else None,
                "dividendPerShare": _clean_float(row.get("dps_common_stock_prim_issue_fy"), digits=4),
                "revenue": revenue,
                "revenueGrowthYoY": _first_finite(
                    row.get("total_revenue_yoy_growth_ttm"), row.get("total_revenue_yoy_growth_fy"), digits=2
                ),
                "netIncome": net_inc,
                "netIncomeGrowthYoY": _first_finite(
                    row.get("net_income_yoy_growth_ttm"), row.get("net_income_yoy_growth_fy"), digits=2
                ),
                "grossMargin": _first_finite(row.get("gross_margin"), row.get("gross_margin_fy"), digits=2),
                "operatingMargin": _first_finite(row.get("operating_margin"), row.get("operating_margin_fy"), digits=2),
                "netMargin": _first_finite(row.get("net_margin"), row.get("net_margin_fy"), digits=2),
                "ebitda": _first_finite(row.get("ebitda"), row.get("ebitda_fy"), digits=2),
                "freeCashFlow": _first_finite(row.get("free_cash_flow"), row.get("free_cash_flow_fy"), digits=2),
                "totalAssets": total_assets,
                "totalDebt": total_debt,
                "totalEquity": total_eq,
                "debtToEquity": _first_finite(row.get("debt_to_equity"), row.get("debt_to_equity_fy"), digits=2),
                "currentRatio": _first_finite(row.get("current_ratio"), row.get("current_ratio_fy"), digits=2),
                "high52": _clean_float(row.get("price_52_week_high"), digits=4),
                "low52": _clean_float(row.get("price_52_week_low"), digits=4),
                "beta": _clean_float(row.get("beta_1_year"), digits=3),
                "_lastClose": close_val,
            }
            clean_metrics = {k: v for k, v in metrics.items() if v is not None}
            out[(row_ex, sym)] = clean_metrics

            # Also expose reverse alias (e.g. EKHO -> EKHOA)
            for local_sym, tv_sym in TV_SYMBOL_ALIASES.items():
                if sym == tv_sym and (row_ex, local_sym) not in out:
                    out[(row_ex, local_sym)] = dict(clean_metrics)

    return out


# ---------------------------------------------------------------------------
# Tier 2: StockAnalysis.com Institutional Statistics Parser
# ---------------------------------------------------------------------------
def parse_stockanalysis_statistics_html(html: str) -> Dict[str, Any]:
    """Parse key-value metric tables from a StockAnalysis /statistics/ HTML page."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    raw_kv: Dict[str, str] = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            k = " ".join(tds[0].get_text(" ", strip=True).split())
            v = " ".join(tds[1].get_text(" ", strip=True).split())
            if k and v and k not in raw_kv:
                raw_kv[k] = v

    parsed: Dict[str, Any] = {}
    for label, target_key in STOCKANALYSIS_NUMERIC_MAP.items():
        if label in raw_kv:
            num = parse_human_number(raw_kv[label])
            if num is not None:
                # Ignore 0.00% dividend yield if DPS is also absent/zero
                if target_key == "dividendYield" and num == 0.0:
                    continue
                parsed[target_key] = num

    for label, target_key in STOCKANALYSIS_STRING_MAP.items():
        if label in raw_kv:
            val = raw_kv[label].strip()
            if val and val.lower() not in {"n/a", "na", "-", "--", "upgrade"}:
                parsed[target_key] = val

    return parsed


def fetch_stockanalysis_one(
    session: requests.Session,
    exchange: str,
    symbol: str,
    timeout: float = 12.0,
) -> Optional[Dict[str, Any]]:
    """Fetch StockAnalysis /statistics/ page for a single (exchange, symbol) with gentle retry."""
    spec = MARKET_SPECS.get(exchange)
    if not spec:
        return None
    sa_ex = spec["sa_exchange"]
    sa_sym = TV_SYMBOL_ALIASES.get(symbol.upper(), symbol.upper())
    url = f"https://stockanalysis.com/quote/{sa_ex}/{sa_sym}/statistics/"

    for attempt in range(2):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 200 and len(r.text) > 10000:
                data = parse_stockanalysis_statistics_html(r.text)
                return data if data else None
            if r.status_code == 404:
                return None
            if r.status_code == 429 and attempt == 0:
                time.sleep(3.5)
                continue
            if r.status_code in (500, 502, 503, 504) and attempt == 0:
                time.sleep(1.5)
                continue
            return None
        except requests.RequestException:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return None
    return None


def fetch_stockanalysis_bulk(
    items: List[Tuple[str, str]],
    max_workers: int = 4,
    pace_delay_sec: float = 0.25,
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Concurrently fetch StockAnalysis institutional statistics with polite pacing to avoid 429 throttling."""
    if not items:
        return {}
    workers = max(1, min(int(max_workers or 4), 5))
    session = _build_http_session(pool_size=workers + 4)
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _paced_fetch(ex: str, sym: str) -> Optional[Dict[str, Any]]:
        if pace_delay_sec > 0:
            time.sleep(pace_delay_sec)
        return fetch_stockanalysis_one(session, ex, sym)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fut_map = {
                pool.submit(_paced_fetch, ex, sym): (ex, sym)
                for ex, sym in items
            }
            for fut in as_completed(fut_map):
                key = fut_map[fut]
                try:
                    data = fut.result()
                    if data:
                        results[key] = data
                except Exception:
                    pass
    finally:
        session.close()
    return results


# ---------------------------------------------------------------------------
# Tier 3: Yahoo Finance Statement Gap-Filler (Only for remaining gaps)
# ---------------------------------------------------------------------------
def fetch_yfinance_one(exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch financial statement & info fallback from yfinance for a single symbol."""
    spec = MARKET_SPECS.get(exchange)
    if not spec:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None

    yf_sym = f"{symbol.upper()}{spec['yf_suffix']}"
    out: Dict[str, Any] = {}
    try:
        tk = yf.Ticker(yf_sym)
        info = tk.info or {}
        if isinstance(info, dict):
            mapping = {
                "marketCap": "marketCap",
                "trailingPE": "peRatio",
                "forwardPE": "forwardPe",
                "priceToBook": "pbRatio",
                "trailingEps": "eps",
                "bookValue": "bookValuePerShare",
                "totalRevenue": "revenue",
                "netIncomeToCommon": "netIncome",
                "ebitda": "ebitda",
                "freeCashflow": "freeCashFlow",
                "operatingCashflow": "operatingCashFlow",
                "totalCash": "totalCash",
                "totalDebt": "totalDebt",
                "currentRatio": "currentRatio",
                "quickRatio": "quickRatio",
                "beta": "beta",
                "fiftyTwoWeekHigh": "high52",
                "fiftyTwoWeekLow": "low52",
                "sharesOutstanding": "sharesOutstanding",
                "sector": "sector",
                "industry": "industry",
            }
            for src_k, dst_k in mapping.items():
                val = info.get(src_k)
                if dst_k in ("sector", "industry"):
                    if isinstance(val, str) and val.strip():
                        out[dst_k] = val.strip()
                else:
                    fv = _clean_float(val, digits=4 if abs(float(val or 0)) < 1e6 else 2) if val is not None else None
                    if fv is not None:
                        out[dst_k] = fv

            # Percentage fields (yfinance stores ratios like 0.25 -> 25.0%)
            for src_k, dst_k in [
                ("returnOnEquity", "roe"),
                ("returnOnAssets", "roa"),
                ("grossMargins", "grossMargin"),
                ("operatingMargins", "operatingMargin"),
                ("profitMargins", "netMargin"),
                ("revenueGrowth", "revenueGrowthYoY"),
                ("earningsGrowth", "netIncomeGrowthYoY"),
                ("dividendYield", "dividendYield"),
                ("payoutRatio", "payoutRatio"),
            ]:
                v = _clean_float(info.get(src_k))
                if v is not None:
                    # Yahoo sometimes returns dividendYield already as % (e.g. 5.2) or decimal (0.052)
                    if dst_k == "dividendYield":
                        pct = round(v * 100.0, 2) if 0 < v < 0.5 else round(v, 2)
                        if 0 < pct <= 60:
                            out[dst_k] = pct
                    else:
                        out[dst_k] = round(v * 100.0, 2) if abs(v) <= 3.0 else round(v, 2)

            de = _clean_float(info.get("debtToEquity"))
            if de is not None:
                # Yahoo returns debtToEquity in % (e.g. 45.2 for 0.452)
                out["debtToEquity"] = round(de / 100.0, 2) if de > 10 else round(de, 2)

        # Pull latest annual income_stmt & balance_sheet if core items still missing
        if out.get("revenue") is None or out.get("netIncome") is None or out.get("eps") is None:
            inc = tk.income_stmt
            if inc is not None and not inc.empty:
                c0 = inc.columns[0]
                for row_lbl, dst_k in [
                    ("Total Revenue", "revenue"),
                    ("Net Income", "netIncome"),
                    ("Gross Profit", "grossProfit"),
                    ("Operating Income", "operatingIncome"),
                    ("EBITDA", "ebitda"),
                    ("Basic EPS", "eps"),
                    ("Diluted EPS", "eps"),
                ]:
                    if dst_k not in out and row_lbl in inc.index:
                        val = _clean_float(inc.loc[row_lbl, c0])
                        if val is not None:
                            out[dst_k] = val

        if out.get("totalEquity") is None or out.get("totalAssets") is None or out.get("totalDebt") is None:
            bal = tk.balance_sheet
            if bal is not None and not bal.empty:
                c0 = bal.columns[0]
                for row_lbl, dst_k in [
                    ("Total Assets", "totalAssets"),
                    ("Total Debt", "totalDebt"),
                    ("Stockholders Equity", "totalEquity"),
                    ("Common Stock Equity", "totalEquity"),
                    ("Ordinary Shares Number", "sharesOutstanding"),
                ]:
                    if dst_k not in out and row_lbl in bal.index:
                        val = _clean_float(bal.loc[row_lbl, c0])
                        if val is not None:
                            out[dst_k] = val
    except Exception:
        pass

    return out if out else None


# ---------------------------------------------------------------------------
# Derived Ratios, Quality Scoring, & Safe Merging
# ---------------------------------------------------------------------------
def enrich_derived_metrics(data: Dict[str, Any], last_close: Optional[float] = None) -> Dict[str, Any]:
    """Derive missing fundamental ratios mathematically from verified financial statement items."""
    out = dict(data)
    close = _clean_float(last_close or out.get("_lastClose"))
    shares = _clean_float(out.get("sharesOutstanding"), digits=2)
    mcap = _clean_float(out.get("marketCap"), digits=2)
    rev = _clean_float(out.get("revenue"), digits=2)
    ni = _clean_float(out.get("netIncome"), digits=2)
    eq = _clean_float(out.get("totalEquity"), digits=2)
    assets = _clean_float(out.get("totalAssets"), digits=2)
    debt = _clean_float(out.get("totalDebt"), digits=2)

    if shares is None and mcap and close and close > 0:
        shares = round(mcap / close, 2)
        out["sharesOutstanding"] = shares

    if out.get("eps") is None and ni is not None and shares and shares > 0:
        out["eps"] = round(ni / shares, 4)
    if out.get("eps") is None and close and close > 0 and out.get("peRatio") and float(out["peRatio"]) > 0:
        out["eps"] = round(close / float(out["peRatio"]), 4)

    if out.get("bookValuePerShare") is None and eq is not None and shares and shares > 0:
        out["bookValuePerShare"] = round(eq / shares, 4)
    if out.get("bookValuePerShare") is None and close and close > 0 and out.get("pbRatio") and float(out["pbRatio"]) > 0:
        out["bookValuePerShare"] = round(close / float(out["pbRatio"]), 4)

    eps = _clean_float(out.get("eps"))
    bvps = _clean_float(out.get("bookValuePerShare"))

    if out.get("peRatio") is None and close and close > 0 and eps and eps > 0:
        pe = close / eps
        if 0.5 <= pe <= 500:
            out["peRatio"] = round(pe, 2)

    if out.get("pbRatio") is None and close and close > 0 and bvps and bvps > 0:
        pb = close / bvps
        if 0.05 <= pb <= 100:
            out["pbRatio"] = round(pb, 2)

    if out.get("roe") is None and ni is not None and eq and eq > 0:
        roe = (ni / eq) * 100.0
        if -200 <= roe <= 300:
            out["roe"] = round(roe, 2)

    if out.get("roa") is None and ni is not None and assets and assets > 0:
        roa = (ni / assets) * 100.0
        if -150 <= roa <= 150:
            out["roa"] = round(roa, 2)

    if out.get("netMargin") is None and ni is not None and rev and rev > 0:
        nm = (ni / rev) * 100.0
        if -300 <= nm <= 200:
            out["netMargin"] = round(nm, 2)

    if out.get("debtToEquity") is None and debt is not None and eq and eq > 0:
        de = debt / eq
        if 0 <= de <= 50:
            out["debtToEquity"] = round(de, 2)

    if out.get("priceToSales") is None and mcap and rev and rev > 0:
        ps = mcap / rev
        if 0.01 <= ps <= 200:
            out["priceToSales"] = round(ps, 2)

    out.pop("_lastClose", None)
    return out


def compute_fundamental_score(data: Dict[str, Any]) -> Optional[int]:
    """
    Compute an institutional 0-100 fundamental quality & valuation score from verified ratios.
    Returns None if fewer than 2 fundamental dimensions are available.
    """
    pts = 0.0
    max_pts = 0.0

    # 1. Valuation: P/E (20 pts)
    pe = _clean_float(data.get("peRatio"))
    if pe is not None and pe > 0:
        max_pts += 20
        if pe <= 8:
            pts += 20
        elif pe <= 12:
            pts += 17
        elif pe <= 18:
            pts += 13
        elif pe <= 28:
            pts += 8
        else:
            pts += 3

    # 2. Valuation: P/B (15 pts)
    pb = _clean_float(data.get("pbRatio"))
    if pb is not None and pb > 0:
        max_pts += 15
        if pb <= 1.2:
            pts += 15
        elif pb <= 2.2:
            pts += 12
        elif pb <= 3.5:
            pts += 8
        else:
            pts += 4

    # 3. Profitability: ROE (20 pts)
    roe = _clean_float(data.get("roe"))
    if roe is not None:
        max_pts += 20
        if roe >= 22:
            pts += 20
        elif roe >= 15:
            pts += 16
        elif roe >= 10:
            pts += 12
        elif roe > 0:
            pts += 6

    # 4. Profitability: Net Margin (15 pts)
    nm = _clean_float(data.get("netMargin"))
    if nm is not None:
        max_pts += 15
        if nm >= 20:
            pts += 15
        elif nm >= 10:
            pts += 11
        elif nm > 0:
            pts += 6

    # 5. Balance Sheet Safety: Debt / Equity & Current Ratio (15 pts)
    de = _clean_float(data.get("debtToEquity"))
    cr = _clean_float(data.get("currentRatio"))
    if de is not None:
        max_pts += 10
        if de <= 0.4:
            pts += 10
        elif de <= 1.0:
            pts += 7
        elif de <= 2.0:
            pts += 4
        else:
            pts += 1
    if cr is not None and cr > 0:
        max_pts += 5
        if cr >= 1.5:
            pts += 5
        elif cr >= 1.0:
            pts += 3
        else:
            pts += 1

    # 6. Cash Flow & Dividends (15 pts)
    fcf = _clean_float(data.get("freeCashFlow"))
    if fcf is not None:
        max_pts += 8
        if fcf > 0:
            pts += 8
    dy = _clean_float(data.get("dividendYield"))
    if dy is not None and dy > 0:
        max_pts += 7
        pts += 7 if dy >= 4.0 else (5 if dy >= 1.5 else 3)

    if max_pts < 25:
        return None
    return max(0, min(100, int(round((pts / max_pts) * 100.0))))


def merge_fundamental_layers(
    existing: Optional[Dict[str, Any]],
    tv_data: Optional[Dict[str, Any]],
    sa_data: Optional[Dict[str, Any]],
    yf_data: Optional[Dict[str, Any]],
    *,
    exchange: str,
    symbol: str,
    last_close: Optional[float] = None,
) -> Tuple[Dict[str, Any], Optional[int]]:
    """
    Merge Existing -> TradingView -> StockAnalysis -> Yahoo Finance (preferring fresher,
    institutional StockAnalysis ratios while preserving all existing metadata and filling every gap).
    """
    spec = MARKET_SPECS.get(exchange, {})
    merged: Dict[str, Any] = dict(existing or {})
    sources: List[str] = []

    # Layer 1: TradingView (strong metadata: sector, industry, logoUrl, 52w high/low, FY/FQ statements)
    if tv_data:
        sources.append("tradingview")
        for k, v in tv_data.items():
            if v is not None and v != "":
                merged[k] = v

    # Layer 2: StockAnalysis (highest institutional accuracy & 45+ ratios across EGX, TADAWUL, QSE, DFM, ADX)
    if sa_data:
        sources.append("stockanalysis")
        for k, v in sa_data.items():
            if v is not None and v != "":
                merged[k] = v

    # Layer 3: Yahoo Finance (fill only remaining gaps)
    if yf_data:
        sources.append("yfinance")
        for k, v in yf_data.items():
            if v is not None and v != "" and merged.get(k) is None:
                merged[k] = v

    # Ensure core identity metadata is present
    merged.setdefault("country", spec.get("country"))
    merged.setdefault("currency", spec.get("currency"))
    merged["symbol"] = symbol
    merged["exchange"] = exchange
    if sources:
        merged["fundamentalsSource"] = "+".join(sources)
        merged["fundamentalsUpdatedAt"] = datetime.now(timezone.utc).isoformat()

    merged = enrich_derived_metrics(merged, last_close=last_close)
    score = compute_fundamental_score(merged)
    return merged, score


def resolve_exchanges_arg(markets_arg: str) -> List[str]:
    """Parse CLI/API market filter like 'egx,tasi,qse,uae' or 'all' into canonical exchanges."""
    out: List[str] = []
    for tok in str(markets_arg or "all").split(","):
        key = tok.strip().lower()
        for ex in MARKET_GROUP_ALIASES.get(key, [key.upper()]):
            if ex in MARKET_SPECS and ex not in out:
                out.append(ex)
    return out or ["EGX", "TADAWUL", "QSE", "DFM", "ADX"]


def _get_supabase_clients() -> Dict[str, Any]:
    from supabase import create_client

    clients: Dict[str, Any] = {}
    p_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    p_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")
    if p_url and p_key:
        clients["primary"] = create_client(p_url, p_key)

    g_url = os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL")
    g_key = (
        os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SAUDI_SUPABASE_SECRET_KEY")
        or os.getenv("SAUDI_SUPABASE_KEY")
    )
    if g_url and g_key:
        clients["gcc"] = create_client(g_url, g_key)

    return clients


def _fetch_paginated(sb: Any, table: str, select_cols: str, exchange: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        batch = (
            sb.table(table)
            .select(select_cols)
            .eq("exchange", exchange)
            .range(offset, offset + 999)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def sync_markets_fundamentals(
    exchanges: Optional[List[str]] = None,
    *,
    use_tradingview: bool = True,
    use_stockanalysis: bool = True,
    use_yfinance_fallback: bool = True,
    max_workers: int = 8,
    dry_run: bool = False,
    limit_per_exchange: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the full 3-tier institutional fundamentals sync across all requested exchanges
    and upsert merged records into Primary (EGX) and GCC (TADAWUL, QSE, DFM, ADX) Supabase.
    """
    target_exchanges = exchanges or ["EGX", "TADAWUL", "QSE", "DFM", "ADX"]
    clients = _get_supabase_clients()
    t0 = time.time()

    # 1. Load active stock catalog + existing stock_fundamentals + latest close prices per exchange
    catalog_by_ex: Dict[str, List[Dict[str, Any]]] = {}
    existing_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    close_by_key: Dict[Tuple[str, str], float] = {}

    for ex in target_exchanges:
        spec = MARKET_SPECS.get(ex)
        if not spec:
            continue
        sb = clients.get(spec["supabase_target"])
        if sb is None:
            logger.warning(f"[fundamentals_sync] Missing Supabase client for {ex} ({spec['supabase_target']})")
            continue

        stocks_rows = _fetch_paginated(sb, "stocks", "symbol,exchange,name,name_ar,country,is_active", ex)
        active_stocks = [r for r in stocks_rows if r.get("symbol") and r.get("is_active", True)]
        if limit_per_exchange:
            active_stocks = active_stocks[:limit_per_exchange]
        catalog_by_ex[ex] = active_stocks

        fund_rows = _fetch_paginated(sb, "stock_fundamentals", "symbol,exchange,name,name_ar,country,data,fund_score", ex)
        for fr in fund_rows:
            sym = str(fr.get("symbol") or "").strip().upper()
            if sym:
                existing_by_key[(ex, sym)] = fr

        # Fetch latest closes (bounded) for derived P/E & P/B computation
        try:
            ti_rows = (
                sb.table("stock_technical_indicators")
                .select("symbol,close,date")
                .eq("exchange", ex)
                .order("date", desc=True)
                .limit(len(active_stocks) * 2 + 50)
                .execute()
                .data
                or []
            )
            for tr in ti_rows:
                sym = str(tr.get("symbol") or "").strip().upper()
                if sym and (ex, sym) not in close_by_key:
                    cl = _clean_float(tr.get("close"))
                    if cl and cl > 0:
                        close_by_key[(ex, sym)] = cl
        except Exception as exc:
            logger.warning(f"[fundamentals_sync] Could not load closes for {ex}: {exc}")

    # 2. Tier 1: TradingView bulk sweep across all target exchanges
    tv_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if use_tradingview:
        tv_map = fetch_tradingview_market_fundamentals(list(catalog_by_ex.keys()))
        logger.info(f"[fundamentals_sync] Tier 1 TradingView matched {len(tv_map)} symbols")

    # 3. Tier 2: StockAnalysis institutional statistics (prioritize symbols still missing core statements/ratios)
    all_pairs: List[Tuple[str, str]] = [
        (ex, str(r["symbol"]).strip().upper())
        for ex, rows in catalog_by_ex.items()
        for r in rows
    ]
    sa_target_pairs: List[Tuple[str, str]] = []
    sa_core_keys = ("revenue", "netIncome", "eps", "peRatio", "roe", "bookValuePerShare")
    for ex, sym in all_pairs:
        ex_d = (existing_by_key.get((ex, sym)) or {}).get("data") or {}
        tv_d = tv_map.get((ex, sym)) or {}
        already_rich = sum(1 for k in sa_core_keys if (tv_d.get(k) is not None or ex_d.get(k) is not None))
        if already_rich < 5:
            sa_target_pairs.append((ex, sym))
    sa_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if use_stockanalysis and sa_target_pairs:
        sa_map = fetch_stockanalysis_bulk(sa_target_pairs, max_workers=min(max_workers, 4))
        logger.info(f"[fundamentals_sync] Tier 2 StockAnalysis matched {len(sa_map)}/{len(sa_target_pairs)} gap symbols")

    # 4. Tier 3: yfinance gap-filler ONLY for symbols still missing >=2 core metrics (eps, peRatio, revenue, netIncome, bookValuePerShare)
    yf_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if use_yfinance_fallback and all_pairs:
        gap_pairs: List[Tuple[str, str]] = []
        core_keys = ("eps", "peRatio", "revenue", "netIncome", "bookValuePerShare")
        for ex, sym in all_pairs:
            ex_d = (existing_by_key.get((ex, sym)) or {}).get("data") or {}
            tv_d = tv_map.get((ex, sym)) or {}
            sa_d = sa_map.get((ex, sym)) or {}
            present = sum(
                1 for k in core_keys if (sa_d.get(k) is not None or tv_d.get(k) is not None or ex_d.get(k) is not None)
            )
            if present < 3:
                gap_pairs.append((ex, sym))
        if gap_pairs:
            logger.info(f"[fundamentals_sync] Tier 3 yfinance gap-filler running on {len(gap_pairs)} symbols...")
            with ThreadPoolExecutor(max_workers=min(max_workers, 6)) as pool:
                futs = {pool.submit(fetch_yfinance_one, ex, sym): (ex, sym) for ex, sym in gap_pairs}
                for fut in as_completed(futs):
                    key = futs[fut]
                    try:
                        d = fut.result()
                        if d:
                            yf_map[key] = d
                    except Exception:
                        pass
            logger.info(f"[fundamentals_sync] Tier 3 yfinance enriched {len(yf_map)}/{len(gap_pairs)} gap symbols")

    # 5. Merge, score, and batch upsert per exchange
    now_iso = datetime.now(timezone.utc).isoformat()
    report: Dict[str, Any] = {"elapsed_sec": 0.0, "markets": {}}

    for ex, stocks_rows in catalog_by_ex.items():
        spec = MARKET_SPECS[ex]
        sb = clients[spec["supabase_target"]]
        upsert_rows: List[Dict[str, Any]] = []
        metrics_cov = {
            "marketCap": 0,
            "peRatio": 0,
            "pbRatio": 0,
            "eps": 0,
            "bookValuePerShare": 0,
            "roe": 0,
            "roa": 0,
            "dividendYield": 0,
            "revenue": 0,
            "netIncome": 0,
            "grossMargin": 0,
            "operatingMargin": 0,
            "netMargin": 0,
            "ebitda": 0,
            "freeCashFlow": 0,
            "debtToEquity": 0,
            "currentRatio": 0,
            "fund_score": 0,
        }

        for st in stocks_rows:
            sym = str(st["symbol"]).strip().upper()
            key = (ex, sym)
            prev_row = existing_by_key.get(key) or {}
            prev_data = prev_row.get("data") if isinstance(prev_row.get("data"), dict) else {}

            merged_data, score = merge_fundamental_layers(
                prev_data,
                tv_map.get(key),
                sa_map.get(key),
                yf_map.get(key),
                exchange=ex,
                symbol=sym,
                last_close=close_by_key.get(key),
            )

            name_en = st.get("name") or prev_row.get("name") or merged_data.get("name") or sym
            name_ar = st.get("name_ar") or prev_row.get("name_ar") or merged_data.get("name_ar")
            if name_ar and not merged_data.get("name_ar"):
                merged_data["name_ar"] = name_ar

            row_payload: Dict[str, Any] = {
                "symbol": sym,
                "exchange": ex,
                "name": name_en,
                "country": st.get("country") or spec["country"],
                "data": merged_data,
                "updated_at": now_iso,
            }
            if name_ar is not None:
                row_payload["name_ar"] = name_ar
            if score is not None:
                row_payload["fund_score"] = score
            elif prev_row.get("fund_score") is not None:
                row_payload["fund_score"] = prev_row["fund_score"]

            upsert_rows.append(row_payload)

            for k in metrics_cov:
                if k == "fund_score":
                    if row_payload.get("fund_score") is not None:
                        metrics_cov[k] += 1
                elif merged_data.get(k) is not None:
                    metrics_cov[k] += 1

        written = 0
        if not dry_run and upsert_rows:
            for i in range(0, len(upsert_rows), 50):
                chunk = upsert_rows[i : i + 50]
                sb.table("stock_fundamentals").upsert(chunk, on_conflict="symbol,exchange").execute()
                written += len(chunk)

        total = len(upsert_rows)
        report["markets"][ex] = {
            "total_symbols": total,
            "upserted": written,
            "tv_hits": sum(1 for r in upsert_rows if (ex, r["symbol"]) in tv_map),
            "sa_hits": sum(1 for r in upsert_rows if (ex, r["symbol"]) in sa_map),
            "yf_hits": sum(1 for r in upsert_rows if (ex, r["symbol"]) in yf_map),
            "coverage": {
                k: {"count": c, "pct": round((c / total) * 100.0, 1) if total else 0.0}
                for k, c in metrics_cov.items()
            },
        }

    report["elapsed_sec"] = round(time.time() - t0, 1)
    return report
