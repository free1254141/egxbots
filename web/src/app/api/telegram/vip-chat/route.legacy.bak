import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient, getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { extractExplicitSymbols, runPipeline } from "@/lib/ai/pipeline";
import { getDeepSeekApiKey, getNvidiaApiKeys } from "@/lib/ai/server-secrets";
import {
    getCairoDateString,
    planLimits,
    resolveSubscriptionQuotaWindow,
} from "@/lib/ai/plan-gate";
import { detectPortfolioIntent, normalizeArabicIntent } from "@/lib/ai/intent-policy";
import { SessionState, SessionSummary } from "@/lib/ai/types";
import {
    buildAnalysisCacheKey,
    getVipAnalysisCache,
    personalizeCachedAnalysis,
    setVipAnalysisCache,
} from "@/lib/ai/analysis-cache";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const ADMIN_TG_IDS = new Set(["5149631436"]);

function isAuthorizedRequest(req: NextRequest): boolean {
    const adminKey =
        req.headers.get("x-admin-key") ||
        req.headers.get("authorization")?.replace("Bearer ", "");
    const expectedKey = process.env.ADMIN_SECRET_KEY?.trim() || "";
    const host = req.headers.get("host") || "";
    const isLocal = host.includes("localhost") || host.includes("127.0.0.1");
    return Boolean(isLocal || (expectedKey && adminKey && adminKey === expectedKey));
}

function isTopicRecommendationsQuery(message: string): boolean {
    const raw = (message || "").trim();
    if (!raw) return false;
    const lower = raw.toLowerCase().replace(/[@/]/g, "").trim();
    if (lower === "recs" || lower === "recommendations" || lower === "signals" || lower === "daily") {
        return true;
    }
    const norm = normalizeArabicIntent(raw);
    const hasRecKw =
        /(?:توصي[اهت]|توصياتك|فرص\s*(?:الشراء|اليوم|السوق|المتاح[اه])|اشار[اه]ت?\s*(?:الشراء|الدخول)|(?:اسهم|الاسهم)\s*(?:المرشح[اه]|المقترح[اه])\s*(?:للشراء)?|اشتري\s*ايه|انصحني\s*اشتري|رشحلي\s*سهم|افضل\s*سهم\s*للشراء)/.test(norm) ||
        /\b(?:recs?|recommendations?|buy\s*signals?)\b/i.test(raw);
    if (!hasRecKw) return false;
    const symbols = extractExplicitSymbols(raw);
    if (symbols.length > 0) return false;
    return true;
}

function deterministicSessionUuid(seed: string): string {
    let h1 = 0xdeadbeef ^ seed.length;
    let h2 = 0x41c6ce57 ^ seed.length;
    let h3 = 0x9e3779b9 ^ seed.length;
    let h4 = 0x85ebca6b ^ seed.length;
    for (let i = 0; i < seed.length; i++) {
        const ch = seed.charCodeAt(i);
        h1 = Math.imul(h1 ^ ch, 2654435761);
        h2 = Math.imul(h2 ^ ch, 1597334677);
        h3 = Math.imul(h3 ^ ch, 2246822507);
        h4 = Math.imul(h4 ^ ch, 3266489909);
    }
    const hex = (n: number) => (n >>> 0).toString(16).padStart(8, "0");
    const raw = `${hex(h1)}${hex(h2)}${hex(h3)}${hex(h4)}`;
    return `${raw.slice(0, 8)}-${raw.slice(8, 12)}-4${raw.slice(13, 16)}-a${raw.slice(17, 20)}-${raw.slice(20, 32)}`;
}

interface ResolvedTelegramUser {
    telegramUserId: number;
    telegramUsername: string;
    linkedUserId: string | null;
    displayName: string;
    isPro: boolean;
    isAdmin: boolean;
    used: number;
    limit: number;
    remaining: number;
    period: "daily" | "monthly";
    stateRow: any | null;
}

async function resolveTelegramUser(
    supabase: any,
    telegramUserId: number,
    telegramUsername: string
): Promise<ResolvedTelegramUser> {
    const tgIdStr = String(telegramUserId);
    const isAdmin = ADMIN_TG_IDS.has(tgIdStr);
    const todayCairo = getCairoDateString();

    // 1. Load telegram_vip_chat_state row + look up linked profiles and invites in parallel
    const [stateRes, profilesRes, inviteRes] = await Promise.all([
        supabase
            .from("telegram_vip_chat_state")
            .select("telegram_user_id, telegram_username, linked_user_id, quota_date, daily_count, session_state, session_summary, chat_history, pending_prompt")
            .eq("telegram_user_id", telegramUserId)
            .maybeSingle(),
        supabase
            .from("profiles")
            .select("id, display_name, username, updated_at")
            .eq("telegram_chat_id", tgIdStr)
            .limit(10),
        supabase
            .from("pro_telegram_invites")
            .select("user_id")
            .eq("vip_telegram_user_id", telegramUserId)
            .limit(10),
    ]);

    const stateRow = stateRes?.data || null;
    const testMode = stateRow?.session_state?.test_mode || null;

    // Collect all candidate user IDs linked to this Telegram account
    const candidateUserIds: string[] = Array.from(
        new Set([
            ...(profilesRes?.data || []).map((r: any) => r.id),
            ...(inviteRes?.data || []).map((r: any) => r.user_id),
            stateRow?.linked_user_id,
        ].filter(Boolean))
    );

    // If candidate IDs exist, check for active or trialing subscriptions across all candidates!
    let activeSubRow: any = null;
    if (candidateUserIds.length > 0) {
        const subRes = await supabase
            .from("subscriptions")
            .select("user_id, plan_id, status, current_period_start, current_period_end")
            .in("user_id", candidateUserIds)
            .in("status", ["active", "trialing"])
            .order("current_period_end", { ascending: false })
            .limit(10);

        const activeSubs = subRes?.data || [];
        if (activeSubs.length > 0) {
            activeSubRow = activeSubs[0];
        }
    }

    // Determine the true linked user: prefer active subscriber, else most recent profile, else invite/state
    const linkedUserId: string | null =
        activeSubRow?.user_id ||
        (profilesRes?.data && profilesRes.data[0]?.id) ||
        (inviteRes?.data && inviteRes.data[0]?.user_id) ||
        stateRow?.linked_user_id ||
        null;

    // If we resolved a linked user that differs from stateRow, update stateRow in the background so it stays in sync
    if (linkedUserId && stateRow?.linked_user_id !== linkedUserId) {
        supabase
            .from("telegram_vip_chat_state")
            .update({ linked_user_id: linkedUserId })
            .eq("telegram_user_id", telegramUserId)
            .then(() => {});
    }

    const matchedProfile = (profilesRes?.data || []).find((p: any) => p.id === linkedUserId) || (profilesRes?.data && profilesRes.data[0]);
    const displayName =
        matchedProfile?.display_name ||
        matchedProfile?.username ||
        telegramUsername ||
        "المستثمر";

    let isPro = isAdmin;
    let used = 0;
    let limit = 10;
    let period: "daily" | "monthly" = "monthly";

    if (linkedUserId) {
        const quotaWin = activeSubRow
            ? resolveSubscriptionQuotaWindow([activeSubRow])
            : { isPro: false, effectiveMonthStartStr: todayCairo.slice(0, 7) + "-01" };

        if (quotaWin.isPro || isAdmin) {
            isPro = true;
        }

        const limitsRes = await supabase
            .from("ai_chatbot_limits")
            .select("date, chat_count")
            .eq("user_id", linkedUserId)
            .gte("date", quotaWin.effectiveMonthStartStr);

        const limitRows = limitsRes?.data || [];
        const monthlyCount = limitRows.reduce(
            (acc: number, r: any) => acc + (Number(r.chat_count) || 0),
            0
        );

        if (isPro) {
            period = "monthly";
            limit = planLimits("pro").chat_messages_per_month || 350;
            used = monthlyCount;
        } else {
            period = "monthly";
            limit = planLimits("free").chat_messages_per_month || 10;
            used = monthlyCount;
        }
    } else {
        // Unlinked Telegram group user -> Free plan (10 messages allowance)
        const rowDate = stateRow?.quota_date ? String(stateRow.quota_date) : "";
        const todayCount = rowDate === todayCairo ? Number(stateRow?.daily_count || 0) : 0;
        isPro = isAdmin;
        period = "monthly";
        limit = isPro ? 350 : 10;
        used = todayCount;
    }

    // Apply optional simulation test_mode (for testing quota exhaustion or free tier)
    if (testMode === "limit_reached") {
        isPro = false;
        period = "monthly";
        limit = 10;
        used = 10;
    } else if (testMode === "free_plan") {
        isPro = false;
        period = "monthly";
        limit = 10;
        used = Math.min(9, used);
    }

    const remaining = Math.max(0, limit - used);

    return {
        telegramUserId,
        telegramUsername,
        linkedUserId,
        displayName,
        isPro,
        isAdmin,
        used,
        limit,
        remaining,
        period,
        stateRow,
    };
}

export async function POST(req: NextRequest) {
    if (!isAuthorizedRequest(req)) {
        return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    let supabase: any;
    try {
        supabase = getSupabaseServiceClient();
    } catch {
        supabase = getSupabaseClient();
    }

    try {
        const body = await req.json();
        const action = String(body.action || "chat").trim();
        const telegramUserId = Number(body.telegram_user_id || 0);
        const telegramUsername = String(body.telegram_username || "مستخدم تليجرام").trim();

        if (!telegramUserId || !Number.isFinite(telegramUserId)) {
            return NextResponse.json(
                { ok: false, error: "Valid telegram_user_id is required" },
                { status: 400 }
            );
        }

        const userInfo = await resolveTelegramUser(supabase, telegramUserId, telegramUsername);
        const todayCairo = getCairoDateString();

        // 1. Action: check_quota or set_pending_prompt
        if (action === "check_quota") {
            return NextResponse.json({
                ok: true,
                linked: Boolean(userInfo.linkedUserId),
                user_id: userInfo.linkedUserId,
                display_name: userInfo.displayName,
                is_pro: userInfo.isPro,
                used: userInfo.used,
                limit: userInfo.limit,
                remaining: userInfo.remaining,
                period: userInfo.period,
                pending_prompt: userInfo.stateRow?.pending_prompt || null,
            });
        }

        if (action === "set_pending_prompt") {
            const promptMode = body.prompt_mode ? String(body.prompt_mode) : null;
            const pendingPayload = promptMode
                ? {
                      mode: promptMode,
                      expires_at: Date.now() + 5 * 60 * 1000,
                  }
                : null;

            await supabase.from("telegram_vip_chat_state").upsert(
                {
                    telegram_user_id: telegramUserId,
                    telegram_username: telegramUsername,
                    linked_user_id: userInfo.linkedUserId,
                    quota_date:
                        userInfo.stateRow?.quota_date === todayCairo
                            ? todayCairo
                            : todayCairo,
                    daily_count:
                        userInfo.stateRow?.quota_date === todayCairo
                            ? Number(userInfo.stateRow?.daily_count || 0)
                            : 0,
                    session_state: userInfo.stateRow?.session_state || {},
                    session_summary: userInfo.stateRow?.session_summary || {},
                    chat_history: userInfo.stateRow?.chat_history || [],
                    pending_prompt: pendingPayload,
                    updated_at: new Date().toISOString(),
                },
                { onConflict: "telegram_user_id" }
            );

            return NextResponse.json({
                ok: true,
                linked: Boolean(userInfo.linkedUserId),
                is_pro: userInfo.isPro,
                used: userInfo.used,
                limit: userInfo.limit,
                remaining: userInfo.remaining,
                period: userInfo.period,
                pending_prompt: pendingPayload,
            });
        }

        if (action === "set_test_mode") {
            const newTestMode = body.test_mode ? String(body.test_mode) : null;
            const currentSessionState = { ...(userInfo.stateRow?.session_state || {}) };
            if (newTestMode && newTestMode !== "normal") {
                currentSessionState.test_mode = newTestMode;
            } else {
                delete currentSessionState.test_mode;
            }

            await supabase.from("telegram_vip_chat_state").upsert(
                {
                    telegram_user_id: telegramUserId,
                    telegram_username: telegramUsername,
                    linked_user_id: userInfo.linkedUserId,
                    quota_date: todayCairo,
                    daily_count:
                        userInfo.stateRow?.quota_date === todayCairo
                            ? Number(userInfo.stateRow?.daily_count || 0)
                            : 0,
                    session_state: currentSessionState,
                    session_summary: userInfo.stateRow?.session_summary || {},
                    chat_history: userInfo.stateRow?.chat_history || [],
                    pending_prompt: null,
                    updated_at: new Date().toISOString(),
                },
                { onConflict: "telegram_user_id" }
            );

            const updatedInfo = await resolveTelegramUser(supabase, telegramUserId, telegramUsername);
            return NextResponse.json({
                ok: true,
                test_mode: newTestMode || "normal",
                is_pro: updatedInfo.isPro,
                used: updatedInfo.used,
                limit: updatedInfo.limit,
                remaining: updatedInfo.remaining,
                period: updatedInfo.period,
            });
        }

        // 2. Action: chat
        const rawMessage = typeof body.message === "string" ? body.message.trim() : "";
        if (!rawMessage) {
            return NextResponse.json({ ok: false, error: "Message is required" }, { status: 400 });
        }

        const chatSource = body.chat_source === "telegram_private" ? "telegram_private" : (body.chat_source === "telegram_b2b" ? "telegram_b2b" : "telegram_topic");
        const bypassQuota = Boolean(body.bypass_quota || chatSource === "telegram_b2b");

        // Restriction: Public Telegram topic (Artoro topic in free group) must NEVER return open recommendations
        if (chatSource === "telegram_topic" && isTopicRecommendationsQuery(rawMessage)) {
            return NextResponse.json({
                ok: true,
                reply:
                    "🔒 **توصيات الشراء اللحظية حصرية لمشتركي PRO في الشات الخاص أو الموقع!**\n\n" +
                    "حفاظاً على سرية وعدالة إشارات التداول لجميع المشتركين، **لا تُعرض توصيات الشراء المفتوحة في هذه الغرفة العامة**.\n\n" +
                    "📌 **للحصول على توصيات الشراء اللحظية فور صدورها:**\n" +
                    "1️⃣ **تحدث مع أرتورو في شات خاص بخصوصية تامة:**\n" +
                    "راسل البوت مباشرةً: [@egxbots_bot](https://t.me/egxbots_bot?start=artoro_chat)\n\n" +
                    "2️⃣ **أو عبر ماسح الذكاء الاصطناعي على الموقع:**\n" +
                    "[egxbots.com/scanner/ai](https://egxbots.com/scanner/ai)\n\n" +
                    "💎 *إذا كنت مشتركاً في باقة PRO، افتح الشات الخاص مع البوت وستظهر لك كافة التوصيات المفتوحة فوراً وبسرية كاملة.*",
                tables: [],
                tools: { results: [], formattedText: "" },
                linked: Boolean(userInfo.linkedUserId),
                display_name: userInfo.displayName,
                is_pro: userInfo.isPro,
                used: userInfo.used,
                limit: userInfo.limit,
                remaining: userInfo.remaining,
                period: userInfo.period,
            });
        }

        // Check portfolio tool requirement for unlinked users (requires linking account to read user's positions)
        if (!userInfo.linkedUserId && detectPortfolioIntent(rawMessage)) {
            return NextResponse.json(
                {
                    ok: false,
                    error_code: "ACCOUNT_LINK_REQUIRED",
                    linked: false,
                    display_name: userInfo.displayName,
                    is_pro: false,
                    used: userInfo.used,
                    limit: userInfo.limit,
                    remaining: userInfo.remaining,
                    period: userInfo.period,
                    detail: "لتحليل محفظتك الاستثمارية، يرجى ربط حسابك في الموقع بالبوت أولاً من صفحة البروفايل.",
                },
                { status: 403 }
            );
        }

        // Check quota limit before running pipeline
        if (!userInfo.isAdmin && !bypassQuota && userInfo.remaining <= 0) {
            return NextResponse.json(
                {
                    ok: false,
                    error_code: "LIMIT_REACHED",
                    linked: Boolean(userInfo.linkedUserId),
                    display_name: userInfo.displayName,
                    is_pro: userInfo.isPro,
                    used: userInfo.used,
                    limit: userInfo.limit,
                    remaining: 0,
                    period: userInfo.period,
                    detail: userInfo.isPro
                        ? `لقد استهلكت باقة رسائلك الشهرية (${userInfo.limit}/${userInfo.limit}).`
                        : `لقد استهلكت باقتك المجانية (${userInfo.limit}/${userInfo.limit} أسئلة). اشترك في باقة PRO للحصول على 350 سؤال شهرياً وتوصيات لحظية!`,
                },
                { status: 429 }
            );
        }

        // Maintenance / Under-Development Mode (only when explicitly enabled via AI_CHAT_MAINTENANCE_MODE === "true")
        if (process.env.AI_CHAT_MAINTENANCE_MODE === "true" && !process.env.JEST_WORKER_ID && process.env.NODE_ENV !== "test") {
            return NextResponse.json({
                ok: true,
                reply:
                    "🛠️ **المساعد الذكي (ARTORO AI) تحت التطوير والتحديث حالياً**\n\n" +
                    "نقوم حالياً بإجراء تحديثات وترقية لمحرك الذكاء الاصطناعي لتحسين سرعة ودقة التحليل الفني والمالي.\n" +
                    "✅ **لم يتم خصم أي سؤال من رصيدك.** سيعود أرتورو للعمل بكامل طاقته قريباً جداً!",
                tables: [],
                linked: Boolean(userInfo.linkedUserId),
                display_name: userInfo.displayName,
                is_pro: userInfo.isPro,
                used: userInfo.used,
                limit: userInfo.limit,
                remaining: userInfo.remaining,
                period: userInfo.period,
            });
        }

        // Atomically consume 1 quota unit (skipped for B2B queries where group quota is handled by B2B RPC)
        let newUsed = bypassQuota ? userInfo.used : userInfo.used + 1;
        if (!userInfo.isAdmin && !bypassQuota && userInfo.linkedUserId) {
            const effectiveDailyLimit = userInfo.isPro ? Math.max(350, userInfo.limit) : userInfo.limit;
            const { data: quotaRows, error: quotaErr } = await supabase.rpc(
                "consume_ai_chat_quota",
                {
                    p_user_id: userInfo.linkedUserId,
                    p_date: todayCairo,
                    p_limit: effectiveDailyLimit,
                }
            );
            if (!quotaErr) {
                const q = Array.isArray(quotaRows) ? quotaRows[0] : quotaRows;
                if (q && !q.allowed) {
                    return NextResponse.json(
                        {
                            ok: false,
                            error_code: "LIMIT_REACHED",
                            linked: true,
                            display_name: userInfo.displayName,
                            is_pro: userInfo.isPro,
                            used: userInfo.limit,
                            limit: userInfo.limit,
                            remaining: 0,
                            period: userInfo.period,
                        },
                        { status: 429 }
                    );
                }
            }
        }

        const newRemaining = userInfo.isAdmin ? 9999 : Math.max(0, userInfo.limit - newUsed);

        // Restore session state, summary, and history from telegram_vip_chat_state
        const savedState = (userInfo.stateRow?.session_state || {}) as Partial<SessionState>;
        const sessionState: SessionState = {
            current_symbol: savedState.current_symbol || null,
            last_symbols: Array.isArray(savedState.last_symbols) ? savedState.last_symbols : [],
            summary: savedState.summary || null,
            current_sector: savedState.current_sector || null,
            language: "ar",
            persisted: true,
        };

        const explicitSymbols = extractExplicitSymbols(rawMessage);
        if (explicitSymbols.length > 0) {
            sessionState.current_symbol = explicitSymbols[0];
            sessionState.last_symbols = explicitSymbols;
        }

        const sessionSummary: SessionSummary | null =
            userInfo.stateRow?.session_summary &&
            typeof userInfo.stateRow.session_summary === "object" &&
            Object.keys(userInfo.stateRow.session_summary).length > 0
                ? (userInfo.stateRow.session_summary as SessionSummary)
                : null;

        const rawHistory = Array.isArray(userInfo.stateRow?.chat_history)
            ? userInfo.stateRow.chat_history
            : [];
        const formattedHistory = rawHistory
            .slice(-14)
            .map((h: any) => ({
                role: h.role === "assistant" ? "assistant" : "user",
                content: String(h.content || "").slice(0, 1600),
            }));

        const deepSeekKey = getDeepSeekApiKey();
        const apiKeys = [...getNvidiaApiKeys(), ...(deepSeekKey ? [deepSeekKey] : [])];
        const effectiveUserId = userInfo.linkedUserId || `tg_${telegramUserId}`;
        const auditUserId = userInfo.linkedUserId || deterministicSessionUuid(`tg-user-${telegramUserId}`);
        const sessionId = deterministicSessionUuid(`tg-${chatSource}-${auditUserId}`);
        const messageId = `tg_msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

        const startTime = Date.now();
        const isPortfolio = Boolean(detectPortfolioIntent(rawMessage));
        const cacheKey = buildAnalysisCacheKey(rawMessage, explicitSymbols, isPortfolio);

        let result: any = null;
        let isCached = false;
        let latencyMs = 0;

        if (cacheKey) {
            const cached = await getVipAnalysisCache(cacheKey, supabase);
            if (cached) {
                isCached = true;
                latencyMs = Date.now() - startTime;
                const personalizedReply = await personalizeCachedAnalysis(
                    cached.reply,
                    userInfo.linkedUserId,
                    explicitSymbols[0],
                    supabase
                );
                result = {
                    response: personalizedReply,
                    tables: cached.tables || [],
                    tools: cached.tools || { results: [], formattedText: "" },
                    summary_state: cached.summary_state || null,
                    session_update: {
                        current_symbol: explicitSymbols[0] || sessionState.current_symbol,
                        last_symbols: explicitSymbols.length > 0 ? explicitSymbols : sessionState.last_symbols,
                        summary: sessionState.summary,
                        current_sector: sessionState.current_sector,
                    },
                };
            }
        }

        if (!result) {
            result = await runPipeline(
                rawMessage,
                [],
                sessionState,
                sessionSummary,
                formattedHistory,
                supabase,
                apiKeys,
                effectiveUserId,
                sessionId,
                messageId,
                "deepseek-chat",
                { isPro: userInfo.isPro, chatSource, skipReview: true, gateMode: "audit_only" }
            );
            latencyMs = Date.now() - startTime;

            if (
                cacheKey &&
                result?.response &&
                result.response.length > 50 &&
                result.response_origin !== "fallback"
            ) {
                setVipAnalysisCache(
                    cacheKey,
                    {
                        reply: result.response,
                        tables: result.tables || [],
                        tools: result.tools || { results: [], formattedText: "" },
                    },
                    supabase
                ).catch((err) => console.warn("[vip-chat] cache save error:", err));
            }
        }

        const updatedSessionState = {
            current_symbol: result.session_update?.current_symbol ?? sessionState.current_symbol,
            last_symbols: result.session_update?.last_symbols ?? sessionState.last_symbols,
            summary: result.session_update?.summary ?? sessionState.summary,
            current_sector: result.session_update?.current_sector ?? sessionState.current_sector,
        };

        const updatedHistory = [
            ...rawHistory.slice(-14),
            { role: "user", content: rawMessage, created_at: new Date().toISOString() },
            {
                role: "assistant",
                content: String(result.response || "").slice(0, 1600),
                created_at: new Date().toISOString(),
            },
        ];

        // Persist state & audit logs in parallel without blocking response
        const roomPrefix =
            chatSource === "telegram_private"
                ? "🔒 [بوت تليجرام الخاص]"
                : "📢 [تليجرام التوبيك العام]";
        const commonMeta = {
            chat_source: chatSource,
            telegram_user_id: telegramUserId,
            telegram_username: telegramUsername,
            display_name: userInfo.displayName,
            linked_user_id: userInfo.linkedUserId,
        };

        const backgroundTasks = [
            supabase.from("telegram_vip_chat_state").upsert(
                {
                    telegram_user_id: telegramUserId,
                    telegram_username: telegramUsername,
                    linked_user_id: userInfo.linkedUserId,
                    quota_date: todayCairo,
                    daily_count:
                        userInfo.stateRow?.quota_date === todayCairo
                            ? Number(userInfo.stateRow?.daily_count || 0) + 1
                            : 1,
                    session_state: updatedSessionState,
                    session_summary: (result as any).summary_state || sessionSummary || {},
                    chat_history: updatedHistory,
                    pending_prompt: null,
                    updated_at: new Date().toISOString(),
                },
                { onConflict: "telegram_user_id" }
            ),
            supabase.from("ai_chat_sessions").upsert(
                {
                    id: sessionId,
                    user_id: auditUserId,
                    title: `${roomPrefix} ${rawMessage.slice(0, 28)}`,
                    state: updatedSessionState,
                    summary_state: (result as any).summary_state || sessionSummary || {},
                    is_deleted_by_user: false,
                    updated_at: new Date().toISOString(),
                },
                { onConflict: "id" }
            ),
            supabase.from("ai_chat_messages").insert([
                {
                    session_id: sessionId,
                    user_id: auditUserId,
                    role: "user",
                    content: rawMessage,
                    metadata: commonMeta,
                    created_at: new Date(Date.now() - 1000).toISOString(),
                },
                {
                    session_id: sessionId,
                    user_id: auditUserId,
                    role: "assistant",
                    content: result.response,
                    latency_ms: latencyMs,
                    metadata: {
                        ...commonMeta,
                        tables: result.tables || [],
                        usage: isCached
                            ? {
                                  prompt_tokens: 0,
                                  completion_tokens: 0,
                                  total_tokens: 0,
                                  provider_calls: 0,
                                  tool_calls: Array.isArray(result.tools?.results) ? result.tools.results.length : 0,
                                  model: "cache (0 tokens)",
                              }
                            : ((result as any).usage || null),
                        response_origin: isCached ? "cache" : ((result as any).response_origin || "llm"),
                        publication_review: (result as any).publication_review || null,
                        cached: isCached,
                    },
                    created_at: new Date().toISOString(),
                },
            ])
        ];

        // Await all parallel writes safely with fallback catch
        await Promise.allSettled(backgroundTasks).catch((err) => console.warn("[vip-chat] background write error:", err));

        return NextResponse.json({
            ok: true,
            reply: result.response,
            tables: result.tables || [],
            tools: (result.tools?.results || []).map((r: any) => r.tool),
            session_state: updatedSessionState,
            linked: Boolean(userInfo.linkedUserId),
            display_name: userInfo.displayName,
            is_pro: userInfo.isPro,
            used: newUsed,
            limit: userInfo.limit,
            remaining: newRemaining,
            period: userInfo.period,
            latency_ms: latencyMs,
            cached: isCached,
        });
    } catch (err: any) {
        console.error("[api/telegram/vip-chat] Error:", err);
        return NextResponse.json(
            { ok: false, error: String(err?.message || err) },
            { status: 500 }
        );
    }
}
