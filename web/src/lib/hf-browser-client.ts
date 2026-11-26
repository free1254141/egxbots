"use client";

import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export const HF_DIRECT_ORIGIN = (
  process.env.NEXT_PUBLIC_HF_DIRECT_URL || "https://weeasdwee-ai-bot.hf.space"
).replace(/\/$/, "");

const PROD_HOSTNAMES = new Set(["egxbots.com", "www.egxbots.com"]);
const MAX_CACHE_ENTRIES = 64;
const DEGRADED_COOLDOWN_MS = 60_000;

type CacheEntry = {
  expiresAt: number;
  body: string;
  contentType: string;
};

const responseCache = new Map<string, CacheEntry>();
const inFlightRequests = new Map<string, Promise<{ status: number; body: string; contentType: string; ok: boolean }>>();
let directHfDegradedUntil = 0;

export function resetHfBrowserClientForTests(): void {
  responseCache.clear();
  inFlightRequests.clear();
  directHfDegradedUntil = 0;
}

function normalizePath(pathAndQuery: string): string {
  return pathAndQuery.startsWith("/") ? pathAndQuery : `/${pathAndQuery}`;
}

export function shouldUseDirectHf(): boolean {
  if (typeof window === "undefined") return false;
  if (process.env.NEXT_PUBLIC_DIRECT_HF === "false") return false;
  if (process.env.JEST_WORKER_ID) return false;
  if (Date.now() < directHfDegradedUntil) return false;
  const host = String(window.location?.hostname || "").toLowerCase();
  return PROD_HOSTNAMES.has(host);
}

export function resolveHfAssetUrl(pathAndQuery: string): string {
  const path = normalizePath(pathAndQuery);
  if (shouldUseDirectHf()) {
    return `${HF_DIRECT_ORIGIN}${path}`;
  }
  return path;
}

function setCachedResponse(key: string, entry: CacheEntry): void {
  if (responseCache.has(key)) {
    responseCache.delete(key);
  }
  responseCache.set(key, entry);
  while (responseCache.size > MAX_CACHE_ENTRIES) {
    const oldestKey = responseCache.keys().next().value;
    if (oldestKey === undefined) break;
    responseCache.delete(oldestKey);
  }
}

function buildJsonResponse(body: string, status = 200, contentType = "application/json"): Response {
  if (typeof Response !== "undefined") {
    return new Response(body, {
      status,
      headers: { "Content-Type": contentType || "application/json" },
    });
  }
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "Content-Type": contentType || "application/json" }),
    text: async () => body,
    json: async () => JSON.parse(body),
  } as unknown as Response;
}

function isAbortError(err: unknown): boolean {
  return Boolean(
    err &&
      typeof err === "object" &&
      ("name" in err ? (err as { name?: string }).name === "AbortError" : false)
  );
}

async function fetchTarget(
  targetPath: string,
  init: RequestInit | undefined,
  useDirect: boolean
): Promise<Response> {
  if (!useDirect) {
    return fetch(targetPath, init);
  }
  const directUrl = `${HF_DIRECT_ORIGIN}${targetPath}`;
  try {
    const res = await fetch(directUrl, {
      ...init,
      credentials: "omit",
    });
    if (res.status >= 500) {
      directHfDegradedUntil = Date.now() + DEGRADED_COOLDOWN_MS;
      return fetch(targetPath, init);
    }
    return res;
  } catch (err) {
    if (isAbortError(err) || init?.signal?.aborted) {
      throw err;
    }
    directHfDegradedUntil = Date.now() + DEGRADED_COOLDOWN_MS;
    return fetch(targetPath, init);
  }
}

/**
 * Fetch a purely-public, unauthenticated API route directly from Hugging Face in
 * production browsers (bypassing Vercel Edge/Fast Origin Transfer), with in-tab
 * TTL caching, concurrent GET deduplication, and automatic same-origin fallback.
 *
 * NEVER use for cookie-authenticated endpoints.
 */
export async function hfPublicFetch(
  pathAndQuery: string,
  init?: RequestInit,
  options?: { cacheTtlMs?: number }
): Promise<Response> {
  const targetPath = normalizePath(pathAndQuery);
  const method = String(init?.method || "GET").toUpperCase();
  const cacheTtlMs = Number(options?.cacheTtlMs || 0);
  const canCache = method === "GET" && cacheTtlMs > 0;
  const useDirect = shouldUseDirectHf();

  if (canCache) {
    const cached = responseCache.get(targetPath);
    if (cached && cached.expiresAt > Date.now()) {
      return buildJsonResponse(cached.body, 200, cached.contentType);
    }
    if (cached) {
      responseCache.delete(targetPath);
    }

    const existingFlight = inFlightRequests.get(targetPath);
    if (existingFlight && !init?.signal) {
      const flightRes = await existingFlight;
      return buildJsonResponse(flightRes.body, flightRes.status, flightRes.contentType);
    }

    if (!init?.signal) {
      const flight = (async () => {
        const res = await fetchTarget(targetPath, init, useDirect);
        if (typeof res?.text !== "function") {
          const jsonFn = (res as unknown as { json?: () => Promise<unknown> })?.json;
          const body = typeof jsonFn === "function" ? JSON.stringify(await jsonFn.call(res)) : "";
          const ct = "application/json";
          if (res.ok && body) {
            setCachedResponse(targetPath, { expiresAt: Date.now() + cacheTtlMs, body, contentType: ct });
          }
          return { status: res.status || (res.ok ? 200 : 500), body, contentType: ct, ok: Boolean(res.ok) };
        }
        const body = await res.text();
        const ct = res.headers?.get?.("content-type") || "application/json";
        if (res.ok) {
          setCachedResponse(targetPath, { expiresAt: Date.now() + cacheTtlMs, body, contentType: ct });
        }
        return { status: res.status, body, contentType: ct, ok: res.ok };
      })().finally(() => {
        inFlightRequests.delete(targetPath);
      });
      inFlightRequests.set(targetPath, flight);
      const result = await flight;
      return buildJsonResponse(result.body, result.status, result.contentType);
    }
  }

  const res = await fetchTarget(targetPath, init, useDirect);
  if (canCache && res.ok && typeof res?.text === "function") {
    const body = await res.text();
    const ct = res.headers?.get?.("content-type") || "application/json";
    setCachedResponse(targetPath, { expiresAt: Date.now() + cacheTtlMs, body, contentType: ct });
    return buildJsonResponse(body, res.status, ct);
  }
  return res;
}

async function getSupabaseAccessToken(): Promise<string | null> {
  try {
    const sb = createSupabaseBrowserClient();
    const { data } = await sb.auth.getSession();
    return data?.session?.access_token || null;
  } catch {
    return null;
  }
}

/**
 * Fetch an authenticated (or dual public/user) HF endpoint directly from the browser
 * using the Supabase JWT Bearer token (`credentials: "omit"`), bypassing Vercel Fast
 * Origin Transfer while preserving SSE streaming and falling back seamlessly to
 * same-origin `fetch()` on missing token (when `requireToken`), 401, 5xx, or network error.
 */
export async function hfAuthFetch(
  pathAndQuery: string,
  init?: RequestInit,
  options?: { requireToken?: boolean }
): Promise<Response> {
  const targetPath = normalizePath(pathAndQuery);
  if (!shouldUseDirectHf()) {
    return fetch(targetPath, init);
  }

  const headers = new Headers(init?.headers);
  let token = headers.get("authorization");
  if (token && token.toLowerCase().startsWith("bearer ")) {
    token = token.slice(7).trim();
  } else {
    token = await getSupabaseAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  if (options?.requireToken && !token) {
    return fetch(targetPath, init);
  }

  const directUrl = `${HF_DIRECT_ORIGIN}${targetPath}`;
  try {
    const res = await fetch(directUrl, {
      ...init,
      headers,
      credentials: "omit",
    });
    if (res.status === 401) {
      return fetch(targetPath, init);
    }
    if (res.status >= 500) {
      directHfDegradedUntil = Date.now() + DEGRADED_COOLDOWN_MS;
      return fetch(targetPath, init);
    }
    return res;
  } catch (err) {
    if (isAbortError(err) || init?.signal?.aborted) {
      throw err;
    }
    directHfDegradedUntil = Date.now() + DEGRADED_COOLDOWN_MS;
    return fetch(targetPath, init);
  }
}
