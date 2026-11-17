export const ADMIN_EXCLUDED_USER_IDS = new Set<string>([
  "ba9c27e8-f62d-452f-8a29-dc77fd092207", // weeessd57
  "f3592b1c-ebe1-4fed-ba36-b92a58568df8", // weeeenew
  "77f317e8-1df4-4cca-933b-bf4d3662c047", // user@gmail.com
]);

export const ADMIN_EXCLUDED_EMAILS = new Set<string>([
  "acursour@gmail.com",
  "weeessd57@gmail.com",
  "weeeessd57@gmail.com",
  "weeasd57@gmail.com",
  "weeeenew@gmail.com",
  "weessd57@gmail.com",
  "user@gmail.com",
  "egxbots@gmail.com",
  "test1@gmail.com",
]);

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Returns true if the account belongs to internal admins or seed test users
 * and should be omitted from customer retention/engagement analytics.
 */
export function isExcludedAdminUser(
  userId?: string | null,
  email?: string | null,
  extraExcludedIds?: Set<string>
): boolean {
  const uid = String(userId || "").trim();
  if (uid && (ADMIN_EXCLUDED_USER_IDS.has(uid) || extraExcludedIds?.has(uid))) {
    return true;
  }
  const normalizedEmail = String(email || "").trim().toLowerCase();
  return Boolean(normalizedEmail && ADMIN_EXCLUDED_EMAILS.has(normalizedEmail));
}
