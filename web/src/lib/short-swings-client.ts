"use client";

import type { ShortSwingsData } from "@/components/ShortSwingsTab";

// Browser memory only. Never reuse a personalized response for another viewer.
type RequestEntry = { promise: Promise<ShortSwingsData>; pending: boolean; expires: number };
const requests = new Map<string, RequestEntry>();
const REUSE_MS = 10_000;

export function invalidateShortSwingsRequest(viewerKey: string) {
  requests.delete(viewerKey);
}

export function requestShortSwings(viewerKey: string, refresh = false): Promise<ShortSwingsData> {
  const existing = requests.get(viewerKey);
  if (existing?.pending || (!refresh && existing && existing.expires > Date.now())) return existing.promise;
  // Discard older users' completed data and expired entries. No disk storage.
  for (const [key, entry] of requests) {
    if (!entry.pending && (key !== viewerKey || entry.expires <= Date.now())) requests.delete(key);
  }
  const entry: RequestEntry = { promise: null as unknown as Promise<ShortSwingsData>, pending: true, expires: 0 };
  entry.promise = fetch("/api/short-swings", { cache: "no-store" }).then(async response => {
    if (!response.ok) throw new Error(`Short swings HTTP ${response.status}`);
    return response.json() as Promise<ShortSwingsData>;
  }).then(data => {
    entry.pending = false;
    entry.expires = Date.now() + REUSE_MS;
    return data;
  }, error => {
    if (requests.get(viewerKey) === entry) requests.delete(viewerKey);
    throw error;
  });
  requests.set(viewerKey, entry);
  return entry.promise;
}
