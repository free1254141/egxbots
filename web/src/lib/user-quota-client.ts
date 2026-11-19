"use client";

import { TRIAL_AUTOSTART_EVENT } from "@/lib/trial-onboarding";

const QUOTA_CACHE_PREFIX = "egxbots_user_quota_v2:";
const QUOTA_TTL_MS = 10 * 1000; // 10 seconds: deduplicates mount bursts while staying fresh after Telegram usage

type CachedQuotaEntry = {
  ts: number;
  data: any;
};

const memoryCache = new Map<string, CachedQuotaEntry>();
const inFlightRequests = new Map<string, Promise<any | null>>();
let listenersBound = false;

const isValidQuotaPayload = (data: any): boolean =>
  Boolean(data && data.ok !== false && (data.ok === true || data.plan));

function clearUserQuotaStorage(storage: Storage, userId?: string | null): void {
  if (userId) {
    storage.removeItem(`${QUOTA_CACHE_PREFIX}${userId}`);
    storage.removeItem(`egxbots_support_pro_v1:${userId}`);
    for (let i = storage.length - 1; i >= 0; i--) {
      const key = storage.key(i);
      if (key && key.startsWith(`egxbots_ai_recs_v2:${userId}:`)) {
        storage.removeItem(key);
      }
    }
  } else {
    for (let i = storage.length - 1; i >= 0; i--) {
      const key = storage.key(i);
      if (
        key &&
        (key.startsWith(QUOTA_CACHE_PREFIX) ||
          key.startsWith("egxbots_support_pro_v1:") ||
          key.startsWith("egxbots_ai_recs_v2:") ||
          key === "egxbots_trial_status_v2")
      ) {
        storage.removeItem(key);
      }
    }
  }
}

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
    clearUserQuotaStorage(window.sessionStorage, userId);
  } catch {
    // sessionStorage unavailable
  }
  try {
    clearUserQuotaStorage(window.localStorage, userId);
  } catch {
    // localStorage unavailable
  }
}

function bindInvalidationListeners(): void {
  if (listenersBound || typeof window === "undefined") return;
  listenersBound = true;

  const clearAll = () => invalidateUserQuotaCache();
  window.addEventListener("egx:entitlements-updated", clearAll);
  window.addEventListener(TRIAL_AUTOSTART_EVENT, clearAll);
  window.addEventListener("storage", (e: StorageEvent) => {
    if (e.key === "egx_entitlements_timestamp" || e.key === "egx_pro_active" || e.key === "egx_chat_pro_active") {
      clearAll();
    }
  });
}

function readCachedQuotaEntry(userId: string, now: number): CachedQuotaEntry | null {
  if (typeof window === "undefined") return null;
  const key = `${QUOTA_CACHE_PREFIX}${userId}`;
  for (const storage of [window.sessionStorage, window.localStorage]) {
    try {
      const raw = storage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw) as CachedQuotaEntry;
        if (parsed?.ts && now - parsed.ts < QUOTA_TTL_MS && isValidQuotaPayload(parsed.data)) {
          return parsed;
        }
      }
    } catch {
      // ignore storage/JSON errors
    }
  }
  return null;
}

/**
 * Shared, deduplicated `/api/user/quota` client fetcher.
 * Combines in-flight Promise deduplication across simultaneously mounted
 * components with a 30-minute `sessionStorage` + `localStorage` cache so each session
 * and browser tab makes at most 1 quota+trial call instead of redundant round trips.
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

    const stored = readCachedQuotaEntry(userId, now);
    if (stored) {
      memoryCache.set(userId, stored);
      return stored.data;
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
      // client-side deduplication and 30m TTL are handled here in memory + sessionStorage/localStorage.
      const res = await fetch("/api/user/quota", { cache: "no-store" });
      if (!res.ok) return null;
      const data = await res.json();
      if (isValidQuotaPayload(data)) {
        const entry: CachedQuotaEntry = { ts: Date.now(), data };
        memoryCache.set(userId, entry);
        if (typeof window !== "undefined") {
          const serialized = JSON.stringify(entry);
          try {
            window.sessionStorage.setItem(`${QUOTA_CACHE_PREFIX}${userId}`, serialized);
          } catch {
            // ignore sessionStorage quota errors
          }
          try {
            window.localStorage.setItem(`${QUOTA_CACHE_PREFIX}${userId}`, serialized);
            window.localStorage.setItem("egx_pro_active", data?.plan?.is_pro === true ? "true" : "false");
            window.localStorage.setItem("egx_chat_pro_active", (data?.plan?.has_chat_pro ?? data?.plan?.is_pro) === true ? "true" : "false");
          } catch {
            // ignore localStorage quota errors
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
