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
