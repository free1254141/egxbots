import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { getCairoDateString, planLimits, resolveSubscriptionQuotaWindow } from "@/lib/ai/plan-gate";
import { isUnlimitedChatUser } from "@/lib/ai/server-secrets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

// Cache top-100 founding member IDs in module memory for 10 minutes to avoid
// scanning 200 subscription rows on every Pro quota check.
let cachedFounderUids: string[] | null = null;
let cachedFounderUidsExpiresAt = 0;
const FOUNDER_CACHE_TTL_MS = 10 * 60 * 1000;

async function getFounderUids(serviceClient: any): Promise<string[]> {
  const now = Date.now();
  if (cachedFounderUids && now < cachedFounderUidsExpiresAt) {
    return cachedFounderUids;
  }
  const { data: allActiveSubs } = await serviceClient
    .from("subscriptions")
    .select("user_id, created_at")
    .eq("status", "active")
    .in("plan_id", ["pro", "lifetime", "pro_lifetime"])
    .order("created_at", { ascending: true })
    .limit(200);

  const uniqueFounderUids = Array.from(
    new Set<string>((allActiveSubs || []).map((s: any) => String(s.user_id || "")).filter(Boolean))
  ).slice(0, 100);

  cachedFounderUids = uniqueFounderUids;
  cachedFounderUidsExpiresAt = now + FOUNDER_CACHE_TTL_MS;
  return uniqueFounderUids;
}

export async function GET(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient(req);
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
    const now = new Date();
    const calMonthStartStr = `${getCairoDateString(now).slice(0, 7)}-01`;

    // Execute all user-scoped queries in a single parallel round-trip
    // to minimize serverless wall-clock & active CPU time.
    const [subResult, limitRowsRes, posResult, trialRes, bonusRes, profileRes] = await Promise.all([
      clientForData
        .from("subscriptions")
        .select("id, plan_id, status, current_period_start, current_period_end, created_at")
        .eq("user_id", user.id)
        .in("status", ["active", "trialing"])
        .order("current_period_end", { ascending: false })
        .limit(5),
      serviceClient
        .from("ai_chatbot_limits")
        .select("date, chat_count")
        .eq("user_id", user.id)
        .gte("date", calMonthStartStr),
      supabase
        .from("positions")
        .select("symbol")
        .eq("user_id", user.id)
        .eq("status", "open"),
      clientForData
        .from("subscription_trials")
        .select("started_at, expires_at")
        .eq("user_id", user.id)
        .maybeSingle(),
      clientForData.rpc("get_chat_bonus_balance", { p_user_id: user.id }),
      clientForData
        .from("profiles")
        .select("telegram_chat_id")
        .eq("id", user.id)
        .maybeSingle(),
    ]);

    const subRows = subResult.data;
    const subErr = subResult.error;
    if (subErr) console.warn("[api/user/quota] subscriptions query error:", subErr);
    if (limitRowsRes.error) console.warn("[api/user/quota] limits count error:", limitRowsRes.error);
    if (posResult.error) console.warn("[api/user/quota] positions query error:", posResult.error);

    // Derive plan status & effective monthly window via the shared single-source helper.
    const isUnlimited = isUnlimitedChatUser(user);
    const quotaWin = resolveSubscriptionQuotaWindow(subRows || [], now);
    const pro = quotaWin.isPro || isUnlimited;
    const activeSub = quotaWin.activeSub;
    const monthStartStr = quotaWin.effectiveMonthStartStr;

    const planName = pro ? (activeSub?.plan_id === "lifetime" || isUnlimited ? "lifetime" : "pro") : "free";
    const limits = planLimits(planName);

    // Derive chat quota (filtered to effective subscription window start)
    const today = quotaWin.todayStr;
    const effectiveLimitRows = (limitRowsRes.data || []).filter((r: any) => String(r.date || "") >= monthStartStr);
    const todayLimitRow = effectiveLimitRows.find((r: any) => r.date === today);
    const todayChatCount = Number(todayLimitRow?.chat_count || 0);
    const monthlyLimitsCount = effectiveLimitRows.reduce(
      (acc: number, row: any) => acc + (Number(row.chat_count) || 0),
      0
    );
    const chatUsed = monthlyLimitsCount;
    const chatLimit = limits.chat_messages_per_month;
    const quotaPeriod = "monthly";

    // Derive portfolio count
    const positionRows = posResult.data;
    const uniqueSymbols = new Set(
      (positionRows || []).map((p: any) => String(p.symbol || "").toUpperCase().trim())
    );
    const portfolioStocksCount = uniqueSymbols.size;

    const portfolioLimit = limits.portfolio_stocks;

    // 4. Founding member detection (first 100 distinct Pro / Lifetime members, cached for 10m)
    let isFoundingMember = false;
    let foundingMemberNumber: number | null = null;
    if (pro) {
      const uniqueFounderUids = await getFounderUids(serviceClient);
      const subIdx = uniqueFounderUids.indexOf(user.id);
      if (subIdx !== -1) {
        isFoundingMember = true;
        foundingMemberNumber = subIdx + 1;
      }
    }

    const isLifetime = activeSub?.plan_id === "lifetime" || activeSub?.plan_id === "pro_lifetime";

    const hasUsedTrial = Boolean(trialRes.data);
    const isTrialActive = trialRes.data?.expires_at
      ? new Date(trialRes.data.expires_at).getTime() > Date.now()
      : false;
    const isTrial = activeSub?.status === "trialing" || activeSub?.provider === "trial" || isTrialActive;
    const bonusBalance = Number(bonusRes.data || 0);
    const telegramLinked = Boolean(profileRes.data?.telegram_chat_id);
    const trialEligible = !hasUsedTrial && !pro;

    return NextResponse.json({
      ok: true,
      plan: {
        id: planName,
        label: isLifetime ? "مدى الحياة (Lifetime)" : (isTrial ? "تجربة Pro مجانية" : (pro ? "Pro" : "مجاني")),
        is_trial: isTrial,
        trial_eligible: trialEligible,
        is_pro: pro,
        is_lifetime: isLifetime,
        status: pro ? (activeSub?.status || "active") : (activeSub ? "canceled" : "none"),
        current_period_end: activeSub?.current_period_end || null,
        created_at: activeSub?.created_at || null,
        is_founding_member: isFoundingMember,
        founding_member_number: foundingMemberNumber,
        bonus_credits: bonusBalance,
        telegram_linked: telegramLinked,
      },
      quota: {
        chat_messages: {
          used: chatUsed,
          limit: chatLimit,
          bonus_credits: bonusBalance,
          remaining: Math.max(0, chatLimit - chatUsed) + (pro ? 0 : bonusBalance),
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
