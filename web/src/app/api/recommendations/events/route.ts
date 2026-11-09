import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { getViewerContext } from "@/lib/supabase/viewer-context";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const PUBLIC_EVENT_TYPES = [
  "recommendation_closed",
  "recommendation_stale",
  "target_or_stop_adjusted",
];

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function GET(request: NextRequest) {
  const requestedLimit = Number(request.nextUrl.searchParams.get("limit") || 100);
  const limit = Math.min(Math.max(Number.isFinite(requestedLimit) ? requestedLimit : 100, 1), 300);
  const monthParam = request.nextUrl.searchParams.get("month") || "";

  try {
    const { authenticated, pro } = await getViewerContext(request);
    if (!authenticated) return NextResponse.json({ detail: "Pro subscription required" }, { status: 401 });
    if (!pro) return NextResponse.json({ detail: "Pro subscription required" }, { status: 403 });
    const supabase = getSupabaseServiceClient({ cacheMarketData: true });

    let query = supabase
      .from("recommendation_events")
      .select("id,recommendation_id,event_type,old_values,new_values,price_at_event,source,telegram_status,created_at")
      .in("event_type", PUBLIC_EVENT_TYPES)
      .not("recommendation_id", "is", null);

    if (monthParam && /^\d{4}-\d{2}$/.test(monthParam)) {
      const startIso = `${monthParam}-01T00:00:00Z`;
      const [year, month] = monthParam.split("-").map(Number);
      const nextMonthIso = new Date(Date.UTC(year, month, 1)).toISOString();
      query = query.gte("created_at", startIso).lt("created_at", nextMonthIso);
    }

    const { data: events, error: eventError } = await query
      .order("created_at", { ascending: false })
      .limit(limit);

    if (eventError) throw eventError;
    const visibleEvents = events || [];
    const recommendationIds = [...new Set(visibleEvents.map((event: any) => String(event.recommendation_id)))];
    if (!recommendationIds.length) {
      return NextResponse.json(
        { events: [], tracked_recommendation_ids: [] },
        { headers: { "Cache-Control": "private, no-store" } },
      );
    }

    const { data: recommendations, error: recommendationError } = await supabase
      .from("scan_results")
      .select("id,symbol,exchange,name,signal,status,is_public,entry_price,target_price,stop_loss,exit_price,profit_loss_pct,logo_url,created_at")
      .in("id", recommendationIds)
      .eq("is_public", true);

    if (recommendationError) throw recommendationError;
    const byId = new Map<string, any>(
      (recommendations || []).map((row: any): [string, any] => [String(row.id), row]),
    );

    const trackedRecommendationIds = [...new Set(
      visibleEvents
        .filter((event: any) => event.event_type === "recommendation_closed" || event.event_type === "recommendation_stale")
        .filter((event: any) => event.telegram_status === "sent")
        .map((event: any) => String(event.recommendation_id))
        .filter((id: string) => byId.has(id)),
    )];
    const sanitized = visibleEvents.filter((event: any) => event.telegram_status === "sent").flatMap((event: any) => {
      const recommendation = byId.get(String(event.recommendation_id));
      if (!recommendation) return [];
      const oldValues = event.old_values && typeof event.old_values === "object" ? event.old_values : {};
      const newValues = event.new_values && typeof event.new_values === "object" ? event.new_values : {};
      const closedOn = newValues.rich_details?.evaluation?.closed_on;
      const occurredAt = event.event_type === "recommendation_closed" &&
        typeof closedOn === "string" && /^\d{4}-\d{2}-\d{2}$/.test(closedOn)
          ? `${closedOn}T12:00:00Z`
          : event.created_at;
      return [{
        id: String(event.id),
        recommendation_id: String(event.recommendation_id),
        event_type: event.event_type,
        occurred_at: occurredAt,
        price_at_event: numeric(event.price_at_event),
        source: event.source,
        symbol: recommendation.symbol,
        exchange: recommendation.exchange,
        name: recommendation.name,
        signal: recommendation.signal,
        logo_url: recommendation.logo_url,
        created_at: recommendation.created_at,
        status: newValues.status || recommendation.status,
        entry_price: numeric(oldValues.entry_price ?? recommendation.entry_price),
        exit_price: numeric(newValues.exit_price ?? recommendation.exit_price ?? event.price_at_event),
        profit_loss_pct: numeric(newValues.profit_loss_pct ?? recommendation.profit_loss_pct),
        exit_reason: newValues.rich_details?.evaluation?.exit_reason || null,
        exit_reason_ar: newValues.rich_details?.evaluation?.exit_reason_ar || null,
        exit_reason_en: newValues.rich_details?.evaluation?.exit_reason_en || null,
        old_target: numeric(oldValues.target_price),
        new_target: numeric(newValues.target_price),
        old_stop: numeric(oldValues.stop_loss),
        new_stop: numeric(newValues.stop_loss),
        target_price: numeric(newValues.target_price ?? recommendation.target_price),
        stop_loss: numeric(newValues.stop_loss ?? recommendation.stop_loss),
        adjustment_type: newValues.adjustment_type || null,
      }];
    });

    return NextResponse.json(
      { events: sanitized, tracked_recommendation_ids: trackedRecommendationIds },
      { headers: { "Cache-Control": "private, max-age=300, stale-while-revalidate=600" } },
    );
  } catch (error) {
    console.error("[RECOMMENDATION_EVENTS_API] Failed to load sent events", error);
    return NextResponse.json(
      { detail: "Recommendation event history is temporarily unavailable." },
      { status: 503, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}
