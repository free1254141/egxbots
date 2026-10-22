import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { hasActiveProSubscription, planLimits } from "@/lib/ai/plan-gate";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

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
    } catch (e) {
      serviceClient = supabase;
    }

    const clientForData = serviceClient || supabase;

    // Fetch subscription first — we need current_period_start to determine the
    // correct quota window for PRO users who upgraded mid-month.
    const subResult = await clientForData
      .from("subscriptions")
      .select("id, plan_id, status, current_period_start, current_period_end, created_at")
      .eq("user_id", user.id)
      .eq("status", "active")
      .order("current_period_end", { ascending: false })
      .limit(5);

    const subRows = subResult.data;
    const subErr = subResult.error;
    if (subErr) console.warn("[api/user/quota] subscriptions query error:", subErr);

    // Derive plan status first — needed to choose the correct quota date window.
    const pro = hasActiveProSubscription(subRows || []);
    const activeSub = subRows?.[0];

    // For PRO users: count only messages since their current subscription period
    // started. This fixes the bug where users who upgraded Free → PRO mid-month
    // had all their Free-tier messages counted against the PRO monthly quota.
    const calMonthStart = new Date();
    calMonthStart.setDate(1);
    calMonthStart.setHours(0, 0, 0, 0);

    let effectiveMonthStart: Date;
    if (pro && activeSub?.current_period_start) {
      const subPeriodStart = new Date(activeSub.current_period_start);
      // Never go earlier than calendar month start (handles users PRO since last month)
      effectiveMonthStart = subPeriodStart > calMonthStart ? subPeriodStart : calMonthStart;
    } else {
      effectiveMonthStart = calMonthStart;
    }
    const monthStartStr = effectiveMonthStart.toISOString().split("T")[0];

    const [limitRowsRes, posResult] = await Promise.all([
      // Chat quota ledger: only from effective subscription start (not calendar month start)
      serviceClient
        .from("ai_chatbot_limits")
        .select("date, chat_count")
        .eq("user_id", user.id)
        .gte("date", monthStartStr),

      // Open portfolio positions
      supabase
        .from("positions")
        .select("symbol")
        .eq("user_id", user.id)
        .eq("status", "open"),
    ]);

    if (limitRowsRes.error) console.warn("[api/user/quota] limits count error:", limitRowsRes.error);
    if (posResult.error) console.warn("[api/user/quota] positions query error:", posResult.error);
    const planName = pro ? (activeSub?.plan_id === "lifetime" ? "lifetime" : "pro") : "free";
    const limits = planLimits(planName);

    // Derive chat quota
    const today = new Date().toISOString().split("T")[0];
    const todayLimitRow = (limitRowsRes.data || []).find((r: any) => r.date === today);
    const todayChatCount = Number(todayLimitRow?.chat_count || 0);
    const monthlyLimitsCount = (limitRowsRes.data || []).reduce(
      (acc: number, row: any) => acc + (Number(row.chat_count) || 0),
      0
    );
    const chatUsed = pro ? monthlyLimitsCount : todayChatCount;
    const chatLimit = pro ? limits.chat_messages_per_month : 5;
    const quotaPeriod = pro ? "monthly" : "daily";

    // Derive portfolio count
    const positionRows = posResult.data;
    const uniqueSymbols = new Set(
      (positionRows || []).map((p: any) => String(p.symbol || "").toUpperCase().trim())
    );
    const portfolioStocksCount = uniqueSymbols.size;

    const portfolioLimit = limits.portfolio_stocks;

    // 4. Founding member detection (first 100 distinct Pro / Lifetime members)
    let isFoundingMember = false;
    let foundingMemberNumber: number | null = null;
    if (pro) {
      const { data: allActiveSubs } = await serviceClient
        .from("subscriptions")
        .select("user_id, created_at")
        .eq("status", "active")
        .in("plan_id", ["pro", "lifetime", "pro_lifetime"])
        .order("created_at", { ascending: true })
        .limit(200);
      
      const uniqueFounderUids = Array.from(
        new Set((allActiveSubs || []).map((s: any) => s.user_id))
      ).slice(0, 100);

      const subIdx = uniqueFounderUids.indexOf(user.id);
      if (subIdx !== -1) {
        isFoundingMember = true;
        foundingMemberNumber = subIdx + 1;
      }
    }

    const isLifetime = activeSub?.plan_id === "lifetime" || activeSub?.plan_id === "pro_lifetime";

    return NextResponse.json({
      ok: true,
      plan: {
        id: planName,
        label: isLifetime ? "مدى الحياة (Lifetime)" : (pro ? "Pro" : "مجاني"),
        is_pro: pro,
        is_lifetime: isLifetime,
        status: activeSub?.status || "active",
        current_period_end: activeSub?.current_period_end || null,
        created_at: activeSub?.created_at || null,
        is_founding_member: isFoundingMember,
        founding_member_number: foundingMemberNumber,
      },
      quota: {
        chat_messages: {
          used: chatUsed,
          limit: chatLimit,
          remaining: Math.max(0, chatLimit - chatUsed),
          percent: Math.min(100, Math.round((chatUsed / Math.max(1, chatLimit)) * 100)),
          period: quotaPeriod,
        },
        portfolio_stocks: {
          used: portfolioStocksCount,
          limit: portfolioLimit,
          remaining: Math.max(0, portfolioLimit - portfolioStocksCount),
          percent: Math.min(100, Math.round((portfolioStocksCount / Math.max(1, portfolioLimit)) * 100)),
        },
        signals: {
          delay_days: limits.signal_delay_days,
          is_instant: limits.signal_delay_days === 0,
        },
      },
    }, {
      // Entitlement changes must be visible immediately after payment or an
      // admin adjustment. Never serve a stale Free/Pro result from HTTP caches.
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (err: any) {
    console.error("[api/user/quota] GET error:", err);
    return NextResponse.json(
      { ok: false, error: err?.message || "Internal server error" },
      { status: 500 }
    );
  }
}
