import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { hasActiveProSubscription } from "@/lib/ai/plan-gate";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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

export async function GET() {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    let serviceClient: any = null;
    try {
      serviceClient = getSupabaseServiceClient();
    } catch {
      serviceClient = supabase;
    }
    const client = serviceClient || supabase;

    // Check Pro status and profile telegram status in parallel
    const [subRes, profileRes, settingsRes] = await Promise.all([
      client
        .from("subscriptions")
        .select("plan_id, status, current_period_end")
        .eq("user_id", user.id)
        .eq("status", "active")
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

    const isPro = hasActiveProSubscription(subRes?.data || []);
    const telegramLinked = Boolean(profileRes?.data?.telegram_chat_id);

    // Fetch scanner history, tracked signals & stats for calendar and signal tracker
    let scannerHistory: any[] = [];
    let lastScanData: any = null;
    let activeSignals: any[] = [];
    let closedSignals: any[] = [];
    let signalsKpis: any = null;

    try {
      const { data: botState } = await client
        .from("bot_states")
        .select("state")
        .eq("bot_id", "scanner_alerts")
        .maybeSingle();
      if (botState?.state) {
        scannerHistory = botState.state.history || [];
        lastScanData = botState.state.last_scan || null;
        if (botState.state.active_signals && botState.state.active_signals.length > 0) {
          activeSignals = botState.state.active_signals;
          closedSignals = botState.state.closed_signals || [];
          signalsKpis = botState.state.signals_kpis || null;
        } else {
          const { deriveTrackedSignalsFromHistory } = await import("@/lib/scannerTradePlan");
          const derived = deriveTrackedSignalsFromHistory(scannerHistory, lastScanData);
          activeSignals = derived.activeSignals;
          closedSignals = derived.closedSignals;
          signalsKpis = derived.kpis;
        }
      }
    } catch (e) {
      console.warn("Could not load bot_states for user calendar:", e);
    }

    const savedAlerts = settingsRes?.data?.app_state?.scanner_alerts || {};
    const preferences: ScannerPreferences = {
      volume_surge: savedAlerts.volume_surge ?? DEFAULT_PREFERENCES.volume_surge,
      breakout: savedAlerts.breakout ?? DEFAULT_PREFERENCES.breakout,
      rsi_oversold: savedAlerts.rsi_oversold ?? DEFAULT_PREFERENCES.rsi_oversold,
      portfolio_watchlist: savedAlerts.portfolio_watchlist ?? DEFAULT_PREFERENCES.portfolio_watchlist,
      disclosures: savedAlerts.disclosures ?? DEFAULT_PREFERENCES.disclosures,
    };

    return NextResponse.json({
      ok: true,
      is_pro: isPro,
      telegram_linked: telegramLinked,
      telegram_chat_id: profileRes?.data?.telegram_chat_id || null,
      preferences,
      history: scannerHistory,
      last_scan: lastScanData,
      active_signals: activeSignals,
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
      .eq("status", "active")
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
