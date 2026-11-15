"""
api/agentic_chat/user_preferences.py
Per-user standing preferences and custom AI rules for the agentic financial chatbot.
Stores and syncs memory with `profiles.custom_ai_rules` in Supabase.
100% parity with Vercel user-preferences.ts.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


SHARIA_RULE_PATTERN = re.compile(r"(?:شريعة|شريعه|شرعي|شرعية|شرعيه|حلال|إسلامي|اسلامي|egx\s*33)", re.IGNORECASE)

SHARIA_FILTER_TOOLS = frozenset({
    "get_recommendations",
    "get_technical_scan",
    "get_accumulation_stocks",
    "screen_stocks",
    "get_fair_value",
})


def user_rules_list(rules: Optional[str]) -> List[str]:
    """Parse newline-separated rules into a clean list."""
    if not rules:
        return []
    return [line.strip() for line in str(rules).split("\n") if line.strip()]


def merge_user_rule(existing: Optional[str], rule: str, max_length: int = 2000) -> str:
    """Append a standing rule without duplicating an existing one."""
    current = str(existing or "").strip()
    clean = str(rule or "").strip()[:400]
    if not clean:
        return current
    # Remove leading bullet if provided by user/model
    clean_text = clean[2:].strip() if clean.startswith("- ") else clean
    if not clean_text:
        return current

    # Deduplicate against existing lines
    current_lines = user_rules_list(current)
    for line in current_lines:
        line_body = line[2:].strip() if line.startswith("- ") else line
        if clean_text.lower() == line_body.lower() or clean_text.lower() in line_body.lower():
            return current

    new_line = f"- {clean_text}"
    if current:
        combined = f"{current}\n{new_line}"
    else:
        combined = new_line
    return combined[-max_length:]


def remove_user_rule(
    existing: Optional[str],
    match: str,
    max_length: int = 2000,
) -> Tuple[str, bool]:
    """Remove the first or matching rules that contain the user/model supplied match text."""
    lines = user_rules_list(existing)
    target = str(match or "").strip().lower()
    if not target or not lines:
        return "\n".join(lines), False

    remaining: List[str] = []
    removed_count = 0
    for line in lines:
        text = line[2:].strip() if line.startswith("- ") else line
        if target in text.lower() or text.lower() in target:
            removed_count += 1
        else:
            remaining.append(line)

    result_str = "\n".join(remaining)[-max_length:]
    return result_str, removed_count > 0


def replace_user_rules(rules: List[str], max_length: int = 2000) -> str:
    """Replace the whole memory with the list proposed."""
    clean_lines = []
    for r in (rules or []):
        s = str(r or "").strip()
        if s:
            clean_lines.append(s if s.startswith("- ") else f"- {s}")
    return "\n".join(clean_lines)[-max_length:]


def is_sharia_preference(rules: Optional[str]) -> bool:
    """Check if the user standing rules enforce Islamic Sharia compliance."""
    if not rules:
        return False
    return bool(SHARIA_RULE_PATTERN.search(str(rules)))


def apply_user_rules_to_tool_args(
    tool_name: str,
    args: Dict[str, Any],
    rules: Optional[str],
) -> Dict[str, Any]:
    """Force deterministic tool filters that a standing rule requires (e.g. sharia_only)."""
    if not rules:
        return args
    next_args = dict(args)
    if is_sharia_preference(rules) and tool_name in SHARIA_FILTER_TOOLS:
        # Enforce sharia_only=True unless explicitly specified otherwise by caller
        if "sharia_only" not in next_args or next_args["sharia_only"] is False:
            next_args["sharia_only"] = True
    return next_args


def build_user_rules_prompt(rules: Optional[str]) -> str:
    """Inject the standing rules into the system prompt for this turn."""
    clean = str(rules or "").strip()
    if not clean:
        return ""
    return (
        "📌 ذاكرة المستخدم الدائمة (قواعد وتفضيلات مخصصة ومحفوظة من محادثات سابقة بحسابه):\n"
        f"{clean}\n\n"
        "تعليمات الالتزام بذاكرة المستخدم:\n"
        "1. التزم بهذه القواعد بدقة في كل الردود واستدعاءات الأدوات ما لم يطلب المستخدم صراحةً خلاف ذلك في هذه الرسالة.\n"
        "2. إذا كانت القواعد تفرض التوافق مع الشريعة الإسلامية، استخدم sharia_only=true دائماً في أدوات التوصيات والمسح الفني واذكر ذلك باختصار.\n"
        "3. إذا تعارضت القاعدة المحفوظة مع السؤال الحالي، اشرح التعارض باختصار واسأل المستخدم عما إذا كان يريد استثناء هذا الطلب فقط أم تعديل الذاكرة الدائمة.\n"
        "4. عند رغبة المستخدم في إضافة أو تعديل أو حذف أي قاعدة من ذاكرته، استدعِ أداة manage_user_preferences فوراً ثم أكّد له ما تم حفظه."
    )
