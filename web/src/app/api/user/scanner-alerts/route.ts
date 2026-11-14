import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getMarketSupabaseClient, getSupabaseServiceClient, resolveRequestMarket } from "@/lib/supabase/route-data";
import { hasActiveProSubscription } from "@/lib/ai/plan-gate";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

interface ScannerPreferences {
  volume_surge: boolean;
  breakout: boolean;
  rsi_oversold: boolean;
  portfolio_watchlist: boolean;
  disclosures: boolean;
}

const DEFAULT_PREFERENCES: ScannerPreferences = {
  volume_surge: true,
  breakout: true,
  rsi_oversold: true,
  portfolio_watchlist: true,
  disclosures: true,
};

export async function GET(request: NextRequest) {
  try {
    const market = resolveRequestMarket(request);
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    let serviceClient: any = null;
    try {
      serviceClient = getSupabaseServiceClient();
    } catch {
      serviceClient = supabase;
    }
    const client = serviceClient || supabase;

    // Check Pro status and profile telegram status in parallel (if authenticated)
    let isPro = false;
    let telegramLinked = false;
    let profileRes: any = null;
    let preferences: ScannerPreferences = DEFAULT_PREFERENCES;

    if (user) {
      const [subRes, pRes, settingsRes] = await Promise.all([
        client
          .from("subscriptions")
          .select("plan_id, status, current_period_end")
          .eq("user_id", user.id)
          .in("status", ["active", "trialing"])
          .limit(1),
        client
          .from("profiles")
          .select("telegram_chat_id, notification_channel")
          .eq("id", user.id)
          .maybeSingle(),
        client
          .from("user_settings")
          .select("app_state")
          .eq("user_id", user.id)
          .maybeSingle(),
      ]);
      profileRes = pRes;
      isPro = hasActiveProSubscription(subRes?.data || []);
      telegramLinked = Boolean(profileRes?.data?.telegram_chat_id);
      const savedAlerts = settingsRes?.data?.app_state?.scanner_alerts || {};
      preferences = {
        volume_surge: savedAlerts.volume_surge ?? DEFAULT_PREFERENCES.volume_surge,
        breakout: savedAlerts.breakout ?? DEFAULT_PREFERENCES.breakout,
        rsi_oversold: savedAlerts.rsi_oversold ?? DEFAULT_PREFERENCES.rsi_oversold,
        portfolio_watchlist: savedAlerts.portfolio_watchlist ?? DEFAULT_PREFERENCES.portfolio_watchlist,
        disclosures: savedAlerts.disclosures ?? DEFAULT_PREFERENCES.disclosures,
      };
    }

    // Fetch scanner history, tracked signals & stats for calendar and signal tracker
    let scannerHistory: any[] = [];
    let lastScanData: any = null;
    let activeSignals: any[] = [];
    let closedSignals: any[] = [];
    let signalsKpis: any = null;

    try {
      let stateData: any = null;
      if (market === "tasi") {
        const saudiClient = getMarketSupabaseClient("tasi");
        const { data: cacheRow } = await saudiClient
          .from("market_cache")
          .select("payload")
          .eq("cache_key", "saudi_scanner_alerts_v1")
          .maybeSingle();
        const rawPayload = cacheRow?.payload;
        stateData = typeof rawPayload === "string" ? JSON.parse(rawPayload) : (rawPayload || null);
      } else {
        const { data: botState } = await client
          .from("bot_states")
          .select("state")
          .eq("bot_id", "scanner_alerts")
          .maybeSingle();
        stateData = botState?.state || null;
      }

      if (stateData) {
        scannerHistory = stateData.history || [];
        lastScanData = stateData.last_scan || null;
        if (stateData.active_signals && stateData.active_signals.length > 0) {
          activeSignals = stateData.active_signals;
          closedSignals = stateData.closed_signals || [];
          signalsKpis = stateData.signals_kpis || null;
        } else {
          const { deriveTrackedSignalsFromHistory } = await import("@/lib/scannerTradePlan");
          const derived = deriveTrackedSignalsFromHistory(scannerHistory, lastScanData);
          activeSignals = derived.activeSignals;
          closedSignals = derived.closedSignals;
          signalsKpis = derived.kpis;
        }

        // Strict Deduplication & Integrity Guard:
        const closedMap = new Map<string, any>();
        for (const s of (closedSignals || [])) {
          if (!s || !s.symbol) continue;
          const key = s.id || `${s.symbol}_${s.entry_date}_${s.scanner_type}_${s.exit_date || ""}`;
          if (!closedMap.has(key)) {
            closedMap.set(key, s);
          }
        }
        closedSignals = Array.from(closedMap.values());
        const closedKeys = new Set(closedSignals.map((s: any) => `${s.symbol}_${s.entry_date}_${s.scanner_type}`));

        const activeMap = new Map<string, any>();
        for (const s of (activeSignals || [])) {
          if (!s || !s.symbol) continue;
          const key = s.id || `${s.symbol}_${s.entry_date}_${s.scanner_type}`;
          if (!activeMap.has(key) && !closedKeys.has(key) && s.status === "active") {
            activeMap.set(key, s);
          }
        }
        activeSignals = Array.from(activeMap.values());
      }
    } catch (e) {
      console.warn("Could not load bot_states for user calendar:", e);
    }

// Preferences resolved above

    const cutoff15Days = new Date();
    cutoff15Days.setDate(cutoff15Days.getDate() - 15);
    const cutoffDateStr = cutoff15Days.toISOString().split("T")[0];

    const sanitizedActiveSignals = isPro
      ? activeSignals.map((s: any) => ({ ...s, is_locked: false }))
      : activeSignals.map((s: any) => ({
          ...s,
          symbol: s.symbol,
          name_ar: s.name_ar || s.symbol,
          name_en: s.name_en || s.symbol,
          sector: s.sector || null,
          entry_price: null,
          current_price: null,
          target_1: null,
          target_1_pct: null,
          target_2: null,
          target_2_pct: null,
          stop_loss: null,
          stop_loss_pct: null,
          highest_price: null,
          lowest_price: null,
          is_locked: true,
        }));

    const sanitizedHistory = isPro
      ? scannerHistory.map((item: any) => ({ ...item, is_locked: false }))
      : scannerHistory.map((item: any) => {
          const itemDate = item.timestamp ? item.timestamp.split("T")[0] : "";
          const isRecent = !itemDate || itemDate >= cutoffDateStr;
          if (!isRecent) return { ...item, is_locked: false };

          const stageResults = item.stage_results;
          if (!stageResults) return { ...item, is_locked: true };

          return {
            ...item,
            is_locked: true,
            stage_results: {
              volume_surge: (stageResults.volume_surge || []).map((s: any) => ({
                ...s,
                symbol: s.symbol,
          name_ar: s.name_ar || s.symbol,
          name_en: s.name_en || s.symbol,
          sector: s.sector || null,
                close: null,
                is_locked: true,
              })),
              breakout: (stageResults.breakout || []).map((s: any) => ({
                ...s,
                symbol: s.symbol,
          name_ar: s.name_ar || s.symbol,
          name_en: s.name_en || s.symbol,
          sector: s.sector || null,
                close: null,
                is_locked: true,
              })),
              rsi_oversold: (stageResults.rsi_oversold || []).map((s: any) => ({
                ...s,
                symbol: s.symbol,
          name_ar: s.name_ar || s.symbol,
          name_en: s.name_en || s.symbol,
          sector: s.sector || null,
                close: null,
                is_locked: true,
              })),
              disclosures: stageResults.disclosures || [],
            },
          };
        });

    return NextResponse.json({
      ok: true,
      is_pro: isPro,
      telegram_linked: telegramLinked,
      telegram_chat_id: profileRes?.data?.telegram_chat_id || null,
      preferences,
      history: sanitizedHistory,
      last_scan: lastScanData,
      active_signals: sanitizedActiveSignals,
      closed_signals: closedSignals,
      signals_kpis: signalsKpis,
    });
  } catch (err: any) {
    console.error("Error in GET /api/user/scanner-alerts:", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();
    const incoming = body.preferences || {};

    let serviceClient: any = null;
    try {
      serviceClient = getSupabaseServiceClient();
    } catch {
      serviceClient = supabase;
    }
    const client = serviceClient || supabase;

    // Check Pro status
    const { data: subData } = await client
      .from("subscriptions")
      .select("plan_id, status, current_period_end")
      .eq("user_id", user.id)
      .in("status", ["active", "trialing"])
      .limit(1);

    const isPro = hasActiveProSubscription(subData || []);
    if (!isPro) {
      return NextResponse.json(
        { error: "تنبيهات الإسكانر الفورية حصرية لمشتركي باقة Pro." },
        { status: 403 }
      );
    }

    // Read current user_settings
    const { data: settingsRow } = await client
      .from("user_settings")
      .select("app_state")
      .eq("user_id", user.id)
      .maybeSingle();

    const currentAppState = settingsRow?.app_state || {};
    const existingAlerts = currentAppState.scanner_alerts || {};
    const updatedScannerAlerts: ScannerPreferences = {
      volume_surge: Boolean(incoming.volume_surge ?? existingAlerts.volume_surge ?? DEFAULT_PREFERENCES.volume_surge),
      breakout: Boolean(incoming.breakout ?? existingAlerts.breakout ?? DEFAULT_PREFERENCES.breakout),
      rsi_oversold: Boolean(incoming.rsi_oversold ?? existingAlerts.rsi_oversold ?? DEFAULT_PREFERENCES.rsi_oversold),
      portfolio_watchlist: Boolean(incoming.portfolio_watchlist ?? existingAlerts.portfolio_watchlist ?? DEFAULT_PREFERENCES.portfolio_watchlist),
      disclosures: Boolean(incoming.disclosures ?? existingAlerts.disclosures ?? DEFAULT_PREFERENCES.disclosures),
    };

    const newAppState = {
      ...currentAppState,
      scanner_alerts: updatedScannerAlerts,
    };

    if (settingsRow) {
      await client
        .from("user_settings")
        .update({
          app_state: newAppState,
          updated_at: new Date().toISOString(),
        })
        .eq("user_id", user.id);
    } else {
      await client.from("user_settings").insert({
        user_id: user.id,
        app_state: newAppState,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    }

    return NextResponse.json({
      ok: true,
      preferences: updatedScannerAlerts,
    });
  } catch (err: any) {
    console.error("Error in POST /api/user/scanner-alerts:", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
