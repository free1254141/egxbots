import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import {
  getAdminConfig,
  saveAdminConfig,
  executeScannerEngine,
  AdminScannerConfig,
} from "@/lib/scannerAlertsEngine";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// ── GET Handler: Fetch current admin scanner config & stats ──
export async function GET() {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    // Verify session
    if (authError || !user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const serviceClient = getSupabaseServiceClient();
    const config = await getAdminConfig(serviceClient);

    // Count linked pro subscribers ready to receive
    const [subRes, profileRes] = await Promise.all([
      serviceClient.from("subscriptions").select("user_id").eq("status", "active"),
      serviceClient.from("profiles").select("id, telegram_chat_id").not("telegram_chat_id", "is", null),
    ]);

    const activeProUids = new Set((subRes.data || []).map((s: any) => s.user_id));
    const linkedProCount = (profileRes.data || []).filter((p: any) => activeProUids.has(p.id)).length;

    return NextResponse.json({
      ok: true,
      config,
      stats: {
        active_pro_subscribers: activeProUids.size,
        linked_telegram_subscribers: linkedProCount,
        readiness_pct: activeProUids.size > 0 ? Math.round((linkedProCount / activeProUids.size) * 100) : 0,
      },
    });
  } catch (err: any) {
    console.error("GET /api/admin/scanner-alerts error:", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// ── POST Handler: Save settings or trigger live scan now ──
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
    const { action } = body;
    const serviceClient = getSupabaseServiceClient();
    const config = await getAdminConfig(serviceClient);

    if (action === "save_settings") {
      const updatedConfig: AdminScannerConfig = {
        ...config,
        is_active: Boolean(body.is_active ?? config.is_active),
        interval_minutes: Number(body.interval_minutes ?? config.interval_minutes),
        market_hours_only: Boolean(body.market_hours_only ?? config.market_hours_only),
        scanners_enabled: {
          ...config.scanners_enabled,
          ...(body.scanners_enabled || {}),
        },
      };

      await saveAdminConfig(updatedConfig, serviceClient);
      return NextResponse.json({ ok: true, config: updatedConfig });
    }

    if (action === "run_scan_now") {
      const engineResult = await executeScannerEngine({
        trigger: `Manual (${user.email || "Admin"})`,
        forceMarketHours: true, // Allow manual test run anytime from Admin UI
        forceDispatch: Boolean(body.force_dispatch),
      });

      const updated = await getAdminConfig(serviceClient);

      return NextResponse.json({
        ok: true,
        scan_result: updated.last_scan,
        duration_ms: engineResult.duration_ms,
        symbols_scanned: engineResult.total_scanned,
        alerts_dispatched: engineResult.alerts_dispatched,
        fresh_matches: engineResult.fresh_matches,
      });
    }

    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  } catch (err: any) {
    console.error("POST /api/admin/scanner-alerts error:", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
