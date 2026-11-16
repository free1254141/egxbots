import crypto from "crypto";

const DISPOSABLE_EMAIL_DOMAINS = new Set([
  "10minutemail.com",
  "10minutemail.net",
  "dispostable.com",
  "dropmail.me",
  "fakeinbox.com",
  "getnada.com",
  "guerrillamail.com",
  "guerrillamail.info",
  "guerrillamail.net",
  "guerrillamail.org",
  "guerrillamailblock.com",
  "inboxkitten.com",
  "maildrop.cc",
  "mailinator.com",
  "mailnesia.com",
  "mohmal.com",
  "sharklasers.com",
  "temp-mail.io",
  "temp-mail.org",
  "tempmail.com",
  "tempmail.net",
  "tempmailo.com",
  "throwawaymail.com",
  "trashmail.com",
  "trashmail.net",
  "yopmail.com",
  "yopmail.fr",
  "yopmail.net",
]);

const GMAIL_DOMAINS = new Set(["gmail.com", "googlemail.com"]);

/**
 * Normalize an email into its canonical identity so Gmail dot tricks
 * (e.g. a.b+1@gmail.com -> ab@gmail.com) and +aliases map to one address.
 */
export function normalizeCanonicalEmail(email: string | null | undefined): string {
  const cleaned = String(email || "").trim().toLowerCase();
  const atIndex = cleaned.lastIndexOf("@");
  if (atIndex <= 0 || atIndex === cleaned.length - 1) return cleaned;

  let local = cleaned.slice(0, atIndex);
  let domain = cleaned.slice(atIndex + 1);

  const plusIdx = local.indexOf("+");
  if (plusIdx !== -1) {
    local = local.slice(0, plusIdx);
  }

  if (GMAIL_DOMAINS.has(domain)) {
    local = local.replace(/\./g, "");
    domain = "gmail.com";
  }

  return `${local}@${domain}`;
}

export function isDisposableEmail(email: string | null | undefined): boolean {
  const cleaned = String(email || "").trim().toLowerCase();
  const atIndex = cleaned.lastIndexOf("@");
  if (atIndex <= 0) return false;
  const domain = cleaned.slice(atIndex + 1);
  return DISPOSABLE_EMAIL_DOMAINS.has(domain);
}

export function hashTrialSignal(rawValue: string | null | undefined): string | null {
  const value = String(rawValue || "").trim();
  if (!value) return null;
  const salt =
    process.env.TRIAL_ABUSE_SALT ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.EASYKASH_SECRET_KEY ||
    "egxbots-trial-guard-v1";
  return crypto.createHmac("sha256", salt).update(value).digest("hex");
}

export function extractClientIp(request: Request): string | null {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  const realIp = request.headers.get("x-real-ip")?.trim();
  return realIp || null;
}
