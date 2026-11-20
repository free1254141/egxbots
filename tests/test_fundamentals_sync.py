"""Unit tests for the unified 3-tier 4-market fundamentals sync & rich AI chat fundamental extraction."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.fundamentals_sync import (
    compute_fundamental_score,
    enrich_derived_metrics,
    merge_fundamental_layers,
    parse_human_number,
    parse_stockanalysis_statistics_html,
    resolve_exchanges_arg,
)
from api.agentic_chat.tools_execution import (
    _compute_fundamental_fair_value,
    _extract_rich_fundamentals,
)


def test_parse_human_number_variants():
    assert parse_human_number("434.16B") == 434_160_000_000.0
    assert parse_human_number("6.41T") == 6_410_000_000_000.0
    assert parse_human_number("-113.05B") == -113_050_000_000.0
    assert parse_human_number("885.16M") == 885_160_000.0
    assert parse_human_number("39.41%") == 39.41
    assert parse_human_number("+2.48%") == 2.48
    assert parse_human_number("10.61") == 10.61
    assert parse_human_number("n/a") is None
    assert parse_human_number("Upgrade") is None
    assert parse_human_number("--") is None


def test_parse_stockanalysis_statistics_html():
    sample_html = """
    <html><body>
      <table>
        <tr><td>Market Cap</td><td>2.18B</td></tr>
        <tr><td>PE Ratio</td><td>10.61</td></tr>
        <tr><td>PB Ratio</td><td>4.07</td></tr>
        <tr><td>Return on Equity (ROE)</td><td>39.41%</td></tr>
        <tr><td>Revenue</td><td>885.16M</td></tr>
        <tr><td>Net Income</td><td>205.24M</td></tr>
        <tr><td>Earnings Per Share (EPS)</td><td>34.21</td></tr>
        <tr><td>Book Value Per Share</td><td>89.05</td></tr>
        <tr><td>Dividend Yield</td><td>6.34%</td></tr>
        <tr><td>Current Ratio</td><td>1.20</td></tr>
        <tr><td>Profit Margin</td><td>23.19%</td></tr>
        <tr><td>Debt / Equity</td><td>n/a</td></tr>
        <tr><td>Graham Number</td><td>Upgrade</td></tr>
        <tr><td>Ex-Dividend Date</td><td>Nov 1, 2026</td></tr>
        <tr><td>Piotroski F-Score</td><td>7</td></tr>
        <tr><td>Altman Z-Score</td><td>4.25</td></tr>
      </table>
    </body></html>
    """
    parsed = parse_stockanalysis_statistics_html(sample_html)
    assert parsed["marketCap"] == 2_180_000_000.0
    assert parsed["peRatio"] == 10.61
    assert parsed["pbRatio"] == 4.07
    assert parsed["roe"] == 39.41
    assert parsed["revenue"] == 885_160_000.0
    assert parsed["netIncome"] == 205_240_000.0
    assert parsed["eps"] == 34.21
    assert parsed["bookValuePerShare"] == 89.05
    assert parsed["dividendYield"] == 6.34
    assert parsed["currentRatio"] == 1.2
    assert parsed["netMargin"] == 23.19
    assert parsed["exDividendDate"] == "Nov 1, 2026"
    assert parsed["piotroskiFScore"] == 7.0
    assert parsed["altmanZScore"] == 4.25
    assert "debtToEquity" not in parsed


def test_derived_metrics_merge_and_score():
    existing = {"isin": "EGS30351C018", "listingStatus": "listed", "name_ar": "مطاحن شرق الدلتا"}
    tv = {"sector": "Consumer Non-Durables", "marketCap": 2_180_000_000.0, "totalAssets": 900_000_000.0, "totalEquity": 500_000_000.0, "sharesOutstanding": 6_000_000.0}
    sa = {"revenue": 885_000_000.0, "netIncome": 205_000_000.0, "dividendYield": 6.34, "freeCashFlow": 150_000_000.0, "currentRatio": 1.6, "debtToEquity": 0.2}
    yf = {"ebitda": 240_000_000.0, "revenue": 1.0}  # revenue must NOT overwrite StockAnalysis

    merged, score = merge_fundamental_layers(
        existing, tv, sa, yf, exchange="EGX", symbol="EDFM", last_close=363.0
    )
    assert merged["isin"] == "EGS30351C018"
    assert merged["name_ar"] == "مطاحن شرق الدلتا"
    assert merged["revenue"] == 885_000_000.0
    assert merged["ebitda"] == 240_000_000.0
    assert merged["eps"] is not None and abs(merged["eps"] - (205_000_000.0 / 6_000_000.0)) < 0.01
    assert merged["peRatio"] is not None and 9.0 < merged["peRatio"] < 12.0
    assert merged["roe"] is not None and abs(merged["roe"] - 41.0) < 0.5
    assert merged["netMargin"] is not None and abs(merged["netMargin"] - 23.16) < 0.2
    assert score is not None and 70 <= score <= 100
    assert merged["fundamentalsSource"] == "tradingview+stockanalysis+yfinance"


def test_resolve_exchanges_arg():
    assert resolve_exchanges_arg("all") == ["EGX", "TADAWUL", "QSE", "DFM", "ADX"]
    assert resolve_exchanges_arg("egx,uae") == ["EGX", "DFM", "ADX"]
    assert resolve_exchanges_arg("tasi,qatar") == ["TADAWUL", "QSE"]


def test_tools_execution_rich_fundamentals_and_graham_fair_value():
    fd = {
        "peRatio": 7.14,
        "pbRatio": 1.69,
        "eps": 18.25,
        "bookValuePerShare": 70.16,
        "roe": 35.69,
        "dividendYield": 3.5,
        "marketCap": 434_160_000_000.0,
        "revenue": 120_660_000_000.0,
        "netIncome": 82_240_000_000.0,
        "debtToEquity": 0.13,
        "sector": "Finance",
    }
    extracted = _extract_rich_fundamentals(fd, fund_score=88)
    assert extracted["pe_ratio"] == 7.14
    assert extracted["pb_ratio"] == 1.69
    assert extracted["eps"] == 18.25
    assert extracted["book_value_per_share"] == 70.16
    assert extracted["roe_pct"] == 35.69
    assert extracted["market_cap"] == 434_160_000_000.0
    assert extracted["fund_score"] == 88.0
    assert "ebitda" not in extracted  # None keys omitted to save LLM tokens

    fv, model, extra = _compute_fundamental_fair_value(130.0, 125.0, 120.0, fd)
    expected_graham = round((22.5 * 18.25 * 70.16) ** 0.5, 2)
    assert fv == expected_graham
    assert "جراهام" in model
    assert extra["pe_ratio"] == 7.14
    assert extra["roe_pct"] == 35.69

    # Fallback when fundamentals absent -> VWAP/EMA quant model
    fv_q, model_q, _ = _compute_fundamental_fair_value(100.0, 105.0, 95.0, {})
    assert fv_q == 101.0
    assert "التوازن الكمي" in model_q


def test_fundamental_diagnosis_archetypes_bank_value_trap_loss_and_expensive():
    import api.agentic_chat.analysis_cache as ac

    # 1. Strong Value + Cash + Dividend (e.g. EMAAR)
    strong = _extract_rich_fundamentals(
        {
            "peRatio": 5.68,
            "pbRatio": 1.12,
            "eps": 2.20,
            "bookValuePerShare": 11.14,
            "roe": 20.88,
            "netMargin": 34.6,
            "netIncome": 17_600_000_000.0,
            "freeCashFlow": 15_000_000_000.0,
            "debtToEquity": 0.08,
            "currentRatio": 3.5,
            "dividendYield": 8.04,
            "sector": "Real Estate",
        },
        fund_score=96,
        close_price=12.48,
        name="Emaar Properties",
    )
    diag = strong["fundamental_diagnosis"]
    assert diag["is_financial_institution"] is False
    assert "ممتاز مالياً" in diag["verdict_ar"]
    assert "value_trap_warning" not in diag
    assert any("التدفق النقدي" in s or "كاش" in s for s in diag["strengths"])

    # 2. Bank with D/E = 2.73 must NOT be flagged with industrial solvency risk
    bank = _extract_rich_fundamentals(
        {
            "peRatio": 10.08,
            "pbRatio": 1.47,
            "eps": 1.80,
            "bookValuePerShare": 12.32,
            "roe": 15.44,
            "roa": 1.55,
            "debtToEquity": 2.73,
            "dividendYield": 3.94,
            "sector": "Finance",
            "industry": "Regional Banks",
        },
        fund_score=75,
        close_price=18.11,
        name="Qatar National Bank",
    )
    bdiag = bank["fundamental_diagnosis"]
    assert bdiag["is_financial_institution"] is True
    assert not any("مديونية عالية" in w for w in bdiag["weaknesses"])
    assert "بنك" in bdiag["financial_health"]

    # 3. Loss-making company
    loss = _extract_rich_fundamentals(
        {"eps": -1.25, "netIncome": -45_000_000.0, "roe": -18.5, "pbRatio": 1.8, "sector": "Industrials"},
        fund_score=20,
        close_price=5.0,
    )
    assert "خسائر" in loss["fundamental_diagnosis"]["verdict_ar"]

    # 4. Value Trap (low P/E=6.5 hiding negative FCF + high debt + low Piotroski)
    trap = _extract_rich_fundamentals(
        {
            "peRatio": 6.5,
            "eps": 1.5,
            "netIncome": 100_000_000.0,
            "freeCashFlow": -80_000_000.0,
            "debtToEquity": 1.9,
            "currentRatio": 0.85,
            "piotroskiFScore": 2,
            "sector": "Materials",
        },
        fund_score=58,
        close_price=9.75,
    )
    assert "value_trap_warning" in trap["fundamental_diagnosis"]
    assert "فخ قيمة" in trap["fundamental_diagnosis"]["verdict_ar"]

    # 5. High-quality but expensive growth stock
    exp = _extract_rich_fundamentals(
        {"peRatio": 34.0, "pbRatio": 5.5, "eps": 0.5, "roe": 26.0, "debtToEquity": 0.25, "sector": "Technology"},
        fund_score=72,
        close_price=17.0,
    )
    assert "مرتفع" in exp["fundamental_diagnosis"]["verdict_ar"]

    # 5b. Real estate under TV sector="Finance" & FinTech with "Banking Technology" in name must NOT be classified as banks
    re_dev = _extract_rich_fundamentals(
        {"peRatio": 6.0, "roe": 20.0, "debtToEquity": 0.08, "sector": "Finance", "industry": "Real Estate Development"},
        fund_score=90, close_price=12.0, name="Emaar Properties",
    )
    assert re_dev["fundamental_diagnosis"]["is_financial_institution"] is False
    fintech = _extract_rich_fundamentals(
        {"peRatio": 16.6, "roe": 41.6, "debtToEquity": 0.4, "sector": "Technology Services", "industry": "Data Processing Services"},
        fund_score=75, close_price=17.3, name="Fawry for Banking Technology and Electronic Payment",
    )
    assert fintech["fundamental_diagnosis"]["is_financial_institution"] is False
    assert "نمو" in fintech["fundamental_diagnosis"]["verdict_ar"]

    # 6. Arabic financial cache key routing (triggers financial Fast-Track)
    assert ac.build_analysis_cache_key("حلل سهم فوري ماليا", market="EGX") == "vip_stock_FWRY_financials"
    assert ac.build_analysis_cache_key("التحليل الاساسي لسهم 2222", market="TADAWUL") == "vip_stock_2222_financials"

