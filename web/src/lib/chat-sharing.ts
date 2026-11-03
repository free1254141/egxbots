export function isChatAdminEmail(email: string | null | undefined): boolean {
    if (!email) return false;
    const clean = email.trim().toLowerCase();
    // Keep the existing administrator accounts working when the deployment
    // does not define ADMIN_EMAILS. Environment values can extend this list.
    const configured = (process.env.NEXT_PUBLIC_ADMIN_EMAILS || process.env.ADMIN_EMAILS || "")
        .split(",").map(e => e.trim().toLowerCase()).filter(Boolean);
    const adminEmails = new Set([
        "acursour@gmail.com",
        "weeeessd57@gmail.com",
        "weeessd57@gmail.com",
        "weeasd57@gmail.com",
        "weeeenew@gmail.com",
        ...configured,
    ]);
    if (adminEmails.has(clean)) return true;
    if (clean.includes("weeessd57") || clean.includes("weeeessd57") || clean.includes("weeasd57")) return true;
    return false;
}

/**
 * Strict gatekeeper for experimental Voice features (Live Phone Call 📞 & Voice Notes 🎙️).
 * STRICT RULE: Only the primary admin account (weeessd57) is granted access.
 * Secondary admin emails (e.g. acursour@gmail.com, weeeenew@gmail.com) and regular users are strictly excluded!
 */
export function isVoiceBetaTester(user: { email?: string | null; id?: string | null } | null | undefined): boolean {
    if (!user) return false;

    const clean = (user.email || "").trim().toLowerCase();

    // Explicitly reject any secondary or other admin emails
    if (clean) {
        if (clean.includes("acursour") || clean.includes("weeeenew")) {
            return false;
        }

        const allowedPrefixes = ["weeessd57@", "weeeessd57@", "weeasd57@", "weessd57@"];
        return allowedPrefixes.some(prefix => clean.startsWith(prefix));
    }

    // Explicit known user ID for weeessd57 in Supabase ONLY if no email was attached
    if (user.id === "ba9c27e8-f62d-452f-8a29-dc77fd092207") return true;

    return false;
}

export function isVoiceBetaTesterEmail(email: string | null | undefined): boolean {
    if (!email) return false;
    return isVoiceBetaTester({ email });
}

