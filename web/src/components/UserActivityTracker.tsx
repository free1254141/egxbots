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
    const key = `${user.id}:${cleanPath}`;
    if (lastTracked.current === key) return;
    if (trackingBlocked()) return;

    // Deduplicate repeated navigation to the same page within 15 minutes
    try {
      const raw = sessionStorage.getItem("egxbots_tracked_paths_v1");
      const map = raw ? JSON.parse(raw) : {};
      const now = Date.now();
      if (map[key] && now - map[key] < 15 * 60 * 1000) {
        lastTracked.current = key;
        return;
      }
      map[key] = now;
      sessionStorage.setItem("egxbots_tracked_paths_v1", JSON.stringify(map));
    } catch {}

    lastTracked.current = key;
    void fetch("/api/analytics/events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        event_name: "page_view",
        path: cleanPath,
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
