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
    "manage_automations": "إدارة الاستشارات المجدولة",
    "search_stocks": "البحث في قاعدة البيانات",
    "get_stock": "بيانات السهم",
}
_ORDERED_TOOL_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    (name, re.compile(rf"`?\b{re.escape(name)}\b`?"), label)
    for name, label in sorted(_TOOL_NAME_LABELS.items(), key=lambda kv: len(kv[0]), reverse=True)
]

_LEAKED_FIELD_EXPR_RE = re.compile(
    r"\s*\(\s*`?(?:is_sharia_compliant|data_is_stale|support_1_is_distant|has_active_recommendation)`?\s*[:=]\s*(?:true|false|null)\s*\)",
    re.IGNORECASE,
)
_LEAKED_FIELD_LABELS: Dict[str, str] = {
    "has_active_recommendation": "التوصية المفتوحة",
    "support_1_is_distant": "بعد الدعم الهيكلي",
    "fundamental_diagnosis": "التشخيص المالي",
    "is_sharia_compliant": "التوافق الشرعي",
    "value_trap_warning": "تحذير فخ القيمة",
    "upcoming_dividend": "التوزيع النقدي القادم",
    "upcoming_events": "الأحداث القادمة ومواعيد النتائج",
    "king_ai_score": "تقييم الذكاء الاصطناعي",
    "data_is_stale": "قدم البيانات",
    "fund_score": "التقييم المالي",
    "vol_ratio": "السيولة النسبية",
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

    return {
        "reply": guarded,
        "warnings": warnings,
        "block_cache": block_cache,
        "prepended_warning": prepended_warning,
    }
