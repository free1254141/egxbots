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
    r"(?:لا\s+تزيد|لا\s+ينصح|لا\s+أنصح|تجنب|ممنوع|مستبعد|مستبعدة|بيع|تصفية|تخارج|إلغاء|خروج|قبل\s+بيع|عوضاً\s+عن|بدلاً\s+من|عدم\s+الشراء|عدم\s+الزيادة|لا\s+تشتري|غير\s+مناسب)"
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

    return {
        "reply": guarded,
        "warnings": warnings,
        "block_cache": block_cache,
        "prepended_warning": prepended_warning,
    }
