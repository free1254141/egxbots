"""
api/agentic_chat/output_guard.py
Deterministic post-generation output guardrail for ARTORO Agentic Chat (<2ms, zero LLM/DB calls).

Verifies model-synthesized replies against actual tool payloads before streaming completion / caching:
1. Enforces stale-quote warnings when `data_is_stale: true` was returned by tools.
2. Flags numeric currency mismatches (e.g. quoting ج.م for a $, SAR, QAR, or AED stock).
3. Blocks shared caching when any fetched stock had missing quote / suggested matches.
4. Sanitizes leaked internal Python tool identifiers from user-facing prose.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

_STALE_MENTION_HINTS = ("موقوف", "قديم", "غير محدث", "غير محدّث", "تنبيه شفافية")
_NUMERIC_EGP_RE = re.compile(r"\d[\d.,]*\s*ج\.م")

_TOOL_NAME_LABELS: Dict[str, str] = {
    "get_stock_levels": "مستويات الدعم والمقاومة",
    "get_accumulation_stocks": "رادار التجميع المؤسسي",
    "get_technical_scan": "المسح الفني",
    "get_sharia_cleanser": "حاسبة التوافق الشرعي والزكاة",
    "get_fair_value": "محرك القيمة العادلة",
    "get_price_traps": "كاشف المصائد السعرية",
    "get_disclosures": "رادار الإفصاحات",
    "get_dividends": "تقويم التوزيعات",
    "manage_portfolio": "إدارة المحفظة",
    "optimize_portfolio": "محرك التحسين الرياضي للمحفظة",
    "calculate_position": "حاسبة المراكز والتبريد الذكي",
    "manage_automations": "إدارة الاستشارات المجدولة",
    "search_stocks": "البحث في قاعدة البيانات",
    "get_stock": "بيانات السهم",
}
_ORDERED_TOOL_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    (name, re.compile(rf"`?\b{re.escape(name)}\b`?"), label)
    for name, label in sorted(_TOOL_NAME_LABELS.items(), key=lambda kv: len(kv[0]), reverse=True)
]

_LEAKED_FIELD_EXPR_RE = re.compile(
    r"\s*\(?`?(?:is_sharia_compliant|data_is_stale|support_1_is_distant|has_active_recommendation|distribution_score|dist_score|acc_score|consecutive)`?\s*[:=]\s*(?:true|false|null|\d+(?:\.\d+)?)\s*`?\)?",
    re.IGNORECASE,
)
_LEAKED_FIELD_LABELS: Dict[str, str] = {
    "has_active_recommendation": "التوصية المفتوحة",
    "calibrated_target_prob_pct": "احتمال الصعود المعاير",
    "prob_hit_target_first_pct": "احتمال بلوغ الهدف أولاً",
    "prob_hit_stop_first_pct": "احتمال كسر الوقف أولاً",
    "portfolio_rotation_matrix": "مصفوفة تدوير المحفظة",
    "exit_priority_symbols": "أسهم أولوية الخروج",
    "trim_excess_symbols": "أسهم تخفيف التركّز",
    "hold_core_symbols": "أسهم الاحتفاظ الأساسي",
    "hold_watch_symbols": "أسهم المراقبة",
    "do_not_buy_symbols": "الأسهم الممنوعة من الشراء",
    "REDUCE_CONCENTRATION": "تخفيف التركّز",
    "strong_accumulation": "تجميع قوي",
    "strong_distribution": "تصريف قوي",
    "weak_accumulation": "تجميع ضعيف",
    "EXIT_PRIORITY": "أولوية خروج",
    "SELL_PRIORITY": "أولوية بيع",
    "TRIM_EXCESS": "تخفيف التركّز",
    "HOLD_WATCH": "مراقبة دون تعزيز",
    "HOLD_CORE": "احتفاظ أساسي",
    "support_1_is_distant": "بعد الدعم الهيكلي",
    "fundamental_diagnosis": "التشخيص المالي",
    "quant_intelligence": "التحليل الكمي ومحاكاة مونت كارلو",
    "is_sharia_compliant": "التوافق الشرعي",
    "consecutive_acc_days": "أيام التجميع المتتالية",
    "value_trap_warning": "تحذير فخ القيمة",
    "distribution_score": "درجة التصريف المؤسسي",
    "max_diversification": "أقصى تنويع ممكن",
    "weak_distribution": "تصريف ضعيف",
    "upcoming_dividend": "التوزيع النقدي القادم",
    "upcoming_events": "الأحداث القادمة ومواعيد النتائج",
    "smart_dca_plan": "خطة التبريد الذكي",
    "king_ai_score": "تقييم الذكاء الاصطناعي",
    "data_is_stale": "قدم البيانات",
    "setup_regime": "التصنيف الكمي للإعداد",
    "brier_score": "دقة المعايرة التاريخية",
    "risk_parity": "توزيع متكافئ للمخاطرة",
    "consecutive": "أيام التتالي",
    "dist_score": "درجة التصريف",
    "fund_score": "التقييم المالي",
    "acc_score": "درجة التجميع",
    "vol_ratio": "السيولة النسبية",
    "min_risk": "أقل مخاطرة",
    "r_vol": "السيولة النسبية",
}
_REDUNDANT_PAREN_FIELD_RE = re.compile(
    r"\s*\(\s*`?("
    + "|".join(sorted((re.escape(k) for k in _LEAKED_FIELD_LABELS), key=len, reverse=True))
    + r")`?\s*\)"
)
_ORDERED_FIELD_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    (name, re.compile(rf"`?\b{re.escape(name)}\b`?"), label)
    for name, label in sorted(_LEAKED_FIELD_LABELS.items(), key=lambda kv: len(kv[0]), reverse=True)
]
_DUP_LIQUIDITY_RE = re.compile(r"(?:السيولة(?:\s+النسبية)?\s+){1,2}(السيولة\s+النسبية)`?")
_SHARIA_TAX_TYPO_RE = re.compile(r"الضريبة\s+الشرعية")
_EX_DATE_INVERTED_RE = re.compile(
    r"(?:"
    r"البيع\s+(?:هنا|يوم[^\n]{0,25}Ex-?Date)\s*[=:]\s*بدون\s+كوبون"
    r"|(?:لو\s+بعت|البيع|أي\s+شراء\s+أو\s+بيع|عند\s+البيع)[^\n.]{0,75}(?:يوم\s+[^\n.]{0,30}|في\s+هذا\s+اليوم)[^\n.]{0,55}(?:مش\s+هتستحق|لا\s+تستحق|لا\s+يمنحك|بدون\s+كوبون|لن\s+تستحق)"
    r")",
    re.IGNORECASE,
)
_EX_DATE_CORRECTION_BANNER = (
    "> ⚠️ **تصحيح قاعدة الـ Ex-Date الرسمية:** يوم الـ `Ex-Date` هو أول جلسة يتداول فيها السهم **بدون كوبون للمشتري الجديد فقط**. "
    "أما إذا كنت تمتلك الأسهم عند إغلاق الجلسة السابقة للـ `Ex-Date` (`Cum-Date`)، **فإنك تستحق الكوبون كاملاً حتى لو بعت أسهمك في يوم الـ `Ex-Date` نفسه أو بعده.**"
)

_AUTOMATION_NO_QUOTA_LINE_RE = re.compile(
    r"^[^\n]*(?:الأتمتة\s+المجدولة|الاتمتة\s+المجدولة|الاتوميشن|Scheduled\s+Automations)[^\n]*"
    r"(?:مش\s+بتاكل|لا\s+تأكل|لا\s+تاكل|لا\s+تستهلك|مش\s+بتستهلك|مش\s+بتتحسب|لا\s+تحتسب|لا\s+تُحتسب|لا\s+تخصم|مش\s+بتخصم|بدون\s+استهلاك)[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
_AUTOMATION_QUOTA_CORRECTION_LINE = (
    "- **الأتمتة المجدولة (Scheduled Automations)** — ⚠️ **تستهلك من الكوتة** "
    "(كل تقرير مجدول يتنفذ تلقائياً يخصم رسالة واحدة `1` من كوتة الشات الشهرية الموحدة)."
)


_BUY_INCREASE_CUES_RE = re.compile(
    r"(?:زيادة|تعزيز|شراء|زود|تزود|أضف|إضافة|التعزيز|الزيادة|ادخل|دخول|شراء\s+إضافي)"
)
_EXIT_OR_NEGATION_CUES_RE = re.compile(
    r"(?:لا\s+تزيد|لا\s+ينصح|لا\s+أنصح|تجنب|ممنوع|مستبعد|مستبعدة|بيع|تصفية|تخارج|إلغاء|خروج|"
    r"قبل\s+بيع|عوضاً\s+عن|بدلاً\s+من|عدم\s+الشراء|عدم\s+الزيادة|لا\s+تشتري|غير\s+مناسب|"
    r"دون\s+زيادة|بدون\s+زيادة|بلا\s+زيادة|دون\s+تعزيز|بدون\s+تعزيز|بلا\s+تعزيز|"
    r"دون\s+إضافة|بدون\s+إضافة|لا\s+إضافة|لا\s+مضاعفة|فلا\s+مضاعفة|"
    r"سيخرج|ستخرج|يخرج|تخرج|يبقى\s+دون|لا\s+تشتر|لا\s+تعزز|لا\s+تزود)"
)


def _collect_excluded_portfolio_symbols(tool_payloads: List[Dict[str, Any]]) -> Dict[str, str]:
    """Collect symbols explicitly excluded from buying by optimizer or deterministic rotation matrix."""
    excluded: Dict[str, str] = {}

    def _visit(node: Any, depth: int) -> None:
        if depth > 4:
            return
        if isinstance(node, list):
            for item in node:
                _visit(item, depth + 1)
            return
        if not isinstance(node, dict):
            return

        if isinstance(node.get("excludedFromBuying"), list):
            for item in node["excludedFromBuying"]:
                if isinstance(item, dict) and item.get("symbol"):
                    s = str(item["symbol"]).strip().upper()
                    excluded.setdefault(s, str(item.get("reason") or "مستبعد من الشراء"))

        rot = node.get("portfolio_rotation_matrix")
        if isinstance(rot, dict) and isinstance(rot.get("exit_priority_symbols"), list):
            for raw_s in rot["exit_priority_symbols"]:
                if isinstance(raw_s, str) and raw_s.strip():
                    excluded.setdefault(raw_s.strip().upper(), "مصنّف كمستبعد/تصفية أولوية في مصفوفة المحفظة")

        if isinstance(node.get("positions"), list):
            for p in node["positions"]:
                if isinstance(p, dict) and p.get("symbol"):
                    if p.get("rotation_action") == "EXIT_PRIORITY" or (p.get("forbidden_to_buy") and (p.get("is_loss_making") or p.get("is_illiquid") or p.get("is_negative_equity"))):
                        excluded.setdefault(
                            str(p["symbol"]).strip().upper(),
                            str(p.get("rotation_reason_ar") or "شركة خاسرة أو سيولة منعدمة — ممنوع التعزيز"),
                        )

        for v in node.values():
            if isinstance(v, (dict, list)):
                _visit(v, depth + 1)

    for payload in tool_payloads or []:
        _visit(payload, 0)
    return excluded


def _collect_ground_truth(
    tool_payloads: List[Dict[str, Any]],
) -> Tuple[List[Tuple[str, str, str]], Set[Tuple[str, str]], bool]:
    stale_stocks: List[Tuple[str, str, str]] = []
    seen_stale_syms: Set[str] = set()
    fetched_currencies: Set[Tuple[str, str]] = set()
    missing_data = False

    def _visit(node: Any, depth: int) -> None:
        nonlocal missing_data
        if depth > 4:
            return
        if isinstance(node, list):
            for item in node:
                _visit(item, depth + 1)
            return
        if not isinstance(node, dict):
            return

        if node.get("suggested_matches"):
            missing_data = True

        sym_raw = node.get("symbol")
        if isinstance(sym_raw, str) and sym_raw.strip():
            sym = sym_raw.strip().upper()
            if node.get("data_is_stale") is True and node.get("stale_data_warning"):
                if sym not in seen_stale_syms:
                    seen_stale_syms.add(sym)
                    stale_stocks.append((sym, str(node.get("date") or "")[:10], str(node["stale_data_warning"])))

            curr = str(node.get("currency") or "").strip()
            has_price_context = (
                node.get("close") is not None
                or node.get("current_price") is not None
                or node.get("fair_value") is not None
                or node.get("support_1") is not None
                or node.get("market_value") is not None
            )
            if curr and has_price_context:
                fetched_currencies.add((sym, curr))

        if isinstance(node.get("stocks"), list):
            for s in node["stocks"]:
                if isinstance(s, dict) and s.get("close") is None:
                    missing_data = True

        for v in node.values():
            if isinstance(v, (dict, list)):
                _visit(v, depth + 1)

    for payload in tool_payloads or []:
        _visit(payload, 0)

    return stale_stocks, fetched_currencies, missing_data


_DISCLAIMER_LINE_RE = re.compile(
    r"ليس(?:ت)?\s+(?:نصيحة|توصية)\s+استثمارية",
    re.IGNORECASE,
)


def _dedupe_trailing_disclaimers(text: str) -> str:
    """Collapse consecutive trailing investment disclaimer footers down to a single clean footer."""
    lines = text.splitlines()
    div_re = re.compile(r"^\s*[-_*]{3,}\s*$")
    content_idx = [
        i for i, ln in enumerate(lines)
        if ln.strip() and not div_re.match(ln)
    ]
    if len(content_idx) < 2:
        return text
    last_i = content_idx[-1]
    prev_i = content_idx[-2]
    if _DISCLAIMER_LINE_RE.search(lines[last_i]) and _DISCLAIMER_LINE_RE.search(lines[prev_i]):
        # Keep the richer disclaimer line (prefer the one without bare markdown italics-only short text)
        keep_last = len(lines[last_i].strip()) >= len(lines[prev_i].strip())
        drop_i = prev_i if keep_last else last_i
        del lines[drop_i]
        cleaned: List[str] = []
        prev_nonempty_is_div = False
        for ln in lines:
            is_div = bool(div_re.match(ln))
            if is_div and prev_nonempty_is_div:
                continue
            cleaned.append(ln)
            if ln.strip():
                prev_nonempty_is_div = is_div
        while cleaned and (not cleaned[-1].strip() or div_re.match(cleaned[-1])):
            cleaned.pop()
        return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()
    return text


def _extract_single_stock_truth(
    tool_payloads: List[Dict[str, Any]],
) -> Tuple[Optional[Tuple[str, Dict[str, Any]]], bool, bool]:
    """Collect authoritative per-stock truth and dividend context from tool payloads."""
    stock_records: Dict[str, Dict[str, Any]] = {}
    checked_dividends = False
    has_any_upcoming_dividend = False

    def _visit(node: Any, depth: int) -> None:
        nonlocal checked_dividends, has_any_upcoming_dividend
        if depth > 4:
            return
        if isinstance(node, list):
            for item in node:
                _visit(item, depth + 1)
            return
        if not isinstance(node, dict):
            return

        if "upcoming_dividend" in node and isinstance(node.get("upcoming_dividend"), dict) and node["upcoming_dividend"]:
            checked_dividends = True
            has_any_upcoming_dividend = True
        if "upcoming_dividends" in node:
            checked_dividends = True
            if isinstance(node.get("upcoming_dividends"), list) and len(node["upcoming_dividends"]) > 0:
                has_any_upcoming_dividend = True
        if "dividends" in node:
            checked_dividends = True
            if isinstance(node.get("dividends"), list):
                for div_row in node["dividends"]:
                    if isinstance(div_row, dict) and (
                        div_row.get("is_upcoming")
                        or div_row.get("upcoming")
                        or div_row.get("status") in ("upcoming", "pending_pay")
                    ):
                        has_any_upcoming_dividend = True

        sym_raw = node.get("symbol")
        if isinstance(sym_raw, str) and sym_raw.strip():
            sym = sym_raw.strip().upper()
            close_v = node.get("close") if node.get("close") is not None else node.get("current_price")
            has_core = (
                close_v is not None
                or node.get("fair_value") is not None
                or isinstance(node.get("quant_intelligence"), dict)
            )
            if has_core:
                if "payout_ratio_pct" in node or "dividend_yield" in node:
                    checked_dividends = True
                rec = stock_records.setdefault(sym, {})
                if close_v is not None and rec.get("close") is None:
                    try:
                        c_f = float(close_v)
                        if c_f > 0:
                            rec["close"] = c_f
                    except (TypeError, ValueError):
                        pass
                if node.get("date") and not rec.get("date"):
                    rec["date"] = str(node["date"])[:10]
                if node.get("currency") and not rec.get("currency"):
                    rec["currency"] = str(node["currency"]).strip()
                up_raw = node.get("valuation_upside_pct") if node.get("valuation_upside_pct") is not None else node.get("upside_pct")
                if up_raw is not None and rec.get("upside") is None:
                    try:
                        rec["upside"] = float(up_raw)
                    except (TypeError, ValueError):
                        pass
                if node.get("fair_value") is not None and rec.get("fair_value") is None:
                    try:
                        fv_v = float(node["fair_value"])
                        if fv_v > 0:
                            rec["fair_value"] = fv_v
                    except (TypeError, ValueError):
                        pass
                for sl_k in ("stop_loss", "tactical_stop_loss"):
                    if node.get(sl_k) is not None:
                        try:
                            sl_v = float(node[sl_k])
                            if sl_v > 0:
                                rec.setdefault("valid_stops", []).append(sl_v)
                        except (TypeError, ValueError):
                            pass
                for r_k in ("resistance_1", "resistance_2"):
                    if node.get(r_k) is not None:
                        try:
                            r_v = float(node[r_k])
                            if r_v > 0:
                                rec.setdefault("valid_resistances", []).append(r_v)
                        except (TypeError, ValueError):
                            pass
                qi = node.get("quant_intelligence")
                if isinstance(qi, dict) and isinstance(qi.get("monte_carlo"), dict):
                    mc = qi["monte_carlo"]
                    if mc.get("stop_barrier") is not None:
                        try:
                            sb_v = float(mc["stop_barrier"])
                            if sb_v > 0:
                                rec.setdefault("valid_stops", []).append(sb_v)
                        except (TypeError, ValueError):
                            pass
                    if mc.get("target_barrier") is not None:
                        try:
                            tb_v = float(mc["target_barrier"])
                            if tb_v > 0:
                                rec.setdefault("valid_resistances", []).append(tb_v)
                        except (TypeError, ValueError):
                            pass
                    if mc.get("prob_hit_target_first_pct") is not None and rec.get("mc_t") is None:
                        try:
                            rec["mc_t"] = float(mc["prob_hit_target_first_pct"])
                            rec["mc_s"] = float(mc.get("prob_hit_stop_first_pct") or 0.0)
                        except (TypeError, ValueError):
                            pass

        for v in node.values():
            if isinstance(v, (dict, list)):
                _visit(v, depth + 1)

    for payload in tool_payloads or []:
        _visit(payload, 0)

    single = next(iter(stock_records.items())) if len(stock_records) == 1 else None
    return single, checked_dividends, has_any_upcoming_dividend


_STATED_CLOSE_RE = re.compile(
    r"(?:^|\n|\|)\s*(?:\*{0,2}(?:السعر\s+الأخير|السعر\s+الحالي|آخر\s+إغلاق(?:\s+متاح)?)\*{0,2}\s*:?\s*\|?\s*\*{0,2}\s*)(\d[\d,]*(?:\.\d+)?)"
)
_STATED_FV_RE = re.compile(
    r"(?:\*{0,2}(?:القيمة\s+العادلة|السعر\s+العادل)(?:\s+(?:المرجحة|المرجّحة|الأساسية|التقديرية|المحسوبة))?(?:\s*\((?!.*جراهام)[^)\n]{1,28}\))?\*{0,2}\s*:?\s*\|?\s*(?:≈\s*)?\*{0,2}\s*)(\d[\d,]*(?:\.\d+)?)"
)
_STATED_STOP_ROW_RE = re.compile(
    r"(?:^|\n)\s*\|\s*\*{0,2}(?:وقف\s+الخسارة[^\n|]{0,30})\*{0,2}\s*\|\s*\*{0,2}(\d[\d,]*(?:\.\d+)?)"
)
_STATED_RES1_ROW_RE = re.compile(
    r"(?:^|\n)\s*\|\s*\*{0,2}(?:المقاومة\s+الأولى[^\n|]{0,25})\*{0,2}\s*\|\s*\*{0,2}(\d[\d,]*(?:\.\d+)?)"
)
_CHEAP_VALUATION_CUE_RE = re.compile(
    r"(?:سهم\s+رخيص|رخيص\s+جداً|فرصة\s+قيمة\s+بخصم|أقل\s+من\s+قيمته\s+العادلة|تحت\s+القيمة\s+العادلة)"
)
_CHEAP_NEGATION_RE = re.compile(
    r"(?:ليس|ليست|غير|لا\s+يُعد|أعلى\s+من|فوق\s+القيمة|مقارنة\s+ب)"
)
_EXPENSIVE_VALUATION_CUE_RE = re.compile(
    r"(?:سهم\s+متضخم\s+سعرياً|أعلى\s+من\s+قيمته\s+العادلة|فوق\s+القيمة\s+العادلة\s+بشكل\s+كبير)"
)
_EXPENSIVE_NEGATION_RE = re.compile(
    r"(?:ليس|ليست|غير|لا\s+يُعد|أقل\s+من|تحت\s+القيمة)"
)
_PHANTOM_DIV_RE = re.compile(r"🎁\s*كوبون\s+قادم\s*:")
_MC_PROB_INVERSION_RE = re.compile(
    r"احتمال\s+(?:الصعود|بلوغ\s+الهدف)[^\n]{0,40}(?:أعلى|أكبر)\s+من\s+(?:كسر\s+الوقف|الهبوط)"
)


def verify_and_guard_reply(
    reply: str,
    tool_payloads: List[Dict[str, Any]],
    market: str = "EGX",
) -> Dict[str, Any]:
    """Verify and enforce deterministic factual guardrails on the generated reply."""
    guarded = str(reply or "")
    warnings: List[str] = []
    block_cache = False
    prepended_warning = False

    if not guarded:
        return {
            "reply": guarded,
            "warnings": warnings,
            "block_cache": False,
            "prepended_warning": False,
        }

    stale_stocks, fetched_currencies, missing_data = _collect_ground_truth(tool_payloads)

    # Check A: Stale Data Enforcement
    head = guarded[:500]
    prepends: List[str] = []
    for sym, dt_str, warn_txt in stale_stocks:
        date_present = bool(dt_str and dt_str in guarded)
        hint_present = any(h in head for h in _STALE_MENTION_HINTS)
        if not date_present and not hint_present:
            prepends.append(f"> {warn_txt}")
            warnings.append(f"stale_warning_injected:{sym}")
            prepended_warning = True
            block_cache = True
    if prepends:
        guarded = "\n".join(prepends) + "\n\n" + guarded

    # Check B: Currency Consistency Guard
    distinct_currs = {curr for _, curr in fetched_currencies if curr}
    if len(distinct_currs) == 1:
        expected_curr = next(iter(distinct_currs))
        if expected_curr != "ج.م" and _NUMERIC_EGP_RE.search(guarded):
            warnings.append(f"currency_mismatch:expected_{expected_curr}_found_EGP")
            block_cache = True

    # Check C: Missing Data Poison Guard
    if missing_data:
        warnings.append("missing_stock_data")
        block_cache = True

    # Check D: Internal Tool-Name & Schema Field Leak Sanitizer
    for name, pat, label in _ORDERED_TOOL_PATTERNS:
        if pat.search(guarded):
            guarded = pat.sub(label, guarded)
            warnings.append(f"tool_name_leaked:{name}")

    if _LEAKED_FIELD_EXPR_RE.search(guarded):
        guarded = _LEAKED_FIELD_EXPR_RE.sub("", guarded)
        warnings.append("internal_field_leaked")

    for paren_match in list(_REDUNDANT_PAREN_FIELD_RE.finditer(guarded)):
        fname = paren_match.group(1)
        warnings.append(f"internal_field_leaked:{fname}")
    if _REDUNDANT_PAREN_FIELD_RE.search(guarded):
        guarded = _REDUNDANT_PAREN_FIELD_RE.sub("", guarded)

    for fname, fpat, flabel in _ORDERED_FIELD_PATTERNS:
        if fpat.search(guarded):
            guarded = fpat.sub(flabel, guarded)
            warnings.append(f"internal_field_leaked:{fname}")

    if _DUP_LIQUIDITY_RE.search(guarded):
        guarded = _DUP_LIQUIDITY_RE.sub(r"\1", guarded)
    guarded = re.sub(r"`\s*السيولة النسبية\s*`?", "السيولة النسبية", guarded)

    if _SHARIA_TAX_TYPO_RE.search(guarded):
        guarded = _SHARIA_TAX_TYPO_RE.sub("الضوابط الشرعية", guarded)
        warnings.append("sharia_typo_fixed")

    has_div_context = any(
        k in guarded for k in ("Ex-Date", "ex_date", "تاريخ التداول بدون كوبون", "الكوبون")
    )
    if has_div_context and _EX_DATE_INVERTED_RE.search(guarded):
        guarded = re.sub(
            r"(?:←|->)?\s*البيع\s+(?:هنا|يوم[^\n]{0,25}Ex-?Date)\s*[=:]\s*بدون\s+كوبون",
            "← الشراء هنا = بدون كوبون (أما من امتلك السهم بإغلاق الجلسة السابقة وباع هنا فيستحق الكوبون)",
            guarded,
            flags=re.IGNORECASE,
        )
        if _EX_DATE_CORRECTION_BANNER not in guarded:
            guarded = f"{_EX_DATE_CORRECTION_BANNER}\n\n{guarded}"
        warnings.append("ex_date_rule_inverted_corrected")
        block_cache = True

    if _AUTOMATION_NO_QUOTA_LINE_RE.search(guarded):
        guarded = _AUTOMATION_NO_QUOTA_LINE_RE.sub(_AUTOMATION_QUOTA_CORRECTION_LINE, guarded)
        warnings.append("automation_quota_misstatement_fixed")
        block_cache = True

    # Check E: Portfolio Contradiction Guard (block recommending BUY/increase on excluded/loss-making stocks)
    excluded_syms = _collect_excluded_portfolio_symbols(tool_payloads)
    if excluded_syms:
        conflict_syms: List[str] = []
        for raw_line in guarded.splitlines():
            clean_line = raw_line.replace("*", "").replace("`", "")
            if not _BUY_INCREASE_CUES_RE.search(clean_line):
                continue
            if _EXIT_OR_NEGATION_CUES_RE.search(clean_line):
                continue
            for sym in excluded_syms:
                if re.search(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", clean_line):
                    if sym not in conflict_syms:
                        conflict_syms.append(sym)
        if conflict_syms:
            for sym in conflict_syms:
                warnings.append(f"excluded_stock_buy_conflict:{sym}")
            block_cache = True
            prepended_warning = True
            banner = (
                f"> ⚠️ **تنبيه اتساق المحفظة التلقائي:** الأسهم التالية (**{', '.join(conflict_syms)}**) "
                "مصنّفة برمجياً كمراكز مستبعدة من الشراء أو التوسع لوجود خسائر صافية أو حقوق ملكية سالبة أو سيولة منعدمة — "
                "تجاهل أي إشارة تعزيز لها وأولِ الأولوية للتصفية لصالح الأسهم السليمة مالياً."
            )
            if "تنبيه اتساق المحفظة التلقائي" not in guarded:
                guarded = f"{banner}\n\n{guarded}"

    # Check F: Deterministic Single-Stock Close, Valuation, Dividend & Monte Carlo Fact-Checker
    single_truth, checked_dividends, has_any_upcoming_dividend = _extract_single_stock_truth(tool_payloads)
    if single_truth is not None:
        sym_f, rec_f = single_truth
        actual_close = rec_f.get("close")
        if actual_close and actual_close > 0:
            m_close = _STATED_CLOSE_RE.search(guarded)
            if m_close:
                try:
                    stated_close = float(m_close.group(1).replace(",", ""))
                    if abs(stated_close - actual_close) / actual_close > 0.025:
                        warnings.append(f"price_hallucination:{sym_f}:stated={stated_close}_actual={actual_close}")
                        block_cache = True
                        prepended_warning = True
                        curr_f = rec_f.get("currency") or "ج.م"
                        dt_f = rec_f.get("date") or "أحدث إغلاق"
                        price_banner = (
                            f"> ⚠️ **تدقيق السعر الحتمي ({sym_f}):** السعر الموثق في آخر جلسة ({dt_f}) هو "
                            f"**{actual_close} {curr_f}** — يُعتمد هذا الرقم على أي سعر مخالف في النص."
                        )
                        if "تدقيق السعر الحتمي" not in guarded:
                            guarded = f"{price_banner}\n\n{guarded}"
                except (TypeError, ValueError):
                    pass

        upside_f = rec_f.get("upside")
        if upside_f is not None:
            dir_conflict = False
            if upside_f <= -15.0:
                for raw_ln in guarded.splitlines():
                    cl_ln = raw_ln.replace("*", "").replace("`", "")
                    if _CHEAP_VALUATION_CUE_RE.search(cl_ln) and not _CHEAP_NEGATION_RE.search(cl_ln):
                        dir_conflict = True
                        break
            elif upside_f >= 20.0:
                for raw_ln in guarded.splitlines():
                    cl_ln = raw_ln.replace("*", "").replace("`", "")
                    if _EXPENSIVE_VALUATION_CUE_RE.search(cl_ln) and not _EXPENSIVE_NEGATION_RE.search(cl_ln):
                        dir_conflict = True
                        break
            if dir_conflict:
                warnings.append(f"valuation_direction_contradiction:{sym_f}")
                block_cache = True
                prepended_warning = True
                val_banner = (
                    f"> ⚠️ **تدقيق التقييم الحتمي ({sym_f}):** السهم يتداول حالياً **أعلى من قيمته العادلة** بنحو "
                    f"`{abs(upside_f):.1f}%` وفق بيانات الأداة — تجاهل أي وصف معاكس له كسهم رخيص."
                    if upside_f < 0
                    else f"> ⚠️ **تدقيق التقييم الحتمي ({sym_f}):** السهم يتداول حالياً **أقل من قيمته العادلة** بنحو "
                    f"`+{upside_f:.1f}%` وفق بيانات الأداة."
                )
                if "تدقيق التقييم الحتمي" not in guarded:
                    guarded = f"{val_banner}\n\n{guarded}"

        mc_t_f = rec_f.get("mc_t")
        mc_s_f = rec_f.get("mc_s")
        if mc_t_f is not None and mc_s_f is not None and mc_t_f <= 15.0 and mc_s_f >= 50.0:
            if _MC_PROB_INVERSION_RE.search(guarded.replace("*", "")):
                warnings.append(f"mc_probability_inversion:{sym_f}")
                block_cache = True
                prepended_warning = True
                mc_banner = (
                    f"> ⚠️ **تدقيق مونت كارلو الحتمي ({sym_f}):** احتمال كسر الوقف (`{mc_s_f:.1f}%`) **أعلى** من "
                    f"احتمال بلوغ الهدف (`{mc_t_f:.1f}%`) خلال 10 جلسات."
                )
                if "تدقيق مونت كارلو الحتمي" not in guarded:
                    guarded = f"{mc_banner}\n\n{guarded}"

        actual_fv = rec_f.get("fair_value")
        if actual_fv and actual_fv > 0:
            m_fv = _STATED_FV_RE.search(guarded)
            if m_fv:
                try:
                    stated_fv = float(m_fv.group(1).replace(",", ""))
                    if abs(stated_fv - actual_fv) / actual_fv > 0.03:
                        warnings.append(f"fair_value_hallucination:{sym_f}:stated={stated_fv}_actual={actual_fv}")
                        block_cache = True
                        prepended_warning = True
                        curr_f = rec_f.get("currency") or "ج.م"
                        fv_banner = (
                            f"> ⚠️ **تدقيق القيمة العادلة الحتمي ({sym_f}):** القيمة العادلة المحسوبة برمجياً هي "
                            f"**{actual_fv} {curr_f}** — يُعتمد هذا الرقم على أي رقم مخالف في النص."
                        )
                        if "تدقيق القيمة العادلة الحتمي" not in guarded:
                            guarded = f"{fv_banner}\n\n{guarded}"
                except (TypeError, ValueError):
                    pass

        valid_stops = rec_f.get("valid_stops") or []
        valid_res = rec_f.get("valid_resistances") or []
        lvl_fixes: List[str] = []
        if valid_stops:
            m_sl = _STATED_STOP_ROW_RE.search(guarded)
            if m_sl:
                try:
                    stated_sl = float(m_sl.group(1).replace(",", ""))
                    if all(abs(stated_sl - vs) / max(vs, 1e-6) > 0.025 for vs in valid_stops):
                        warnings.append(f"level_hallucination:{sym_f}:stop_loss")
                        block_cache = True
                        lvl_fixes.append(f"وقف الخسارة الموثق = **{valid_stops[-1]}**")
                except (TypeError, ValueError):
                    pass
        if valid_res:
            m_r1 = _STATED_RES1_ROW_RE.search(guarded)
            if m_r1:
                try:
                    stated_r1 = float(m_r1.group(1).replace(",", ""))
                    if all(abs(stated_r1 - vr) / max(vr, 1e-6) > 0.025 for vr in valid_res):
                        warnings.append(f"level_hallucination:{sym_f}:resistance_1")
                        block_cache = True
                        lvl_fixes.append(f"المقاومة الأولى الموثقة = **{valid_res[0]}**")
                except (TypeError, ValueError):
                    pass
        if lvl_fixes:
            prepended_warning = True
            curr_f = rec_f.get("currency") or "ج.م"
            lvl_banner = f"> ⚠️ **تدقيق المستويات الحتمي ({sym_f}):** {' | '.join(lvl_fixes)} ({curr_f})."
            if "تدقيق المستويات الحتمي" not in guarded:
                guarded = f"{lvl_banner}\n\n{guarded}"

    if checked_dividends and not has_any_upcoming_dividend and _PHANTOM_DIV_RE.search(guarded):
        warnings.append("phantom_upcoming_dividend")
        block_cache = True
        guarded = re.sub(
            r"^[^\n]*🎁\s*كوبون\s+قادم\s*:[^\n]*$",
            "- **التوزيعات القادمة:** لا يوجد كوبون قادم معلن حالياً في قاعدة البيانات (الأرقام المذكورة تخص التوزيعات التاريخية فقط).",
            guarded,
            flags=re.MULTILINE,
        )

    guarded = _dedupe_trailing_disclaimers(guarded)

    return {
        "reply": guarded,
        "warnings": warnings,
        "block_cache": block_cache,
        "prepended_warning": prepended_warning,
    }
