import { NextRequest, NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { getSupabaseServiceClient, toNumber } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS } from "@/lib/cache/daily";
import { getViewerContext } from "@/lib/supabase/viewer-context";
import { paymentsEnabled } from "@/lib/ai/plan-gate";
import { applyRecommendationQuotes } from "@/lib/recommendation-quotes";

const FREE_ENCRYPTED_OPEN_RETURN_PCT = 50;
const DAY_MS = 24 * 60 * 60 * 1000;

const RECOMMENDATION_FIELDS =
  "id,batch_id,symbol,exchange,name,last_close,precision,signal,status,entry_price,target_price,stop_loss,is_public,created_at,updated_at,exit_price,profit_loss_pct,top_reasons,rich_details";

export const runtime = "nodejs";
// Responses stay request-specific (locked vs unlocked rows depend on the viewer),
// so the CDN must never share them. The expensive part — reading the public
// snapshot from Supabase — is cached below in the Data Cache instead.
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

type RecommendationSnapshot = {
  rows: Record<string, any>[];
  sectors: Record<string, string>;
};

/**
 * Public recommendation snapshot (rows + sector labels). Nothing in here is
 * viewer-specific, so it is shared by anonymous and signed-in callers. The
 * per-viewer masking/locking still happens on every request in `GET`.
 */
const loadRecommendationSnapshot = unstable_cache(
  async (limit: number): Promise<RecommendationSnapshot> => {
    const supabase = getSupabaseServiceClient({ cacheMarketData: true });
    // The calendar and closed archive need every public recommendation.
    // current_public_recommendations deduplicates by symbol and would erase
    // historical wins/losses whenever that view exists.
    const { data, error } = await supabase
      .from("scan_results")
      .select(RECOMMENDATION_FIELDS)
      .eq("is_public", true)
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error) throw error;

    let rows: Record<string, any>[] = data || [];
    // Quote refresh is independent of trade evaluation. Never replace closed
    // exit prices, and never infer a current quote from an old recommendation.
    const openSymbols = [...new Set(rows.filter((row) => row.status === "open").map((row) => row.symbol))];
    if (openSymbols.length) {
      const since = new Date(Date.now() - 30 * DAY_MS).toISOString().slice(0, 10);
      const { data: quotes, error: quoteError } = await supabase.from("stock_prices")
        .select("symbol,exchange,date,close,volume,updated_at")
        .in("symbol", openSymbols).gte("date", since)
        .order("date", { ascending: false }).limit(6000);
      if (quoteError) throw quoteError;
      rows = applyRecommendationQuotes(rows, quotes || []);
    }

    const symbols = Array.from(new Set(rows.map((row) => String(row.symbol || "")).filter(Boolean)));
    const { data: fundamentals } = symbols.length
      ? await supabase
        .from("stock_fundamentals")
        .select("symbol,data")
        .in("symbol", symbols)
      : { data: [] as Array<{ symbol: string; data?: Record<string, unknown> }> };

    const sectors: Record<string, string> = {};
    for (const row of fundamentals || []) {
      sectors[String(row.symbol)] =
        row.data?.sector || row.data?.Sector || row.data?.industry || "General";
    }

    return { rows, sectors };
  },
  ["ai-bot-recommendations-snapshot-v1"],
  { revalidate: 900, tags: [DAILY_CACHE_TAGS.recommendations] }
);

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const requestedLimit = Number(url.searchParams.get("limit") || 50);
  const limit = Number.isFinite(requestedLimit) && requestedLimit > 0
      ? Math.min(Math.floor(requestedLimit), 200)
      : 50;

  try {
    // Session + plan now resolve through in-memory freshness windows instead
    // of a Supabase auth round trip on every page view.
    const { authenticated, pro } = await getViewerContext(req);
    const payments = paymentsEnabled();
    const delayedVisibility = !authenticated || (payments && !pro);
    const delayDays = Number(process.env.FREE_SIGNAL_DELAY_DAYS || 15) || 15;
    const cutoffTime = Date.now() - delayDays * 24 * 60 * 60 * 1000;
    // Round down the display cutoff; actionable-signal gating uses cutoffTime.
    const cutoff = new Date(Math.floor(cutoffTime / 86400000) * 86400000).toISOString();
    // Shared, viewer-independent snapshot from the Data Cache. Re-reading it per
    // visitor used to run 3 Supabase queries on every request.
    const { rows: visibleData, sectors } = await loadRecommendationSnapshot(limit);
    const closed = (row: Record<string, unknown>) => ["win", "loss"].includes(String(row.status || "").toLowerCase());
    const recommendationReturnPct = (row: Record<string, unknown>) => {
      if (closed(row)) return row.profit_loss_pct == null ? null : toNumber(row.profit_loss_pct, 0);
      const entryPrice = toNumber(row.entry_price, 0);
      const lastClose = toNumber(row.last_close, 0);
      if (entryPrice > 0 && lastClose > 0) return ((lastClose - entryPrice) / entryPrice) * 100;
      return row.profit_loss_pct == null ? null : toNumber(row.profit_loss_pct, 0);
    };
    const isHighReturn = (row: Record<string, unknown>) =>
      (recommendationReturnPct(row) ?? Number.NEGATIVE_INFINITY) > FREE_ENCRYPTED_OPEN_RETURN_PCT;
    const recommendationAgeDays = (row: Record<string, unknown>) => {
      const createdMs = row.created_at ? new Date(String(row.created_at)).getTime() : Number.NaN;
      if (!Number.isFinite(createdMs)) return null;
      const endAt = closed(row) && row.updated_at ? new Date(String(row.updated_at)).getTime() : Date.now();
      if (!Number.isFinite(endAt)) return null;
      return Math.floor(Math.max(0, endAt - createdMs) / DAY_MS);
    };
    // Actionable picks for anonymous and Free users are safely locked and masked
    // by `if (locked)` below (withholding symbol, name, and trade prices).
    // Settled outcomes (wins/losses) remain public for auditing.

    const sectorMap = new Map(Object.entries(sectors));

    const results = visibleData.map((row: Record<string, unknown>) => {
      // Closed outcomes remain encrypted for Free users only during the 15-day delay window.
      // Once the 15-day delay passes, their identity and trade levels are released.
      const createdMs = row.created_at ? new Date(String(row.created_at)).getTime() : Number.NaN;
      const closedAtMs = row.updated_at ? new Date(String(row.updated_at)).getTime() : createdMs;
      const isClosed = closed(row);
      const richDetails = row.rich_details && typeof row.rich_details === "object"
        ? row.rich_details as Record<string, any>
        : {};
      const evaluation = richDetails.evaluation && typeof richDetails.evaluation === "object"
        ? richDetails.evaluation as Record<string, unknown>
        : {};
      const exitReason = isClosed ? {
        exit_reason: evaluation.exit_reason || null,
        exit_reason_ar: evaluation.exit_reason_ar || null,
        exit_reason_en: evaluation.exit_reason_en || null,
      } : {};
      const fresh = !Number.isFinite(createdMs) || createdMs > cutoffTime;
      const isFreshClosed = !Number.isFinite(closedAtMs) || closedAtMs > cutoffTime;
      const highReturnPro = !isClosed && isHighReturn(row);
      const locked = delayedVisibility && !isClosed && ((!authenticated || fresh) || highReturnPro);
      if (locked) {
        const precision = toNumber(row.precision, 0);
        const score = (value: number) => Math.max(1, Math.min(10, Math.round(value)));
        const lastClose = toNumber(row.last_close, 0);
        const entryPrice = toNumber(row.entry_price, 0);
        const sinceRecommendationPct = entryPrice > 0 && lastClose > 0
          ? ((lastClose - entryPrice) / entryPrice) * 100
          : row.profit_loss_pct != null
            ? toNumber(row.profit_loss_pct, 0)
            : null;
        const stopLoss = toNumber(row.stop_loss, 0);
        const safetyRate = lastClose > 0 && stopLoss > 0
          ? score(10 - Math.abs((lastClose - stopLoss) / lastClose) * 20)
          : 5;
        return {
          id: row.id,
          locked: true,
          exchange: row.exchange || "EGX",
          signal: row.signal || "BUY",
          status: row.status || "open",
          precision,
          technical_score: score(precision * 10 - 0.5),
          fundamental_score: score(precision * 10 - 0.8),
          sentiment_score: score(precision * 10 - 1.2),
          safety_rate: safetyRate,
          profit_loss_pct: sinceRecommendationPct,
          high_return_pro: highReturnPro,
          recommendation_age_days: highReturnPro ? recommendationAgeDays(row) : null,
          created_at: row.created_at,
          delayed: true,
          snapshot_cutoff: cutoff,
        };
      }
      const closedLocked = delayedVisibility && isClosed && (fresh || isFreshClosed);
      if (closedLocked) {
        return {
          id: row.id,
          identity_locked: true,
          exchange: row.exchange || "EGX",
          status: row.status,
          precision: toNumber(row.precision, 0),
          profit_loss_pct: toNumber(row.profit_loss_pct, 0),
          high_return_pro: false,
          recommendation_age_days: null,
          created_at: row.created_at,
          updated_at: row.updated_at || row.created_at,
          delayed: false,
        };
      }
      return {
      ...(authenticated ? row : {
        id: row.id,
        symbol: row.symbol,
        exchange: row.exchange,
        name: row.name,
        is_public: row.is_public,
        created_at: row.created_at,
        ...(isClosed ? {
          status: row.status,
          updated_at: row.updated_at,
          entry_price: row.entry_price,
          exit_price: row.exit_price,
          profit_loss_pct: row.profit_loss_pct,
        } : {}),
        delayed: !isClosed,
        anonymous: true,
      }),
      sector: sectorMap.get(String(row.symbol)) || "General",
      year: row.created_at ? new Date(String(row.created_at)).getFullYear() : null,
      // Rows reaching this branch are visible now (Pro, or Free after the
      // 15-day delay); only rows returned by the locked branch are delayed.
      delayed: false,
      snapshot_cutoff: null,
      precision: authenticated ? toNumber(row.precision, 0) : null,
      // Locked rows returned above never carry quotes or analysis. Once the
      // delay expires, visible recommendations can safely include their data.
      last_close: toNumber(row.last_close, 0) > 0 ? toNumber(row.last_close, 0) : null,
      top_reasons: row.top_reasons,
      ...exitReason,
      };
    });

    return NextResponse.json(results, {
      headers: {
        // Visibility depends on the request's Supabase session. Never let a
        // CDN-shared response cross between anonymous and authenticated users.
        // Keep plan-specific responses private, but allow the same browser
        // tab to reuse the daily snapshot while navigating between tabs.
        "Cache-Control": "private, no-store, max-age=0, must-revalidate",
        "Vercel-Cache-Tag": DAILY_CACHE_TAGS.recommendations,
      },
    });
  } catch (error) {
    console.error("ai_bot recommendations error:", error);
    return NextResponse.json([], { status: 200 });
  }
}
