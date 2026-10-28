/**
 * Shared client-side entitlements broadcast & cache-busting helper.
 * Ensures all open tabs, modals, profile, and scanner cards react
 * instantly when a user activates a Pro trial or completes payment.
 */
export function broadcastEntitlements(isPro: boolean) {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem("egx_scanner_alerts_cache_v2");
    localStorage.setItem("egx_pro_active", isPro ? "true" : "false");
    localStorage.setItem("egx_entitlements_timestamp", String(Date.now()));
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith("egxbots_support_pro_v1:")) {
        sessionStorage.removeItem(k);
      }
    }
    window.dispatchEvent(new CustomEvent("egx:entitlements-updated", { detail: { is_pro: isPro } }));
  } catch {}
}
