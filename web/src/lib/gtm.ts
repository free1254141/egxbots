/**
 * Thin Google Tag Manager helper.
 *
 * The GTM container is injected once in `app/layout.tsx`; this module only
 * pushes semantic events onto `window.dataLayer` so Ads/Analytics can build
 * the signup funnel without touching each component's business logic.
 */

type GtmPayload = Record<string, unknown>;

declare global {
  interface Window {
    dataLayer?: GtmPayload[];
  }
}

export function trackEvent(event: string, payload: GtmPayload = {}): void {
  if (typeof window === "undefined") return;
  try {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event, ...payload });
  } catch {
    // Analytics must never break a user interaction.
  }
}
