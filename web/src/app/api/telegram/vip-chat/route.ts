import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient, getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { extractExplicitSymbols, runPipeline } from "@/lib/ai/pipeline";
import { getDeepSeekApiKey, getNvidiaApiKeys } from "@/lib/ai/server-secrets";
import { hasActiveProSubscription, planLimits } from "@/lib/ai/plan-gate";
import { detectPortfolioIntent, normalizeArabicIntent } from "@/lib/ai/intent-policy";
import { SessionState, SessionSummary } from "@/lib/ai/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const ADMIN_TG_IDS = new Set(["5149631436"]);

function getCairoDateString(date: Date = new Date()): string {
    try {
        return new Intl.DateTimeFormat("en-CA", {
            timeZone: "Africa/Cairo",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
        }).format(date);
    } catch {
        const cairoMs = date.getTime() + 3 * 60 * 60 * 1000;
        return new Date(cairoMs).toISOString().split("T")[0];
    }
}

function isAuthorizedRequest(req: NextRequest): boolean {
    const adminKey =
        req.headers.get("x-admin-key") ||
        req.headers.get("authorization")?.replace("Bearer ", "");
    const expectedKey = process.env.ADMIN_SECRET_KEY?.trim() || "";
    const host = req.headers.get("host") || "";
    const isLocal = host.includes("localhost") || host.includes("127.0.0.1");
    return Boolean(isLocal || (expectedKey && adminKey && adminKey === expectedKey));
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

    // 1. Load telegram_vip_chat_state row + look up linked profile in parallel
    const [stateRes, profileRes, inviteRes] = await Promise.all([
        supabase
            .from("telegram_vip_chat_state")
            .select("telegram_user_id, telegram_username, linked_user_id, quota_date, daily_count, session_state, session_summary, chat_history, pending_prompt")
            .eq("telegram_user_id", telegramUserId)
            .maybeSingle(),
        supabase
            .from("profiles")
            .select("id, display_name, username")
            .eq("telegram_chat_id", tgIdStr)
            .limit(1)
            .maybeSingle(),
        supabase
            .from("pro_telegram_invites")
            .select("user_id")
            .eq("vip_telegram_user_id", telegramUserId)
            .limit(1)
            .maybeSingle(),
    ]);

    const stateRow = stateRes?.data || null;
    const testMode = stateRow?.session_state?.test_mode || null;
    const linkedUserId: string | null =
        profileRes?.data?.id ||
        inviteRes?.data?.user_id ||
        stateRow?.linked_user_id ||
        null;

    const displayName =
        profileRes?.data?.display_name ||
        profileRes?.data?.username ||
        telegramUsername ||
        "المستثمر";

    let isPro = false;
    let used = 0;
    let limit = Number(process.env.FREE_CHAT_DAILY_MESSAGES || "5");
    let period: "daily" | "monthly" = "daily";

    if (linkedUserId) {
        const monthStart = `${todayCairo.slice(0, 7)}-01`;
        const [subRes, limitsRes] = await Promise.all([
            supabase
                .from("subscriptions")
                .select("plan_id, status, current_period_end")
                .eq("user_id", linkedUserId)
                .eq("status", "active")
                .limit(10),
            supabase
                .from("ai_chatbot_limits")
                .select("date, chat_count")
                .eq("user_id", linkedUserId)
                .gte("date", monthStart),
        ]);

        isPro = hasActiveProSubscription(subRes?.data || []);

        const limitRows = limitsRes?.data || [];
        const todayRow = limitRows.find((r: any) => String(r.date) === todayCairo);
        const todayCount = Number(todayRow?.chat_count || 0);
        const monthlyCount = limitRows.reduce(
            (acc: number, r: any) => acc + (Number(r.chat_count) || 0),
            0
        );

        if (isPro) {
            period = "monthly";
            limit = planLimits("pro").chat_messages_per_month || 350;
            used = monthlyCount;
        } else {
            period = "daily";
            limit = Number(process.env.FREE_CHAT_DAILY_MESSAGES || "5");
            used = todayCount;
        }
    } else {
        // Unlinked Telegram group user -> Free plan (5 messages/day)
        const rowDate = stateRow?.quota_date ? String(stateRow.quota_date) : "";
        const todayCount = rowDate === todayCairo ? Number(stateRow?.daily_count || 0) : 0;
        isPro = false;
        period = "daily";
        limit = Number(process.env.FREE_CHAT_DAILY_MESSAGES || "5");
        used = todayCount;
    }

    // Apply optional simulation test_mode (for testing quota exhaustion or free tier)
    if (testMode === "limit_reached") {
        isPro = false;
        period = "daily";
        limit = 5;
        used = 5;
    } else if (testMode === "free_plan") {
        isPro = false;
        period = "daily";
        limit = 5;
        used = Math.min(4, used);
    }

    const remaining = Math.max(0, limit - used);

    return {
        telegramUserId,
        telegramUsername,
        linkedUserId,
        displayName,
        isPro,
        isAdmin: false,
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

        // Check if message asks for Pro-only recommendations when user is on Free plan
        const normalizedMsg = normalizeArabicIntent(rawMessage);
        const asksProRecs =
            /(?:توصيات|توصيه|اشارات|اشاره|ترشيحات|recommendations?|signals?)/i.test(normalizedMsg) &&
            !/(?:يعني\s*ايه|ما\s*معنى|ما\s*هو|شرح|تعريف)/i.test(normalizedMsg);

        if (!userInfo.isPro && !detectPortfolioIntent(rawMessage) && asksProRecs) {
            return NextResponse.json(
                {
                    ok: false,
                    error_code: "PRO_REQUIRED",
                    linked: Boolean(userInfo.linkedUserId),
                    display_name: userInfo.displayName,
                    is_pro: false,
                    used: userInfo.used,
                    limit: userInfo.limit,
                    remaining: userInfo.remaining,
                    period: userInfo.period,
                    detail: "التوصيات وإشارات الشراء الفورية متاحة حصرياً لمشتركي باقة PRO.",
                },
                { status: 403 }
            );
        }

        // Check portfolio tool requirement for unlinked users
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
        if (!userInfo.isAdmin && userInfo.remaining <= 0) {
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
                        : `لقد استهلكت رصيدك اليومي المجاني (${userInfo.limit}/${userInfo.limit} أسئلة اليوم). اشترك في باقة PRO للحصول على 350 سؤال شهرياً وتوصيات لحظية!`,
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

        // Atomically consume 1 quota unit
        let newUsed = userInfo.used + 1;
        if (!userInfo.isAdmin && userInfo.linkedUserId) {
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
                content: String(h.content || "").slice(0, 500),
            }));

        const deepSeekKey = getDeepSeekApiKey();
        const apiKeys = [...getNvidiaApiKeys(), ...(deepSeekKey ? [deepSeekKey] : [])];
        const effectiveUserId = userInfo.linkedUserId || `tg_${telegramUserId}`;
        const sessionId = deterministicSessionUuid(`tg-vip-${effectiveUserId}`);
        const messageId = `tg_msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

        const startTime = Date.now();
        const result = await runPipeline(
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
            { isPro: userInfo.isPro }
        );
        const latencyMs = Date.now() - startTime;

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
                content: String(result.response || "").slice(0, 1200),
                created_at: new Date().toISOString(),
            },
        ];

        // Persist updated state, history, and daily_count in telegram_vip_chat_state
        await supabase.from("telegram_vip_chat_state").upsert(
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
                session_summary: sessionSummary || {},
                chat_history: updatedHistory,
                pending_prompt: null,
                updated_at: new Date().toISOString(),
            },
            { onConflict: "telegram_user_id" }
        );

        // If linked to a website user, also log to ai_chat_sessions & ai_chat_messages so it appears in Admin Logs
        if (userInfo.linkedUserId) {
            try {
                await supabase.from("ai_chat_sessions").upsert(
                    {
                        id: sessionId,
                        user_id: userInfo.linkedUserId,
                        title: `[Telegram VIP] ${rawMessage.slice(0, 28)}`,
                        state: updatedSessionState,
                        updated_at: new Date().toISOString(),
                    },
                    { onConflict: "id" }
                );
                await supabase.from("ai_chat_messages").insert([
                    {
                        session_id: sessionId,
                        user_id: userInfo.linkedUserId,
                        role: "user",
                        content: rawMessage,
                        created_at: new Date(Date.now() - 1000).toISOString(),
                    },
                    {
                        session_id: sessionId,
                        user_id: userInfo.linkedUserId,
                        role: "assistant",
                        content: result.response,
                        latency_ms: latencyMs,
                        created_at: new Date().toISOString(),
                    },
                ]);
            } catch (logErr) {
                console.warn("[telegram/vip-chat] Non-fatal session log error:", logErr);
            }
        }

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
        });
    } catch (err: any) {
        console.error("[api/telegram/vip-chat] Error:", err);
        return NextResponse.json(
            { ok: false, error: String(err?.message || err) },
            { status: 500 }
        );
    }
}
