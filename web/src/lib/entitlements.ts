/**
 * Shared client-side entitlements broadcast & cache-busting helper.
 * Ensures all open tabs, modals, profile, and scanner cards react
 * instantly when a user activates a Pro trial or completes payment.
 */
export function broadcastEntitlements(isPro: boolean, hasChatPro?: boolean) {
  if (typeof window === "undefined") return;
  const chatPro = hasChatPro ?? isPro;
  try {
    localStorage.removeItem("egx_scanner_alerts_cache_v2");
    localStorage.setItem("egx_pro_active", isPro ? "true" : "false");
    localStorage.setItem("egx_chat_pro_active", chatPro ? "true" : "false");
    localStorage.setItem("egx_entitlements_timestamp", String(Date.now()));
    const clearStorage = (storage: Storage) => {
      for (let i = storage.length - 1; i >= 0; i--) {
        const k = storage.key(i);
        if (
          k &&
          (k.startsWith("egxbots_support_pro_v1:") ||
            k.startsWith("egxbots_user_quota_v2:") ||
            k.startsWith("egxbots_ai_recs_v2:") ||
            k.startsWith("egxbots_portfolio_snapshot_v1:") ||
            k.startsWith("egxbots_portfolio_perf_v1:") ||
            k.startsWith("egxbots_automations_v1:") ||
            k.startsWith("egxbots_telegram_pro_v2:") ||
            k.startsWith("egxbots_chart_markers_v2:") ||
            k === "egxbots_trial_status_v2")
        ) {
          storage.removeItem(k);
        }
      }
    };
    clearStorage(sessionStorage);
    clearStorage(localStorage);
    window.dispatchEvent(new CustomEvent("egx:entitlements-updated", { detail: { is_pro: isPro, has_chat_pro: chatPro } }));
  } catch {}
}
