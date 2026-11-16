"use client";

import { toast } from "sonner";

/**
 * Compute a deterministic, privacy-safe SHA-256 device fingerprint for trial
 * anti-abuse checks. Never sends raw hardware values to the server—only a hex digest.
 */
export async function getTrialDeviceFingerprint(): Promise<string> {
  if (typeof window === "undefined") return "";
  try {
    const nav = window.navigator;
    const scr = window.screen;
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    const parts = [
      nav.userAgent || "",
      nav.language || "",
      String(nav.hardwareConcurrency || ""),
      String((nav as Navigator & { deviceMemory?: number }).deviceMemory || ""),
      String(nav.maxTouchPoints || 0),
      `${scr?.width || 0}x${scr?.height || 0}x${scr?.colorDepth || 0}`,
      String(window.devicePixelRatio || 1),
      tz,
    ];
    const raw = parts.join("|");
    if (window.crypto?.subtle) {
      const data = new TextEncoder().encode(raw);
      const digest = await window.crypto.subtle.digest("SHA-256", data);
      return Array.from(new Uint8Array(digest))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    }
    // Lightweight deterministic fallback when SubtleCrypto is unavailable
    let h = 2166136261;
    for (let i = 0; i < raw.length; i += 1) {
      h ^= raw.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return `fnv_${(h >>> 0).toString(16)}`;
  } catch {
    return "";
  }
}

export function notifyTrialActivationError(
  data: { error?: string; message?: string; telegram_bot_url?: string } | null | undefined,
  isAr: boolean,
  userId?: string | null
): void {
  const msg = data?.message || (isAr ? "تعذر تفعيل التجربة" : "Could not activate trial");
  if (data?.error === "TELEGRAM_LINK_REQUIRED") {
    const tgUrl =
      data.telegram_bot_url ||
      (userId ? `https://t.me/egxbots_bot?start=${userId}` : "https://t.me/egxbots_bot");
    toast.error(msg, {
      duration: 8000,
      action: {
        label: isAr ? "ربط تليجرام الآن" : "Link Telegram",
        onClick: () => {
          window.open(tgUrl, "_blank", "noopener,noreferrer");
        },
      },
    });
    return;
  }
  toast.error(msg);
}
