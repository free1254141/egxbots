/**
 * Per-user standing preferences for the AI chat.
 *
 * Stored in `profiles.custom_ai_rules` (the same field the admin already
 * exposes). The chat route loads it on every turn and:
 *  - appends it to the system prompt so the model follows it across sessions,
 *  - enforces deterministic filters server-side (e.g. sharia_only) so a model
 *    mistake cannot bypass a standing rule,
 *  - bypasses the shared analysis cache when rules exist, because cached
 *    answers are not personalized.
 */

export const SHARIA_RULE_PATTERN = /(?:شريعة|شرعي|شرعية|حلال|إسلامي|اسلامي|egx\s*33)/i;

export const SHARIA_FILTER_TOOLS = new Set([
  "get_recommendations",
  "get_technical_scan",
  "get_accumulation_stocks",
  "screen_stocks",
]);

export function isShariaPreference(rules?: string | null): boolean {
  return Boolean(rules && SHARIA_RULE_PATTERN.test(rules));
}

/** Force deterministic filters that a standing rule requires. */
export function applyUserRulesToToolArgs(
  name: string,
  args: Record<string, unknown>,
  rules?: string | null,
): Record<string, unknown> {
  if (!rules) return args;
  const next = { ...args };
  if (isShariaPreference(rules) && SHARIA_FILTER_TOOLS.has(name)) {
    next.sharia_only = true;
  }
  return next;
}

/** Append a standing rule without duplicating an existing one. */
export function mergeUserRule(existing: string | null | undefined, rule: string, maxLength = 1500): string {
  const current = String(existing || "").trim();
  const clean = String(rule || "").trim().replace(/\s+/g, " ").slice(0, 400);
  if (!clean) return current;
  if (current.toLowerCase().includes(clean.toLowerCase())) return current;
  return [current, `- ${clean}`].filter(Boolean).join("\n").slice(-maxLength);
}

/** Inject the standing rules into the system prompt for this turn. */
export function buildUserRulesPrompt(rules?: string | null): string {
  const clean = String(rules || "").trim();
  if (!clean) return "";
  return [
    "",
    "قواعد المستخدم الدائمة (التزم بها في كل الردود واستدعاءات الأدوات، ولا تنسها بين الجلسات):",
    clean,
    "عند طلب التوصيات أو المسح الفني، إن كانت هذه القواعد تفرض الشريعة الإسلامية فاستخدم sharia_only=true دائماً وبيّن ذلك بإيجاز.",
  ].join("\n");
}
