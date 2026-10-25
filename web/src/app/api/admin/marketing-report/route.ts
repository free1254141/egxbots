import { NextRequest, NextResponse } from "next/server";
import { requireAdmin } from "@/lib/admin-auth";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ReportRow = {
  channel: string;
  campaign: string;
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  bounced: number;
  converted: number;
};

const pct = (n: number, d: number) => (d > 0 ? Math.round((n / d) * 1000) / 10 : null);

/** Admin-only campaign performance report: sent/delivered/opened/clicked/converted per campaign. */
export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  const requested = Number(req.nextUrl.searchParams.get("days") || "30");
  const days = Math.min(90, Math.max(1, Number.isFinite(requested) ? Math.floor(requested) : 30));

  const service = getSupabaseServiceClient();
  const { data, error } = await service.rpc("marketing_campaign_report", { p_days: days });
  if (error) {
    console.warn("[admin/marketing-report] rpc failed:", error.code || "database_error");
    return NextResponse.json({ error: "report_unavailable" }, { status: 500 });
  }

  const rows = ((data || []) as ReportRow[]).map((r) => ({
    ...r,
    sent: Number(r.sent),
    delivered: Number(r.delivered),
    opened: Number(r.opened),
    clicked: Number(r.clicked),
    bounced: Number(r.bounced),
    converted: Number(r.converted),
  }));

  return NextResponse.json({
    days,
    campaigns: rows.map((r) => ({
      ...r,
      open_rate_pct: pct(r.opened, r.sent),
      click_rate_pct: pct(r.clicked, r.sent),
      conversion_rate_pct: pct(r.converted, r.sent),
    })),
  });
}
