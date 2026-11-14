import { createClient } from "@supabase/supabase-js";
import { marketCachedFetch } from "@/lib/cache/market-query-cache";

export function getSupabaseClient(): any {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const key =
    process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.SUPABASE_ANON_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

  if (!url || !key) {
    throw new Error("Missing Supabase environment variables");
  }

  return createClient(url, key, {
    global: { fetch: marketCachedFetch({ url, key }) },
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  }) as any;
}

/** Server-only client for private tables. Never fall back to an anonymous key. */
export function getSupabaseServiceClient(options: { cacheMarketData?: boolean } = {}): any {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY;

  if (!url || !key) {
    throw new Error("Missing server-side Supabase service credentials");
  }

  return createClient(url, key, {
    ...(options.cacheMarketData ? { global: { fetch: marketCachedFetch({ url, key }) } } : {}),
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  }) as any;
}

/** Cookie-free public reads; preserves anonymous RLS (never escalates to service role). */
export function getPublicMarketClient(): any {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY;
  if (!url || !key) throw new Error("Missing public Supabase configuration");
  return createClient(url, key, {
    global: { fetch: marketCachedFetch({ url, key }) },
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

export type MarketMode = "egx" | "tasi";

const SAUDI_MARKET_TOKENS = new Set([
  "tasi",
  "tadawul",
  "saudi",
  "saudi arabia",
  "saudi_arabia",
  "ksa",
  "sa",
  "sar",
  "تاسي",
  "السعودية",
  "تداول",
]);

const EGX_MARKET_TOKENS = new Set([
  "egx",
  "egypt",
  "eg",
  "egp",
  "مصر",
  "البورصة المصرية",
]);

const SAUDI_SYMBOL_QUERY_RE = /^\d{4}(\.(SR|SA|TADAWUL))?$/i;

function parseMarketToken(raw?: string | null): MarketMode | null {
  if (!raw) return null;
  const clean = raw.trim().toLowerCase();
  if (!clean) return null;
  if (SAUDI_MARKET_TOKENS.has(clean)) return "tasi";
  if (EGX_MARKET_TOKENS.has(clean)) return "egx";
  return null;
}

function readCookieFromHeader(cookieHeader: string | null | undefined, name: string): string | null {
  if (!cookieHeader) return null;
  const parts = cookieHeader.split(";");
  for (const part of parts) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) {
      const rawValue = part.slice(idx + 1).trim();
      try {
        return decodeURIComponent(rawValue);
      } catch {
        return rawValue;
      }
    }
  }
  return null;
}

/**
 * Resolves the target market (`"egx"` | `"tasi"`) for an incoming route request.
 * Priority: explicit argument -> URL query params -> `x-egxbots-market` header -> `egxbots_market` cookie -> `"egx"`.
 */
export function resolveRequestMarket(
  req?: Request | null,
  explicitCountryOrMarket?: string | null,
): MarketMode {
  const fromExplicit = parseMarketToken(explicitCountryOrMarket);
  if (fromExplicit) return fromExplicit;

  if (req?.url) {
    try {
      const parsedUrl = new URL(req.url, "http://localhost");
      for (const paramName of ["market", "country", "exchange"]) {
        const parsed = parseMarketToken(parsedUrl.searchParams.get(paramName));
        if (parsed) return parsed;
      }
      const symbolParam = parsedUrl.searchParams.get("symbol")?.trim();
      if (symbolParam && SAUDI_SYMBOL_QUERY_RE.test(symbolParam)) {
        return "tasi";
      }
    } catch {
      // Ignore malformed request URLs
    }
  }

  const headerMarket = parseMarketToken(req?.headers?.get?.("x-egxbots-market"));
  if (headerMarket) return headerMarket;

  const cookieFromStore = (req as { cookies?: { get?: (n: string) => { value?: string } | undefined } } | null | undefined)
    ?.cookies?.get?.("egxbots_market")?.value;
  const cookieMarket =
    parseMarketToken(cookieFromStore) ??
    parseMarketToken(readCookieFromHeader(req?.headers?.get?.("cookie"), "egxbots_market"));
  if (cookieMarket) return cookieMarket;

  return "egx";
}

export function getMarketExchange(market: MarketMode): "EGX" | "TADAWUL" {
  return market === "tasi" ? "TADAWUL" : "EGX";
}

function createSaudiSupabaseClient(
  keyCandidates: Array<string | undefined>,
  cacheMarketData: boolean,
  missingMessage: string,
): any {
  const url = process.env.SAUDI_SUPABASE_URL || process.env.NEXT_PUBLIC_SAUDI_SUPABASE_URL;
  const key = keyCandidates.find((candidate) => Boolean(candidate));

  if (!url || !key) {
    throw new Error(missingMessage);
  }

  return createClient(url, key, {
    ...(cacheMarketData ? { global: { fetch: marketCachedFetch({ url, key }) } } : {}),
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  }) as any;
}

/** Market-aware public/cached Supabase client (`"egx"` -> Primary, `"tasi"` -> Saudi). */
export function getMarketSupabaseClient(market: MarketMode = "egx"): any {
  if (market !== "tasi") {
    return getSupabaseClient();
  }

  return createSaudiSupabaseClient(
    [
      process.env.SAUDI_SUPABASE_SECRET_KEY,
      process.env.SAUDI_SUPABASE_SERVICE_ROLE_KEY,
      process.env.SAUDI_SUPABASE_SERVICE_KEY,
      process.env.NEXT_PUBLIC_SAUDI_SUPABASE_PUBLISHABLE_KEY,
      process.env.SAUDI_SUPABASE_ANON_KEY,
      process.env.NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY,
    ],
    true,
    "Missing Saudi Supabase environment variables",
  );
}

/** Market-aware server Supabase client (`"egx"` -> Primary, `"tasi"` -> Saudi). */
export function getMarketSupabaseServiceClient(
  market: MarketMode = "egx",
  options: { cacheMarketData?: boolean } = {},
): any {
  if (market !== "tasi") {
    return getSupabaseServiceClient(options);
  }

  return createSaudiSupabaseClient(
    [
      process.env.SAUDI_SUPABASE_SECRET_KEY,
      process.env.SAUDI_SUPABASE_SERVICE_ROLE_KEY,
      process.env.SAUDI_SUPABASE_SERVICE_KEY,
      process.env.SAUDI_SUPABASE_ANON_KEY,
      process.env.NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY,
    ],
    Boolean(options.cacheMarketData),
    "Missing Saudi Supabase server credentials",
  );
}

export function toNumber(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function toSnakeCase(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}
