"use client";

import { Suspense, useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

function getTrackingSessionId(): string {
  const key = "egxbots_activity_session_v1";
  try {
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const created = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(key, created);
    return created;
  } catch {
    return "browser-session";
  }
}

// After a 401 the server cannot see this browser's session (expired token). Every
// further page view would be another failed serverless call, so pause for a while.
const BLOCK_KEY = "egxbots_activity_blocked_until_v1";
const BLOCK_MS = 10 * 60 * 1000;
function trackingBlocked(): boolean {
  try {
    return Number(sessionStorage.getItem(BLOCK_KEY) || 0) > Date.now();
  } catch {
    return false;
  }
}
function blockTracking() {
  try {
    sessionStorage.setItem(BLOCK_KEY, String(Date.now() + BLOCK_MS));
  } catch {
    // storage unavailable
  }
}

function normalizeTrackedPath(cleanPath: string): string {
  if (cleanPath.startsWith("/stocks/")) return "/stocks/[symbol]";
  if (cleanPath.startsWith("/blogs/")) return "/blogs/[slug]";
  if (cleanPath.startsWith("/reports/")) return "/reports/[report]";
  return cleanPath;
}

const TRACKED_PATHS_STORAGE_KEY = "egxbots_tracked_paths_v2";
const TRACK_DEDUPE_MS = 6 * 60 * 60 * 1000; // 6 hours

function Tracker() {
  const { user } = useAuth();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = ["bots", "similarity", "backtests", "analytics"].includes(rawTab || "") ? rawTab : "bots";
  const lastTracked = useRef("");

  useEffect(() => {
    if (!user || !pathname || pathname.startsWith("/admin") || pathname.startsWith("/api/")) return;
    const basePath = pathname.replace(/^\/(?:ar|en)(?=\/|$)/, "") || "/";
    const cleanPath = basePath === "/scanner/backtests" ? `${basePath}?tab=${tab}` : basePath;
    const normalizedPath = normalizeTrackedPath(cleanPath);
    const key = `${user.id}:${normalizedPath}`;
    if (lastTracked.current === key) return;
    if (trackingBlocked()) return;

    // Deduplicate repeated navigation to the same route pattern within 6 hours via localStorage
    try {
      const raw = localStorage.getItem(TRACKED_PATHS_STORAGE_KEY);
      const map: Record<string, number> = raw ? JSON.parse(raw) : {};
      const now = Date.now();
      for (const existingKey of Object.keys(map)) {
        if (now - Number(map[existingKey] || 0) >= TRACK_DEDUPE_MS) {
          delete map[existingKey];
        }
      }
      if (map[key] && now - map[key] < TRACK_DEDUPE_MS) {
        lastTracked.current = key;
        return;
      }
      map[key] = now;
      localStorage.setItem(TRACKED_PATHS_STORAGE_KEY, JSON.stringify(map));
    } catch {}

    lastTracked.current = key;
    void fetch("/api/analytics/events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        event_name: "page_view",
        path: normalizedPath,
        session_id: getTrackingSessionId(),
        metadata: { title: typeof document !== "undefined" ? document.title : "", ...(basePath === "/scanner/backtests" ? { tab } : {}) },
      }),
      keepalive: true,
    }).then((res) => { if (res.status === 401) blockTracking(); }).catch(() => undefined);
  }, [pathname, tab, user]);

  return null;
}

export default function UserActivityTracker() {
  return <Suspense fallback={null}><Tracker /></Suspense>;
}
