"""
Deterministic Corporate Events & Reality-Check Engine (Zero-LLM, Zero-Vercel-CPU).

Single source of truth for:
1. Event Reality-Check (#4): compares disclosure/news polarity against same-session
   price change, relative volume (r_vol), and accumulation/distribution scores to flag
   "Sell the News" (تصريف على الخبر) vs "Institutional Confirmation" (تأكيد شرائي مؤسسي).
2. Corporate Actions & Ex-Date Impact Calculator (#5): exact deterministic math for
   bonus shares (أسهم مجانية), stock splits (تجزئة), cash dividends (كوبون نقدي + صافي بعد الضريبة),
   and rights issues (حقوق اكتتاب / TERP) including portfolio average-cost adjustment.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

_POS_EVENT_RE = re.compile(
    r"توزيع|كوبون|أسهم مجانية|اسهم مجانية|منحة|نمو|ارتفاع الأرباح|ارتفاع صافى|زيادة الأرباح|"
    r"تعاقد|عقد جديد|استحواذ|شراء خزينة|أسهم خزينة|تجزئة|dividend|bonus|buyback|contract|profit growth",
    re.IGNORECASE,
)
_NEG_EVENT_RE = re.compile(
    r"خسائر|خسارة|تراجع الأرباح|انخفاض الأرباح|تخارج|إيقاف|تعليق|غرامة|شطب|نزاع|تحذير|"
    r"loss|decline|suspend|penalty|delist",
    re.IGNORECASE,
)


def _safe_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _price_decimals(price: float) -> int:
    if price < 2.0:
        return 3
    if price < 10.0:
        return 3
    return 2


def infer_event_polarity(
    sentiment: Optional[str] = None,
    action_type: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """Infer 'positive', 'negative', or 'neutral' polarity from disclosure metadata."""
    s = str(sentiment or "").strip().lower()
    a = str(action_type or "").strip().lower()
    if a == "buy" or s in ("bullish", "positive"):
        return "positive"
    if a == "sell" or s in ("bearish", "negative"):
        return "negative"
    t = str(title or "").strip()
    if t:
        if _NEG_EVENT_RE.search(t):
            return "negative"
        if _POS_EVENT_RE.search(t):
            return "positive"
    return "neutral"


def classify_event_reality_check(
    *,
    sentiment: Optional[str] = None,
    action_type: Optional[str] = None,
    title: Optional[str] = None,
    change_pct: Optional[float] = None,
    r_vol: Optional[float] = None,
    distribution_score: Optional[float] = None,
    accumulation_score: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Compare a disclosure/event polarity with actual market price & liquidity reaction.
    Returns None when change_pct is unavailable.
    """
    chg = _safe_float(change_pct)
    if chg is None:
        return None

    rv = _safe_float(r_vol)
    rv_eff = rv if (rv is not None and rv > 0) else 1.0
    dist = _safe_float(distribution_score) or 0.0
    acc = _safe_float(accumulation_score) or 0.0
    polarity = infer_event_polarity(sentiment=sentiment, action_type=action_type, title=title)

    chg_str = f"{chg:+.2f}%"
    rv_part_ar = f" بحجم تداول {rv:.1f}x" if (rv is not None and rv > 0) else ""
    rv_part_en = f" on {rv:.1f}x vol" if (rv is not None and rv > 0) else ""

    # 1. Positive catalyst met with selling / distribution -> Sell the News
    if polarity == "positive" and (
        chg <= -1.0 or (chg <= 0.25 and (rv_eff >= 1.6 or dist >= 60.0))
    ):
        return {
            "code": "sell_the_news",
            "tone": "warning",
            "polarity": polarity,
            "label_ar": "بيع على الخبر (تصريف)",
            "label_en": "Sell the News",
            "change_pct": round(chg, 2),
            "r_vol": round(rv, 2) if rv is not None else None,
            "summary_ar": f"خبر إيجابي لكن السعر تحرك {chg_str}{rv_part_ar} — إشارة جني أرباح أو تصريف على الخبر.",
            "summary_en": f"Positive catalyst met with {chg_str}{rv_part_en} — potential sell-the-news distribution.",
        }

    # 2. Positive catalyst confirmed by price + liquidity
    if polarity == "positive" and chg >= 1.2 and (rv_eff >= 1.25 or acc >= 60.0) and dist < 60.0:
        return {
            "code": "institutional_confirmation",
            "tone": "positive",
            "polarity": polarity,
            "label_ar": "تأكيد شرائي مؤسسي",
            "label_en": "Institutional Confirmation",
            "change_pct": round(chg, 2),
            "r_vol": round(rv, 2) if rv is not None else None,
            "summary_ar": f"تفاعل إيجابي مؤكد ({chg_str}{rv_part_ar}) يدعم مصداقية الخبر.",
            "summary_en": f"Confirmed bullish reaction ({chg_str}{rv_part_en}) supporting the catalyst.",
        }

    # 3. Negative event confirmed by heavy selloff
    if polarity == "negative" and chg <= -1.2 and (rv_eff >= 1.2 or dist >= 55.0):
        return {
            "code": "confirmed_selloff",
            "tone": "negative",
            "polarity": polarity,
            "label_ar": "ضغط بيعي مؤكد",
            "label_en": "Confirmed Selloff",
            "change_pct": round(chg, 2),
            "r_vol": round(rv, 2) if rv is not None else None,
            "summary_ar": f"السوق يؤكد سلبية الخبر بهبوط {chg_str}{rv_part_ar}.",
            "summary_en": f"Market confirms negative catalyst ({chg_str}{rv_part_en}).",
        }

    # 4. Negative event absorbed positively (bad news priced in)
    if polarity == "negative" and chg >= 0.6:
        return {
            "code": "quiet_absorption",
            "tone": "positive",
            "polarity": polarity,
            "label_ar": "امتصاص للخبر السلبي",
            "label_en": "Bad-News Absorption",
            "change_pct": round(chg, 2),
            "r_vol": round(rv, 2) if rv is not None else None,
            "summary_ar": f"تماسك السهم ({chg_str}{rv_part_ar}) رغم سلبية الخبر يوحي بتسعيره مسبقاً.",
            "summary_en": f"Resilient move ({chg_str}{rv_part_en}) despite negative headline suggests priced-in news.",
        }

    # 5. Neutral/admin event with decisive breakout or selloff
    if chg >= 2.0 and rv_eff >= 1.5 and dist < 60.0:
        return {
            "code": "institutional_confirmation",
            "tone": "positive",
            "polarity": polarity,
            "label_ar": "تفاعل شرائي قوي",
            "label_en": "Strong Bullish Reaction",
            "change_pct": round(chg, 2),
            "r_vol": round(rv, 2) if rv is not None else None,
            "summary_ar": f"صعود قوي {chg_str}{rv_part_ar} تزامناً مع الإفصاح.",
            "summary_en": f"Strong upward reaction ({chg_str}{rv_part_en}) alongside the filing.",
        }

    if chg <= -2.0 and rv_eff >= 1.5:
        return {
            "code": "confirmed_selloff",
            "tone": "negative",
            "polarity": polarity,
            "label_ar": "ضغط بيعي قوي",
            "label_en": "Heavy Selling Reaction",
            "change_pct": round(chg, 2),
            "r_vol": round(rv, 2) if rv is not None else None,
            "summary_ar": f"هبوط حاد {chg_str}{rv_part_ar} تزامناً مع الإفصاح.",
            "summary_en": f"Sharp selloff ({chg_str}{rv_part_en}) alongside the filing.",
        }

    return {
        "code": "neutral_watch",
        "tone": "neutral",
        "polarity": polarity,
        "label_ar": "امتصاص هادئ / تسعير مسبق",
        "label_en": "Quiet / Priced-In",
        "change_pct": round(chg, 2),
        "r_vol": round(rv, 2) if rv is not None else None,
        "summary_ar": f"رد فعل محدود ({chg_str}{rv_part_ar}) — الخبر مسعّر مسبقاً أو بانتظار تأكيد السيولة.",
        "summary_en": f"Muted reaction ({chg_str}{rv_part_en}) — largely priced in or awaiting volume confirmation.",
    }


def _normalize_action_type(raw: str) -> str:
    s = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("bonus", "bonus_shares", "free_shares", "stock_dividend", "منحة", "مجاني", "أسهم_مجانية", "اسهم_مجانية"):
        return "bonus_shares"
    if s in ("split", "stock_split", "share_split", "تجزئة", "تقسيم"):
        return "stock_split"
    if s in ("dividend", "cash_dividend", "coupon", "كوبون", "توزيع", "توزيع_نقدي"):
        return "cash_dividend"
    if s in ("rights", "rights_issue", "subscription", "capital_increase", "اكتتاب", "حق_اكتتاب", "حقوق_اكتتاب"):
        return "rights_issue"
    return s


def calculate_corporate_action(
    *,
    action_type: str,
    pre_ex_price: float,
    shares: float = 1000.0,
    avg_buy_price: Optional[float] = None,
    ratio_new: Optional[float] = None,
    ratio_for: float = 1.0,
    dividend_per_share: Optional[float] = None,
    tax_rate_pct: Optional[float] = None,
    subscription_price: Optional[float] = None,
    exchange: str = "EGX",
    currency: str = "ج.م",
    symbol: Optional[str] = None,
    used_portfolio_position: bool = False,
) -> Dict[str, Any]:
    """
    Exact deterministic Ex-Date & portfolio cost-basis calculator for:
    - bonus_shares (e.g. ratio_new=1, ratio_for=4 => 1 free share per 4 held, +25% shares)
    - stock_split (e.g. ratio_new=5, ratio_for=1 => 5-for-1 split)
    - cash_dividend (dividend_per_share + tax_rate_pct + Yield on Cost)
    - rights_issue (TERP, theoretical right value, required subscription cash, new avg cost)
    """
    act = _normalize_action_type(action_type)
    ex_u = str(exchange or "EGX").strip().upper()
    sym_u = str(symbol or "").strip().upper() or None

    p0 = _safe_float(pre_ex_price)
    qty0 = _safe_float(shares)
    if p0 is None or p0 <= 0:
        return {"status": "error", "message": "يجب إدخال سعر السهم قبل تاريخ الحق (أكبر من صفر)."}
    if qty0 is None or qty0 <= 0:
        qty0 = 1000.0

    avg0 = _safe_float(avg_buy_price)
    if avg0 is None or avg0 <= 0:
        avg0 = p0

    dec = _price_decimals(p0)
    old_val = qty0 * p0
    old_cost = qty0 * avg0

    if act == "bonus_shares":
        rn = _safe_float(ratio_new)
        rf = _safe_float(ratio_for) or 1.0
        if rn is None or rn <= 0 or rf <= 0:
            return {"status": "error", "message": "يرجى تحديد نسبة الأسهم المجانية (مثلاً 1 سهم مجاني لكل 4 أسهم)."}
        bonus_ratio = rn / rf
        factor = 1.0 + bonus_ratio
        ex_price = p0 / factor
        new_shares = qty0 * factor
        added_shares = new_shares - qty0
        new_avg = avg0 / factor
        adj_pct = ((ex_price - p0) / p0) * 100.0
        return {
            "status": "success",
            "symbol": sym_u,
            "exchange": ex_u,
            "currency": currency,
            "action_type": "bonus_shares",
            "action_label_ar": "أسهم مجانية (توزيع منحة)",
            "used_portfolio_position": used_portfolio_position,
            "ratio_description_ar": f"{rn:g} سهم مجاني لكل {rf:g} أسهم (+{bonus_ratio * 100:.2f}%)",
            "pre_ex_price": round(p0, dec),
            "theoretical_ex_price": round(ex_price, dec),
            "price_adjustment_pct": round(adj_pct, 2),
            "old_shares": round(qty0, 2),
            "added_shares": round(added_shares, 2),
            "new_shares": round(new_shares, 2),
            "old_avg_cost": round(avg0, dec),
            "new_avg_cost": round(new_avg, dec),
            "old_market_value": round(old_val, 2),
            "new_market_value": round(new_shares * ex_price, 2),
            "summary_ar": (
                f"بعد توزيع {rn:g} سهم مجاني لكل {rf:g} أسهم: ينخفض السعر النظري من {p0:.{dec}f} إلى {ex_price:.{dec}f} {currency} ({adj_pct:.2f}%)، "
                f"وترتفع أسهمك من {qty0:,.0f} إلى {new_shares:,.2f} سهم، وينخفض متوسط تكلفتك من {avg0:.{dec}f} إلى {new_avg:.{dec}f} {currency} بنفس القيمة السوقية الإجمالية."
            ),
            "notes_ar": [
                "الانخفاض السعري يوم التداول بدون حق (Ex-Date) هو تعديل فني تلقائي وليس خسارة فعلية لأن عدد أسهمك يزيد بنفس النسبة.",
                "الكسور السهمية (إن وجدت) تُجبر لصالح صغار المساهمين وفق إعلان الشركة ومصر للمقاصة.",
            ],
        }

    if act == "stock_split":
        rn = _safe_float(ratio_new)
        rf = _safe_float(ratio_for) or 1.0
        if rn is None or rn <= 0 or rf <= 0:
            return {"status": "error", "message": "يرجى تحديد معامل التجزئة (مثلاً 5 إلى 1)."}
        factor = rn / rf
        if factor <= 0:
            return {"status": "error", "message": "معامل التجزئة غير صالح."}
        ex_price = p0 / factor
        new_shares = qty0 * factor
        added_shares = new_shares - qty0
        new_avg = avg0 / factor
        adj_pct = ((ex_price - p0) / p0) * 100.0
        is_reverse = factor < 1.0
        label_ar = "تجزئة عكسية (تجميع أسهم)" if is_reverse else "تجزئة السهم (تقسيم القيمة الاسمية)"
        return {
            "status": "success",
            "symbol": sym_u,
            "exchange": ex_u,
            "currency": currency,
            "action_type": "stock_split",
            "action_label_ar": label_ar,
            "used_portfolio_position": used_portfolio_position,
            "ratio_description_ar": f"{rn:g} إلى {rf:g} (معامل {factor:.4g}x)",
            "pre_ex_price": round(p0, dec),
            "theoretical_ex_price": round(ex_price, dec),
            "price_adjustment_pct": round(adj_pct, 2),
            "old_shares": round(qty0, 2),
            "added_shares": round(added_shares, 2),
            "new_shares": round(new_shares, 2),
            "old_avg_cost": round(avg0, dec),
            "new_avg_cost": round(new_avg, dec),
            "old_market_value": round(old_val, 2),
            "new_market_value": round(new_shares * ex_price, 2),
            "summary_ar": (
                f"بعد التجزئة ({rn:g} إلى {rf:g}): يتعدل السعر النظري من {p0:.{dec}f} إلى {ex_price:.{dec}f} {currency}، "
                f"ويتغير عدد أسهمك من {qty0:,.0f} إلى {new_shares:,.2f} سهم، ومتوسط تكلفتك من {avg0:.{dec}f} إلى {new_avg:.{dec}f} {currency}."
            ),
            "notes_ar": [
                "التجزئة تغيّر عدد الأسهم والسعر بنفس النسبة ولا تغيّر القيمة السوقية الإجمالية لمركزك أو حصتك في الشركة.",
            ],
        }

    if act == "cash_dividend":
        dps = _safe_float(dividend_per_share)
        if dps is None or dps <= 0:
            return {"status": "error", "message": "يرجى تحديد قيمة الكوبون النقدي للسهم الواحد (أكبر من صفر)."}
        default_tax = 5.0 if ex_u == "EGX" else 0.0
        tax_pct = _safe_float(tax_rate_pct)
        if tax_pct is None or tax_pct < 0 or tax_pct > 50:
            tax_pct = default_tax
        ex_price = max(0.0, p0 - dps)
        adj_pct = ((ex_price - p0) / p0) * 100.0
        gross_cash = qty0 * dps
        tax_amt = gross_cash * (tax_pct / 100.0)
        net_cash = gross_cash - tax_amt
        cur_yield_pct = (dps / p0) * 100.0
        net_cur_yield_pct = ((dps * (1.0 - tax_pct / 100.0)) / p0) * 100.0
        yoc_gross_pct = (dps / avg0) * 100.0
        yoc_net_pct = ((dps * (1.0 - tax_pct / 100.0)) / avg0) * 100.0
        effective_breakeven_after_div = max(0.0, avg0 - dps * (1.0 - tax_pct / 100.0))
        notes = [
            f"السعر النظري يوم التداول بدون كوبون (Ex-Date) ينخفض بقيمة الكوبون الإجمالي ({dps:.{dec}f} {currency}).",
        ]
        if ex_u == "EGX":
            notes.append(f"تم احتساب ضريبة التوزيعات النقدية بنسبة {tax_pct:g}% (النسبة القانونية للأسهم المقيدة بالبورصة المصرية 5%).")
        elif tax_pct == 0:
            notes.append("ضريبة التوزيعات الافتراضية 0% للمواطنين والمقيمين (قد تُطبق 5% لغير المقيمين في السوق السعودي).")
        return {
            "status": "success",
            "symbol": sym_u,
            "exchange": ex_u,
            "currency": currency,
            "action_type": "cash_dividend",
            "action_label_ar": "توزيع كوبون نقدي",
            "used_portfolio_position": used_portfolio_position,
            "dividend_per_share": round(dps, dec),
            "tax_rate_pct": round(tax_pct, 2),
            "pre_ex_price": round(p0, dec),
            "theoretical_ex_price": round(ex_price, dec),
            "price_adjustment_pct": round(adj_pct, 2),
            "old_shares": round(qty0, 2),
            "new_shares": round(qty0, 2),
            "added_shares": 0.0,
            "old_avg_cost": round(avg0, dec),
            "effective_cost_after_dividend": round(effective_breakeven_after_div, dec),
            "gross_dividend": round(gross_cash, 2),
            "tax_amount": round(tax_amt, 2),
            "net_dividend": round(net_cash, 2),
            "dividend_yield_pct": round(cur_yield_pct, 2),
            "net_dividend_yield_pct": round(net_cur_yield_pct, 2),
            "yield_on_cost_pct": round(yoc_gross_pct, 2),
            "net_yield_on_cost_pct": round(yoc_net_pct, 2),
            "old_market_value": round(old_val, 2),
            "new_market_value": round(qty0 * ex_price, 2),
            "summary_ar": (
                f"كوبون {dps:.{dec}f} {currency}/سهم على {qty0:,.0f} سهم: إجمالي {gross_cash:,.2f} {currency}، "
                f"والصافي بعد ضريبة {tax_pct:g}% هو {net_cash:,.2f} {currency} (عائد صافي على متوسط شرائك {yoc_net_pct:.2f}%). "
                f"السعر النظري بعد الحق: {ex_price:.{dec}f} {currency}."
            ),
            "notes_ar": notes,
        }

    if act == "rights_issue":
        rn = _safe_float(ratio_new)
        rf = _safe_float(ratio_for) or 1.0
        sub_p = _safe_float(subscription_price)
        if rn is None or rn <= 0 or rf <= 0:
            return {"status": "error", "message": "يرجى تحديد نسبة الاكتتاب (مثلاً 1 سهم جديد لكل 2 سهم قديم)."}
        if sub_p is None or sub_p < 0:
            return {"status": "error", "message": "يرجى تحديد سعر الاكتتاب للسهم الجديد."}
        terp = (p0 * rf + sub_p * rn) / (rf + rn)
        right_value = max(0.0, p0 - terp)
        added_shares = qty0 * (rn / rf)
        new_shares = qty0 + added_shares
        sub_cash = added_shares * sub_p
        total_cost_after = old_cost + sub_cash
        new_avg = total_cost_after / new_shares if new_shares > 0 else avg0
        adj_pct = ((terp - p0) / p0) * 100.0
        return {
            "status": "success",
            "symbol": sym_u,
            "exchange": ex_u,
            "currency": currency,
            "action_type": "rights_issue",
            "action_label_ar": "زيادة رأس مال بحقوق اكتتاب",
            "used_portfolio_position": used_portfolio_position,
            "ratio_description_ar": f"{rn:g} سهم جديد لكل {rf:g} سهم بسعر اكتتاب {sub_p:.{dec}f} {currency}",
            "subscription_price": round(sub_p, dec),
            "pre_ex_price": round(p0, dec),
            "theoretical_ex_price": round(terp, dec),
            "theoretical_right_value": round(right_value, dec),
            "price_adjustment_pct": round(adj_pct, 2),
            "old_shares": round(qty0, 2),
            "added_shares": round(added_shares, 2),
            "new_shares": round(new_shares, 2),
            "subscription_cost": round(sub_cash, 2),
            "old_avg_cost": round(avg0, dec),
            "new_avg_cost": round(new_avg, dec),
            "old_market_value": round(old_val, 2),
            "new_market_value": round(new_shares * terp, 2),
            "summary_ar": (
                f"الاكتتاب بنسبة {rn:g} لكل {rf:g} بسعر {sub_p:.{dec}f} {currency}: السعر النظري بعد الحق (TERP) هو {terp:.{dec}f} {currency}، "
                f"والقيمة النظرية لحق الاكتتاب {right_value:.{dec}f} {currency}. "
                f"مشاركتك الكاملة تتطلب {sub_cash:,.2f} {currency} لشراء {added_shares:,.2f} سهم جديد ليصبح متوسطك {new_avg:.{dec}f} {currency}."
            ),
            "notes_ar": [
                "عدم الاكتتاب وعدم بيع حق الاكتتاب قبل انتهاء فترته يؤدي إلى تخفيف (Dilution) فعلي في قيمة حصتك.",
                "إذا لم ترغب في ضخ سيولة إضافية، يمكنك بيع حق الاكتتاب في السوق أثناء فترة تداوله لتعويض فارق السعر.",
            ],
        }

    return {
        "status": "error",
        "message": "نوع الإجراء غير مدعوم. الأنواع المدعومة: bonus_shares، stock_split، cash_dividend، rights_issue.",
    }
