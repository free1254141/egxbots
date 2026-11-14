"use client";

import { TRIAL_AUTOSTART_EVENT } from "@/lib/trial-onboarding";

const QUOTA_CACHE_PREFIX = "egxbots_user_quota_v2:";
const QUOTA_TTL_MS = 30 * 60 * 1000; // 30 minutes

type CachedQuotaEntry = {
  ts: number;
  data: any;
};

const memoryCache = new Map<string, CachedQuotaEntry>();
const inFlightRequests = new Map<string, Promise<any | null>>();
let listenersBound = false;

const isValidQuotaPayload = (data: any): boolean =>
  Boolean(data && data.ok !== false && (data.ok === true || data.plan));

export function invalidateUserQuotaCache(userId?: string | null): void {
  if (userId) {
    memoryCache.delete(userId);
    inFlightRequests.delete(userId);
  } else {
    memoryCache.clear();
    inFlightRequests.clear();
  }

  if (typeof window === "undefined") return;
  try {
    if (userId) {
      window.sessionStorage.removeItem(`${QUOTA_CACHE_PREFIX}${userId}`);
      window.sessionStorage.removeItem(`egxbots_support_pro_v1:${userId}`);
      for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
        const key = window.sessionStorage.key(i);
        if (key && key.startsWith(`egxbots_ai_recs_v2:${userId}:`)) {
          window.sessionStorage.removeItem(key);
        }
      }
    } else {
      for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
        const key = window.sessionStorage.key(i);
        if (
          key &&
          (key.startsWith(QUOTA_CACHE_PREFIX) ||
            key.startsWith("egxbots_support_pro_v1:") ||
            key.startsWith("egxbots_ai_recs_v2:") ||
            key === "egxbots_trial_status_v2")
        ) {
          window.sessionStorage.removeItem(key);
        }
      }
    }
  } catch {
    // sessionStorage unavailable
  }
}

function bindInvalidationListeners(): void {
  if (listenersBound || typeof window === "undefined") return;
  listenersBound = true;

  // If the user explicitly pressed browser Refresh (F5), clear cached session quota
  // and recommendations once at boot so manual admin approvals reflect immediately.
  try {
    const navEntry = window.performance?.getEntriesByType?.("navigation")?.[0] as
      | PerformanceNavigationTiming
      | undefined;
    if (navEntry?.type === "reload") {
      invalidateUserQuotaCache();
    }
  } catch {
    // ignore performance API errors
  }

  const clearAll = () => invalidateUserQuotaCache();
  window.addEventListener("egx:entitlements-updated", clearAll);
  window.addEventListener(TRIAL_AUTOSTART_EVENT, clearAll);
  window.addEventListener("storage", (e: StorageEvent) => {
    if (e.key === "egx_entitlements_timestamp" || e.key === "egx_pro_active") {
      clearAll();
    }
  });
}

/**
 * Shared, deduplicated `/api/user/quota` client fetcher.
 * Combines in-flight Promise deduplication across simultaneously mounted
 * components with a 30-minute `sessionStorage` cache so each session makes at
 * most 1 quota+trial call instead of 4-5 redundant round trips.
 */
export async function fetchUserQuotaCached(
  userId?: string | null,
  opts?: { force?: boolean }
): Promise<any | null> {
  if (!userId) return null;
  bindInvalidationListeners();

  const force = opts?.force === true;
  const now = Date.now();

  if (!force) {
    const mem = memoryCache.get(userId);
    if (mem && now - mem.ts < QUOTA_TTL_MS) {
      return mem.data;
    }

    if (typeof window !== "undefined") {
      try {
        const raw = window.sessionStorage.getItem(`${QUOTA_CACHE_PREFIX}${userId}`);
        if (raw) {
          const parsed = JSON.parse(raw) as CachedQuotaEntry;
          if (parsed?.ts && now - parsed.ts < QUOTA_TTL_MS && isValidQuotaPayload(parsed.data)) {
            memoryCache.set(userId, parsed);
            return parsed.data;
          }
        }
      } catch {
        // ignore storage/JSON errors
      }
    }

    const existingPromise = inFlightRequests.get(userId);
    if (existingPromise) {
      return existingPromise;
    }
  } else {
    invalidateUserQuotaCache(userId);
  }

  const requestPromise = (async () => {
    try {
      // Bypass browser HTTP cache so force refreshes & post-upgrade mutations never read stale Free responses;
      // client-side deduplication and 30m TTL are handled here in memory + sessionStorage.
      const res = await fetch("/api/user/quota", { cache: "no-store" });
      if (!res.ok) return null;
      const data = await res.json();
      if (isValidQuotaPayload(data)) {
        const entry: CachedQuotaEntry = { ts: Date.now(), data };
        memoryCache.set(userId, entry);
        if (typeof window !== "undefined") {
          try {
            window.sessionStorage.setItem(`${QUOTA_CACHE_PREFIX}${userId}`, JSON.stringify(entry));
          } catch {
            // ignore storage quota errors
          }
        }
      }
      return data;
    } catch {
      return null;
    } finally {
      inFlightRequests.delete(userId);
    }
  })();

  inFlightRequests.set(userId, requestPromise);
  return requestPromise;
}
