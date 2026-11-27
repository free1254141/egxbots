"""
Offline deterministic regression tests for the 2026-11-28 ARTORO AI Chat structural fixes:
1. Check G (Multi-Stock Price Cross-Verification + Ungrounded History Table Circuit-Breaker — [22]/[26]).
2. Split-EMA bear-market guard (KORA 2.13 vs 2.57) + Dual Fair-Value parity ([11]/[12]).
3. Small-portfolio optimizer accounting invariant (totalSellValue == leftoverCash delta) + currentSectorBreakdown ([28]).
4. Unified fuzzy Arabic alias rescue ('بلم هيلز' -> PHDC) across hints, cache key, and standalone detection ([29]).
5. Bare Arabic company names ('القاهرة للدواجن', 'جلاكسو') unlocking 0-token Early Cache ([14]/[21]).
6. Canonical Preset Fast-Track for `vip_top_stocks` ([25]/[33]), 4096 max_tokens ([23]), weekend Sunday note,
   vision prompt dedupe, Telegram 4600-char compaction + guard_warnings logging, and zero hardcoded quantity:100 in StockCard.tsx.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np

from api.agentic_chat.output_guard import verify_and_guard_reply
from api.agentic_chat.tools_execution import _detect_and_adjust_price_split, _sync_get_fair_value
from api.agentic_chat.pipeline import (
    known_symbol_hints,
    _is_unambiguous_standalone_input,
    _resolve_query_market,
)
from api.agentic_chat.analysis_cache import build_analysis_cache_key
from api.stock_aliases import fuzzy_resolve_arabic_alias_match, resolve_stock_symbol
from api.portfolio_or_optimizer import AssetInput, optimize_portfolio_or

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Check G: Ungrounded History Table Circuit-Breaker & Multi-Stock Price Check
# ---------------------------------------------------------------------------

def test_check_g2_quarantines_ungrounded_history_table_hallucination():
    """Reproduces [26]: manage_portfolio returned 0 positions, yet LLM fabricated an 11-stock table with GSSC=8.42."""
    hallucinated_reply = (
        "# 📭 محفظتك المسجلة فاضية\n\n"
        "| # | السهم | الكود | السعر (ج.م) | التغير | RSI | القيمة العادلة | الشرعية |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| 1 | أبو ظبي الإسلامي | ADIB | 45.98 | +0.11% | 35.28 | 67.56 | ✅ |\n"
        "| 8 | إي إف جي هيرميس | EFIH | 24.50 | -0.81% | 44.90 | 19.80 | ✅ |\n"
        "| 9 | جي إس سي | GSSC | 8.42 | -0.47% | 38.20 | 7.10 | ✅ |\n"
        "| 11 | زهرة للزيوت | ZEOT | 12.85 | -0.39% | 42.10 | 10.90 | ✅ |\n"
    )
    tool_payloads = [
        {"status": "success", "operation": "view", "positions": [], "cash_balance": 0.0}
    ]
    res = verify_and_guard_reply(hallucinated_reply, tool_payloads, market="EGX")
    assert any(w.startswith("ungrounded_stock_table:") for w in res["warnings"])
    assert res["block_cache"] is True
    assert "حماية دقة البيانات التلقائية" in res["reply"]
    # Every fabricated figure MUST be scrubbed so the user NEVER sees GSSC = 8.42 or fake RSI/FV
    assert "8.42" not in res["reply"]
    assert "38.20" not in res["reply"]
    assert "24.50" not in res["reply"]
    assert "12.85" not in res["reply"]
    assert "⚠️ غير مُحدّث في هذا الدور" in res["reply"]


def test_check_g1_verifies_multi_stock_prices_and_passes_grounded_table():
    """Grounded table passes with 0 warnings; >5% price error in a grounded table gets caught."""
    tool_payloads = [
        {
            "status": "success",
            "stocks": [
                {"symbol": "GSSC", "close": 225.25, "currency": "ج.م"},
                {"symbol": "EFIH", "close": 24.61, "currency": "ج.م"},
            ],
        }
    ]
    good_reply = (
        "| # | السهم | الكود | السعر (ج.م) | RSI | الشرعية |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | الصوامع والتخزين | GSSC | 225.25 | 26.24 | ❌ |\n"
        "| 2 | إي فاينانس | EFIH | 24.61 | 59.49 | ✅ |\n"
    )
    good_res = verify_and_guard_reply(good_reply, tool_payloads, market="EGX")
    assert good_res["warnings"] == []
    assert good_res["block_cache"] is False

    bad_reply = (
        "| # | السهم | الكود | السعر (ج.م) | RSI | الشرعية |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | الصوامع والتخزين | GSSC | 8.42 | 26.24 | ❌ |\n"
        "| 2 | إي فاينانس | EFIH | 24.61 | 59.49 | ✅ |\n"
    )
    bad_res = verify_and_guard_reply(bad_reply, tool_payloads, market="EGX")
    assert any(w.startswith("multi_stock_price_mismatch:GSSC:") for w in bad_res["warnings"])
    assert bad_res["block_cache"] is True
    assert "225.25 ج.م" in bad_res["reply"]


# ---------------------------------------------------------------------------
# 2. Split-EMA False Positive Fix (KORA) & Dual Fair-Value Tolerance
# ---------------------------------------------------------------------------

def test_bear_drawdown_does_not_trigger_false_split_ema_while_real_split_still_triggers():
    """KORA's gradual -44% bear decline (3.39 -> 1.88) keeps DB EMA200=2.9495; POUL's 3.7:1 split still adjusts."""
    # Gradual decline (no overnight <0.45x jump), max_25 ~ 2.05, DB EMA200 = 2.9495 (1.44x max_25 < 1.85x)
    kora_desc = [{"close": round(1.88 + i * 0.025, 4)} for i in range(60)]
    ema50, ema200, sf, adj = _detect_and_adjust_price_split(kora_desc, 2.3211, 2.9495, 1.88)
    assert adj is False
    assert sf is None
    assert ema200 == 2.9495

    # Real corporate split (POUL overnight drop 39.89 -> 10.79, ratio 0.27 < 0.45)
    poul_desc = [{"close": 6.83 + (i * 0.05)} for i in range(25)] + [{"close": 39.89} for _ in range(20)]
    p_ema50, p_ema200, p_sf, p_adj = _detect_and_adjust_price_split(poul_desc, 9.16, 9.16, 6.83)
    assert p_adj is True
    assert p_sf is not None and p_sf < 0.45
    assert p_ema50 is not None and p_ema200 is not None


def test_output_guard_accepts_any_tool_returned_fair_value_and_flags_real_fabrication():
    """If get_stock and get_fair_value return valid values, Check F never cries wolf — yet catches fabricated 9.99."""
    payloads = [
        {"status": "success", "stocks": [{"symbol": "KORA", "close": 1.88, "fair_value": 2.13, "currency": "ج.م"}]},
        {
            "status": "success",
            "fair_value_stocks": [
                {
                    "symbol": "KORA",
                    "current_price": 1.88,
                    "fair_value": 2.57,
                    "currency": "ج.م",
                    "status_ar": "أقل من السعر العادل 🟢",
                    "formula_substitution_ar": "(0.60 × 2.95) + (0.40 × 1.99) = 2.57 ج.م",
                }
            ],
        },
    ]
    ok_reply = "**السعر الأخير:** 1.88 ج.م | **القيمة العادلة:** 2.57 ج.م"
    ok_res = verify_and_guard_reply(ok_reply, payloads, market="EGX")
    assert not any(w.startswith("fair_value_hallucination") for w in ok_res["warnings"])

    fake_reply = "**السعر الأخير:** 1.88 ج.م | **القيمة العادلة:** 9.99 ج.م"
    fake_res = verify_and_guard_reply(fake_reply, payloads, market="EGX")
    assert any(w.startswith("fair_value_hallucination:KORA:") for w in fake_res["warnings"])


# ---------------------------------------------------------------------------
# 3. Small-Portfolio Optimizer Accounting Invariant & Current Sector Breakdown
# ---------------------------------------------------------------------------

def test_small_portfolio_optimizer_reconciles_sales_and_preserves_current_sectors():
    """Reproduces [28]: 254.70 EGP portfolio (KORA 100 @ 1.88 + LUTS 100 @ 0.667 excluded)."""
    dates = [f"2026-10-{d:02d}" for d in range(1, 31)]
    rng = np.random.default_rng(42)
    kora_rets = {dt: float(r) for dt, r in zip(dates, rng.normal(0.0, 0.015, len(dates)))}
    luts_rets = {dt: float(r) for dt, r in zip(dates, rng.normal(0.0, 0.02, len(dates)))}

    assets = [
        AssetInput(
            symbol="KORA",
            name_ar="قرة للطاقة",
            sector="طاقة ومرافق",
            price=1.88,
            returns_by_date=kora_rets,
            current_shares=100,
        ),
        AssetInput(
            symbol="LUTS",
            name_ar="لوتس للاستثمار",
            sector="خدمات مالية غير مصرفية",
            price=0.667,
            returns_by_date=luts_rets,
            current_shares=100,
            max_weight_override=0.0,
            exclusion_reason="شركة خاسرة (EPS سلبي)",
        ),
    ]
    res = optimize_portfolio_or(
        assets,
        total_capital=254.70,
        objective="hrp",
        max_weight_pct=35.0,
        max_sector_pct=45.0,
    )
    by_sym = {r["symbol"]: r for r in res["allocations"]}
    assert by_sym["LUTS"]["action"] == "SELL"
    assert by_sym["KORA"]["action"] == "SELL"
    assert by_sym["KORA"]["deltaShares"] < 0

    ts = res["tradeSummary"]
    assert ts["sellCount"] == 2
    assert abs(ts["totalSellValue"] - res["leftoverCash"]) < 0.05
    # Current sectors MUST reflect both holdings before LUTS exclusion
    curr_sectors = {s["sector"] for s in res["currentSectorBreakdown"]}
    assert "طاقة ومرافق" in curr_sectors
    assert "خدمات مالية غير مصرفية" in curr_sectors


# ---------------------------------------------------------------------------
# 4. Unified Fuzzy Arabic Alias Rescue + Bare Arabic Standalone Early Cache
# ---------------------------------------------------------------------------

def test_fuzzy_arabic_typo_unified_across_hints_cache_and_standalone():
    """'بلم هيلز' (1-letter typo for 'بالم هيلز') resolves to PHDC across ALL 3 subsystems."""
    assert resolve_stock_symbol("بلم هيلز") == "PHDC"
    assert fuzzy_resolve_arabic_alias_match("بلم هيلز") == ("بلم هيلز", "PHDC")

    hints = known_symbol_hints("بلم هيلز")
    assert hints and hints[0]["symbols"] == ["PHDC"]

    assert build_analysis_cache_key("بلم هيلز", market="EGX") == "vip_stock_PHDC"
    assert build_analysis_cache_key("حلل سهم بلم هيلز", market="EGX") == "vip_stock_PHDC"
    assert build_analysis_cache_key("بلم هيلز ليه نزل النهارده", market="EGX") is None

    assert _is_unambiguous_standalone_input("بلم هيلز", market="EGX") is True
    assert _is_unambiguous_standalone_input("حلل سهم بلم هيلز", market="EGX") is False


def test_bare_arabic_company_names_are_unambiguous_standalone_for_early_cache():
    """'القاهرة للدواجن' ([14]) & 'جلاكسو' ([21]) unlock 0-token Early Cache even with conversation history."""
    assert _is_unambiguous_standalone_input("القاهرة للدواجن", market="EGX") is True
    assert _is_unambiguous_standalone_input("جلاكسو", market="EGX") is True
    assert _is_unambiguous_standalone_input("لوتس", market="EGX") is True
    # Multi-word prompts MUST remain False to protect contextual-followup semantics
    assert _is_unambiguous_standalone_input("حلل سهم PHDC", market="EGX") is False
    assert _is_unambiguous_standalone_input("ما رأيك في جلاكسو", market="EGX") is False


# ---------------------------------------------------------------------------
# 5. Architectural Contract Checks (Fast-Track, 4096 max_tokens, Telegram, StockCard)
# ---------------------------------------------------------------------------

def test_pipeline_telegram_and_stockcard_structural_contracts():
    pipeline_src = (ROOT / "api" / "agentic_chat" / "pipeline.py").read_text(encoding="utf-8")
    assert '"vip_top_stocks"' in pipeline_src
    assert '"max_tokens": 3000' not in pipeline_src
    assert pipeline_src.count('"max_tokens": 4096') >= 2
    assert "يوم الأحد القادم" in pipeline_src
    assert "أداة get_stock فقط (ولا تستدعِ get_stock_levels المكررة)" in pipeline_src

    tg_src = (ROOT / "api" / "native_telegram_vip_chat.py").read_text(encoding="utf-8")
    assert "reply_text[:1600]" not in tg_src
    assert "_compact_history_content(reply_text" in tg_src
    assert 'common_meta["guard_warnings"]' in tg_src
    assert "📷 صورة مرفقة للتحليل" in tg_src

    stock_card_src = (ROOT / "web" / "src" / "components" / "chat" / "StockCard.tsx").read_text(encoding="utf-8")
    assert "quantity: 100" not in stock_card_src
    assert "/api/portfolio" not in stock_card_src


# ---------------------------------------------------------------------------
# 6. QA Adversarial Regression Tests (5 Legitimate Table Shapes, 50-Row Split FV,
#    40-Seed Zero-Cash Budget Ceiling, and Saudi Exact Alias Priority)
# ---------------------------------------------------------------------------

def test_check_g_zero_false_positives_on_all_five_legitimate_table_shapes():
    """All 5 legitimate Markdown table formats must produce 0 warnings and block_cache=False."""
    comi_payload = [{"status": "success", "stocks": [{"symbol": "COMI", "close": 85.0, "currency": "ج.م"}]}]

    # 1. DCA plan table (no stock column, 2500 EGP tranche amount)
    dca_table = (
        "| الدفعة | المبلغ | السعر | الدعم |\n"
        "|---|---|---|---|\n"
        "| الدفعة الأولى | 2500 | 82.00 | 80.00 |\n"
        "| الدفعة الثانية | 2500 | 79.00 | 78.00 |\n"
    )
    r1 = verify_and_guard_reply(dca_table, comi_payload, market="EGX")
    assert r1["warnings"] == [] and r1["block_cache"] is False

    # 2. Portfolio table with Arabic names + 4-digit share quantities (1500, 2500)
    pf_payload = [
        {
            "status": "success",
            "operation": "view",
            "positions": [
                {"symbol": "COMI", "current_price": 85.0, "currency": "ج.م"},
                {"symbol": "FWRY", "current_price": 17.2, "currency": "ج.م"},
            ],
        }
    ]
    pf_table = (
        "| السهم | الكمية | السعر الحالي | التغير |\n"
        "|---|---|---|---|\n"
        "| البنك التجاري الدولي | 1500 | 85.00 | +1.2% |\n"
        "| فوري | 2500 | 17.20 | -0.3% |\n"
    )
    r2 = verify_and_guard_reply(pf_table, pf_payload, market="EGX")
    assert r2["warnings"] == [] and r2["block_cache"] is False

    # 3. Arabic stock table with English rating/signal words (STRONG, HIGH)
    sig_table = (
        "| السهم | السعر (ج.م) | الإشارة | التقييم |\n"
        "|---|---|---|---|\n"
        "| البنك التجاري الدولي (COMI) | 85.00 | STRONG | HIGH |\n"
    )
    r3 = verify_and_guard_reply(sig_table, comi_payload, market="EGX")
    assert r3["warnings"] == [] and r3["block_cache"] is False

    # 4. Open recommendations table with 'السعر عند الدخول' before 'السعر الحالي'
    recs_table = (
        "| السهم | السعر عند الدخول | السعر الحالي | التغير | التقييم |\n"
        "|---|---|---|---|---|\n"
        "| التجاري الدولي (COMI) | 75.00 | 85.00 | +13.3% | إيجابي |\n"
    )
    r4 = verify_and_guard_reply(recs_table, comi_payload, market="EGX")
    assert r4["warnings"] == [] and r4["block_cache"] is False

    # 5. English headers with 'Entry Price' before 'Current Price'
    en_table = (
        "| Stock | Entry Price | Current Price | RSI |\n"
        "|---|---|---|---|\n"
        "| COMI | 75.00 | 85.00 | 58.2 |\n"
    )
    r5 = verify_and_guard_reply(en_table, comi_payload, market="EGX")
    assert r5["warnings"] == [] and r5["block_cache"] is False


def test_sync_get_fair_value_deduplicates_50_rows_and_queries_split_history(monkeypatch):
    """When stock_technical_indicators returns 50 multi-date rows for 1 symbol (POUL), split history MUST be queried."""
    queried_tables: list[tuple[str, int | None]] = []

    class _FakeResp:
        def __init__(self, data):
            self.data = data

    class _FakeQuery:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self._limit: int | None = None

        def select(self, *_a, **_kw):
            return self

        def eq(self, *_a, **_kw):
            return self

        def in_(self, *_a, **_kw):
            return self

        def order(self, *_a, **_kw):
            return self

        def limit(self, n):
            self._limit = n
            return self

        def execute(self):
            queried_tables.append((self.table_name, self._limit))
            if self.table_name == "stock_technical_indicators":
                return _FakeResp([
                    {
                        "symbol": "POUL",
                        "close": 6.83,
                        "change_pct": 1.49,
                        "vwap_20": 7.45,
                        "ema_50": 9.17,
                        "ema_200": 9.16,
                        "date": f"2026-11-{max(1, 26 - (i % 25)):02d}",
                    }
                    for i in range(50)
                ])
            if self.table_name == "stock_fundamentals":
                return _FakeResp([])
            if self.table_name == "stock_prices":
                # Overnight split 39.89 -> 10.79 (ratio 0.27 < 0.45)
                rows = [{"symbol": "POUL", "date": f"2026-11-{26 - i:02d}", "close": 6.83 + i * 0.05} for i in range(25)]
                rows += [{"symbol": "POUL", "date": f"2026-09-{25 - i:02d}", "close": 39.89} for i in range(20)]
                return _FakeResp(rows)
            return _FakeResp([])

    class _FakeSB:
        def from_(self, name: str):
            return _FakeQuery(name)

    monkeypatch.setattr("api.agentic_chat.tools_execution._get_sb", lambda: _FakeSB())
    res = _sync_get_fair_value(symbols=["POUL"], mode="specific_stocks", market="EGX")
    assert res["status"] == "success"
    price_calls = [lim for tbl, lim in queried_tables if tbl == "stock_prices"]
    assert len(price_calls) == 1
    assert price_calls[0] == 120


def test_optimizer_zero_cash_40_seeds_never_overshoots_capital():
    """Zero-cash 6-stock 20,000 EGP portfolios across 40 seeds must NEVER exceed capital or emit unfunded BUYs."""
    dates = [f"2026-10-{d:02d}" for d in range(1, 31)]
    sectors = ["بنوك", "عقارات", "أغذية", "كيماويات", "اتصالات", "صناعة"]
    prices = [100.0, 50.0, 40.0, 25.0, 20.0, 10.0]
    shares = [40, 60, 75, 160, 200, 200]  # sum = 4000+3000+3000+4000+4000+2000 = 20,000 EGP (0 cash)

    for seed in range(40):
        rng = np.random.default_rng(seed)
        assets = [
            AssetInput(
                symbol=f"SYM{k}",
                name_ar=f"سهم {k}",
                sector=sectors[k],
                price=prices[k],
                returns_by_date={dt: float(r) for dt, r in zip(dates, rng.normal(0.0, 0.015 + k * 0.003, len(dates)))},
                current_shares=shares[k],
            )
            for k in range(6)
        ]
        res = optimize_portfolio_or(
            assets,
            total_capital=20000.0,
            objective="hrp",
            max_weight_pct=35.0,
            max_sector_pct=45.0,
        )
        assert res["investedAmount"] <= res["totalCapital"] + 1e-6, f"seed {seed} overshot capital"
        assert abs((res["totalCapital"] - res["investedAmount"]) - res["leftoverCash"]) < 0.02, f"seed {seed} cash mismatch"
        ts = res["tradeSummary"]
        assert ts["totalBuyValue"] <= ts["totalSellValue"] + 1e-6, f"seed {seed} unfunded buy"
        assert abs(ts["netCashDelta"] - res["leftoverCash"]) < 0.02, f"seed {seed} netCashDelta mismatch"


def test_saudi_exact_alias_never_polluted_by_egx_fuzzy_fallback():
    """Exact Saudi company names (e.g. 'جي آي جي') must resolve ONLY to TASI 8250, never polluted by EGX fuzzy BIGP."""
    hints = known_symbol_hints("جي آي جي")
    assert len(hints) == 1
    assert hints[0]["symbols"] == ["8250"]
    assert hints[0]["market"] == "TASI"
    mkt, is_cross = _resolve_query_market("جي آي جي", active_market="EGX", hints=hints)
    assert mkt == "TADAWUL"
    assert is_cross is False

