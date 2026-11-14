"use client";

import { createBrowserClient } from "@supabase/ssr";
import { AuthError, createClient, type SupabaseClient } from "@supabase/supabase-js";

const wrappedAuth = new WeakSet<object>();
function deduplicateRefresh(client: ReturnType<typeof createBrowserClient>) {
  if (wrappedAuth.has(client.auth)) return client;
  wrappedAuth.add(client.auth);
  const refresh = client.auth.refreshSession.bind(client.auth);
  const pending = new Map<string, ReturnType<typeof refresh>>();
  let generation = 0;
  let owner: string | null | undefined;
  client.auth.onAuthStateChange((event, session) => {
    const next = session?.user?.id ?? null;
    if (event === "INITIAL_SESSION" && owner === undefined) {
      owner = next;
      return;
    }
    if (event === "SIGNED_OUT" || (event === "SIGNED_IN" && next !== owner)) {
      owner = next;
      generation++;
      pending.clear();
    }
  });
  client.auth.refreshSession = ((session?: Parameters<typeof refresh>[0]) => {
    const startedGeneration = generation;
    const key = `${generation}:${session?.refresh_token || "current-session"}`;
    const existing = pending.get(key);
    if (existing) return existing;
    const operation = refresh(session).then((result) =>
      startedGeneration === generation
        ? result
        : {
            data: { session: null, user: null },
            error: new AuthError(
              "Authentication identity changed during refresh",
            ),
          },
    );
    pending.set(key, operation);
    void operation.then(
      () => pending.delete(key),
      () => pending.delete(key),
    );
    return operation;
  }) as typeof client.auth.refreshSession;
  return client;
}

export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey =
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

  if (!url || !anonKey) {
    console.error("Missing Supabase environment variables:", {
      hasUrl: !!url,
      hasAnonKey: !!anonKey,
    });
    throw new Error(
      "Missing Supabase env vars - check Vercel environment variables",
    );
  }

  return deduplicateRefresh(createBrowserClient(url, anonKey));
}

let cachedSaudiBrowserClient: {
  cacheKey: string;
  client: SupabaseClient<any, "public", any>;
} | null = null;

/**
 * Market-aware browser Supabase client for public market-data reads.
 * Primary auth/profiles/subscriptions always use `createSupabaseBrowserClient()`.
 */
export function createMarketSupabaseBrowserClient(
  market: "egx" | "tasi" = "egx",
) {
  if (market !== "tasi") {
    return createSupabaseBrowserClient();
  }

  const url = process.env.NEXT_PUBLIC_SAUDI_SUPABASE_URL;
  const anonKey =
    process.env.NEXT_PUBLIC_SAUDI_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    console.error("Missing Saudi Supabase environment variables:", {
      hasUrl: !!url,
      hasAnonKey: !!anonKey,
    });
    throw new Error(
      "Missing Saudi Supabase env vars - check NEXT_PUBLIC_SAUDI_SUPABASE_URL and NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY",
    );
  }

  const cacheKey = `${url}|${anonKey}`;
  if (cachedSaudiBrowserClient && cachedSaudiBrowserClient.cacheKey === cacheKey) {
    return cachedSaudiBrowserClient.client;
  }

  const client = createClient(url, anonKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  });
  cachedSaudiBrowserClient = { cacheKey, client };
  return client;
}
