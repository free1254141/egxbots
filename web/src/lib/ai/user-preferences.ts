/**
 * Per-user standing preferences for the AI chat.
 *
 * Stored in `profiles.custom_ai_rules` (the same field the admin already
 * exposes). The chat route loads it on every turn and appends it to the system
 * prompt, so the model — not a regex router — decides how to interpret it,
 * when to apply it, and how to discuss a conflict with the user.
 *
 * The model can manage the same list through `manage_user_preferences`
 * (add / delete / replace). No native intent pattern matching lives here.
 */

export function userRulesList(rules?: string | null): string[] {
  return String(rules || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Append a standing rule without duplicating an existing one. */
export function mergeUserRule(existing: string | null | undefined, rule: string, maxLength = 2000): string {
  const current = String(existing || "").trim();
  const clean = String(rule || "").trim().slice(0, 400);
  if (!clean) return current;
  if (current.toLowerCase().includes(clean.toLowerCase())) return current;
  return [current, `- ${clean}`].filter(Boolean).join("\n").slice(-maxLength);
}

/** Remove the first rule that contains the user/model supplied match text. */
export function removeUserRule(
  existing: string | null | undefined,
  match: string,
  maxLength = 2000,
): { rules: string; removed: boolean } {
  const lines = userRulesList(existing);
  const target = String(match || "").trim().toLowerCase();
  if (!target) return { rules: lines.join("\n"), removed: false };
  const remaining = lines.filter((line) => {
    const text = line.startsWith("- ") ? line.slice(2) : line;
    return !text.toLowerCase().includes(target);
  });
  return { rules: remaining.join("\n").slice(-maxLength), removed: remaining.length !== lines.length };
}

/** Replace the whole memory with the list the model proposes. */
export function replaceUserRules(rules: string[], maxLength = 2000): string {
  const lines = (Array.isArray(rules) ? rules : [])
    .map((rule) => String(rule || "").trim())
    .filter(Boolean)
    .map((rule) => (rule.startsWith("- ") ? rule : `- ${rule}`));
  return lines.join("\n").slice(-maxLength);
}

/** Inject the standing rules into the system prompt for this turn. */
export function buildUserRulesPrompt(rules?: string | null): string {
  const clean = String(rules || "").trim();
  if (!clean) return "";
  return [
    "",
    "ذاكرة المستخدم الدائمة (قواعد وتفضيلات محفوظة من محادثات سابقة):",
    clean,
    "التزم بها في كل الردود واستدعاءات الأدوات ما لم يطلب المستخدم صراحةً غير ذلك في هذه الرسالة.",
    "إذا تعارضت القاعدة المحفوظة مع الطلب الحالي، اشرح التعارض باختصار واسأل المستخدم: أطبق القاعدة المحفوظة، أم أستثني هذا الطلب فقط، أم أحدّث الذاكرة؟ لا تتجاهل القاعدة بصمت.",
    "عندما يوافق المستخدم على إضافة قاعدة أو تعديلها أو حذفها، استخدم أداة manage_user_preferences ثم أكّد له ما تم حفظه.",
  ].join("\n");
}
