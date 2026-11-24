"use client";



import { createContext, useContext, useState, ReactNode, useEffect, useCallback, useRef } from "react";

import { useAuth } from "@/contexts/AuthContext";

import { ChatSession } from "@/components/chat/ChatSidebar";

import { sanitizeReply, sanitizeUiLabel, stripEnvironmentLeak } from "@/lib/ai/sanitizer";

import { createChatRequest } from "@/lib/chat-request.cjs";

import { orderChatMessages } from "@/lib/ai/chat-order";

import { invalidateUserQuotaCache } from "@/lib/user-quota-client";



export type AnswerStageId = "understand" | "fetch_data" | "quant_verify" | "synthesize";

export type AnswerStageItem = {
    id: AnswerStageId;
    label: string;
    status: "pending" | "in_progress" | "done";
};

const _RAW_STATUS_CODES = new Set(["thinking", "vision", "executing_tools", "quant_engine", "generating", "cached"]);

export function createInitialAnswerStages(opts?: { hasImages?: boolean; isVoiceNote?: boolean }): AnswerStageItem[] {
    return [
        {
            id: "understand",
            label: opts?.isVoiceNote
                ? "تحويل الرسالة الصوتية وفهم السؤال"
                : opts?.hasImages
                ? "قراءة الصورة وفهم سياق السؤال"
                : "فهم السؤال وتحديد السهم والسوق",
            status: "in_progress",
        },
        {
            id: "fetch_data",
            label: "جلب البيانات الحية من أدوات السوق",
            status: "pending",
        },
        {
            id: "quant_verify",
            label: "التحليل الكمي ومحاكاة مونت كارلو وحسم التعارض",
            status: "pending",
        },
        {
            id: "synthesize",
            label: "صياغة التقرير النهائي ومراجعة الحارس الآلي",
            status: "pending",
        },
    ];
}

function _resolveStageIdFromPayload(payload: { step_id?: string; status?: string }): AnswerStageId | null {
    const sid = payload.step_id;
    if (sid === "understand" || sid === "fetch_data" || sid === "quant_verify" || sid === "synthesize") {
        return sid;
    }
    const st = String(payload.status || "").trim();
    if (st === "thinking" || st === "vision") return "understand";
    if (st === "executing_tools" || st === "cached") return "fetch_data";
    if (st === "quant_engine") return "quant_verify";
    if (st === "generating") return "synthesize";
    return null;
}

export function advanceAnswerStagesOnStatus(
    stages: AnswerStageItem[] | undefined,
    payload: { step_id?: string; status?: string; message?: string; content?: string }
): AnswerStageItem[] {
    const base = stages && stages.length > 0 ? stages.map((s) => ({ ...s })) : createInitialAnswerStages();
    const rawMsg = typeof payload.message === "string"
        ? payload.message.trim()
        : typeof payload.content === "string"
        ? payload.content.trim()
        : "";
    const humanLabel = rawMsg && !_RAW_STATUS_CODES.has(rawMsg) ? rawMsg : "";

    if (payload.status === "cached") {
        const understand = base.find((s) => s.id === "understand") || createInitialAnswerStages()[0];
        const fetchStage = base.find((s) => s.id === "fetch_data") || createInitialAnswerStages()[1];
        const synthStage = base.find((s) => s.id === "synthesize") || createInitialAnswerStages()[3];
        return [
            { ...understand, status: "done" },
            { ...fetchStage, label: humanLabel || "تم استرجاع التحليل الموثق من الذاكرة", status: "done" },
            { ...synthStage, status: "in_progress" },
        ];
    }

    const targetId = _resolveStageIdFromPayload(payload);
    if (!targetId) return base;

    let targetIdx = base.findIndex((s) => s.id === targetId);
    if (targetIdx < 0) {
        const fresh = createInitialAnswerStages();
        const prevMap = new Map(base.map((s) => [s.id, s]));
        base.splice(0, base.length, ...fresh.map((s) => prevMap.get(s.id) || s));
        targetIdx = base.findIndex((s) => s.id === targetId);
    }

    return base.map((stage, idx) => {
        if (idx < targetIdx) {
            return { ...stage, status: "done" };
        }
        if (idx === targetIdx) {
            return {
                ...stage,
                label: humanLabel || stage.label,
                status: "in_progress",
            };
        }
        return { ...stage, status: "pending" };
    });
}

export function advanceAnswerStagesOnToken(stages: AnswerStageItem[] | undefined): AnswerStageItem[] {
    if (!stages || stages.length === 0) return [];
    const middleReached = stages.some(
        (s) => (s.id === "fetch_data" || s.id === "quant_verify") && (s.status === "done" || s.status === "in_progress")
    );
    const filtered = middleReached
        ? stages
        : stages.filter((s) => s.id === "understand" || s.id === "synthesize");
    return filtered.map((stage) =>
        stage.id === "synthesize"
            ? { ...stage, status: "in_progress" }
            : { ...stage, status: "done" }
    );
}

export function finalizeAnswerStages(
    stages: AnswerStageItem[] | undefined,
    opts?: { toolsUsed?: string[]; cached?: boolean }
): AnswerStageItem[] {
    if (!stages || stages.length === 0) return [];
    const hasTools = Array.isArray(opts?.toolsUsed) && opts.toolsUsed.length > 0;
    const filtered = stages.filter((s) => {
        if (s.id === "understand" || s.id === "synthesize") return true;
        if (s.status === "done" || s.status === "in_progress") return true;
        if (hasTools && !opts?.cached) return true;
        return false;
    });
    return filtered.map((s) => ({ ...s, status: "done" }));
}

export type ChatMessage = {

    id?: string;

    role: "user" | "assistant" | "system";

    content: string;

    timestamp: number;

    imageUrl?: string;

    imagePreviewUrl?: string;

    images?: string[];

    actions?: ChatAction[];

    suggestedButtons?: string[];

    isStreaming?: boolean;

    statusText?: string;

    answerStages?: AnswerStageItem[];

    tables?: ChatTable[];

    latencyMs?: number;

    isVoice?: boolean;

    isVoiceNote?: boolean;

    isVoiceCall?: boolean;

    voiceAudioUrl?: string;

    voiceDuration?: number;

    spokenText?: string;

};



export type ChatTable = {

    id: string;

    title: string;

    headers: string[];

    rows: string[][];

    source?: string;

    data_time?: string;

    charts?: Record<string, {
        series: Array<{ d: string; c: number; v?: number | null }>;
        ema50?: number | null;
        support1?: number | null;
        resistance1?: number | null;
    }>;

    visuals?: {
        comparison?: Array<{
            symbol: string;
            name_ar?: string;
            close?: number | null;
            change_pct?: number | null;
            rsi_14?: number | null;
            r_vol?: number | null;
            king_ai_score?: number | null;
            support_1?: number | null;
            resistance_1?: number | null;
            currency?: string;
            is_sharia_compliant?: boolean | null;
        }>;
        portfolio?: {
            cash_balance?: number;
            totals?: {
                positions_count?: number;
                cost_basis?: number | null;
                market_value?: number | null;
                profit_value?: number | null;
                profit_pct?: number | null;
                equity?: number | null;
            };
            totals_by_market?: Record<string, {
                currency?: string;
                positions_count?: number;
                cost_basis?: number | null;
                market_value?: number | null;
                profit_value?: number | null;
            }>;
            positions?: Array<{
                symbol: string;
                name?: string;
                market?: string;
                currency?: string;
                quantity?: number | null;
                market_value?: number | null;
                cost_basis?: number | null;
                profit_value?: number | null;
                profit_pct?: number | null;
            }>;
        };
        market_breadth?: {
            market?: string;
            index_name?: string;
            index_close?: number | null;
            index_change_pct?: number | null;
            currency?: string;
            date?: string | null;
            advancing: number;
            declining: number;
            unchanged: number;
            total_stocks: number;
        };
        accumulation?: Array<{
            symbol: string;
            name_ar?: string;
            accumulation_score?: number | null;
            r_vol?: number | null;
            consecutive_acc_days?: number | null;
            close?: number | null;
            change_pct?: number | null;
            currency?: string;
        }>;
        fair_value?: Array<{
            symbol: string;
            currency?: string;
            current_price: number;
            fair_value: number;
            upside_pct?: number | null;
            status?: string;
            model?: string;
            pe_ratio?: number | null;
            sector?: string | null;
        }>;
        recommendations?: Array<{
            symbol: string;
            currency?: string;
            entry_price: number;
            target_price?: number | null;
            stop_loss?: number | null;
            last_close?: number | null;
            date?: string | null;
            status?: string | null;
            timeframe?: string | null;
        }>;
        sharia?: {
            symbol: string;
            currency?: string;
            is_sharia_compliant?: boolean;
            sharia_index?: string;
            shares_count?: number;
            coupon_per_share?: number;
            total_dividends?: number;
            purification_rate_pct?: number;
            purification_amount?: number;
            zakat_amount?: number;
        };
        price_traps?: {
            market?: string;
            currency?: string;
            asOf?: string | null;
            bearTraps?: Array<{
                symbol: string;
                close?: number | null;
                wickPct?: number | null;
                relativeVolume?: number | null;
                changePct?: number | null;
                conviction?: number | null;
            }>;
            bullTraps?: Array<{
                symbol: string;
                close?: number | null;
                wickPct?: number | null;
                relativeVolume?: number | null;
                changePct?: number | null;
                conviction?: number | null;
            }>;
        };
        disclosures?: Array<{
            symbol?: string | null;
            company_name?: string | null;
            disclosure_type?: string | null;
            disclosure_date?: string | null;
            title?: string | null;
            sentiment?: string | number | null;
            source_url?: string | null;
        }>;
        quant_analysis?: Array<{
            symbol: string;
            name_ar?: string | null;
            exchange?: string;
            currency?: string;
            close?: number | null;
            change_pct?: number | null;
            rsi_14?: number | null;
            r_vol?: number | null;
            ema_50?: number | null;
            ema_200?: number | null;
            stop_loss?: number | null;
            support_1?: number | null;
            support_2?: number | null;
            resistance_1?: number | null;
            resistance_2?: number | null;
            king_ai_score?: number | null;
            wyckoff_phase?: string | null;
            macd?: number | null;
            setup_regime?: string;
            setup_regime_label_ar?: string;
            conflict_resolution_ar?: string;
            technical_score?: number;
            fundamental_score?: number;
            conviction_score?: number;
            is_sharia_compliant?: boolean | null;
            bull_case?: string[];
            bear_case?: string[];
            monte_carlo?: {
                paths_count?: number;
                horizon_days?: number;
                daily_limit_pct?: number;
                target_barrier?: number;
                stop_barrier?: number;
                raw_target_prob_pct?: number;
                prob_hit_target_first_pct?: number;
                calibrated_target_prob_pct?: number;
                prob_hit_stop_first_pct?: number;
                prob_stay_in_range_pct?: number;
                mathematical_expectancy_pct?: number;
                expected_10d_range?: { p10: number; p50: number; p90: number };
                daily_vol_pct?: number;
                annualized_vol_pct?: number;
            };
            self_learning?: {
                raw_target_prob_pct?: number;
                calibrated_target_prob_pct?: number;
                empirical_hit_rate_pct?: number | null;
                empirical_sample_size?: number;
                brier_score?: number | null;
                learned_lesson_ar?: string;
            };
            macro_sensitivity?: {
                rating?: string;
                corr_usd_parallel?: number | null;
                corr_gold?: number | null;
                summary_ar?: string;
            } | null;
        }>;
        dca_plan?: {
            symbol: string;
            exchange?: string;
            currency?: string;
            dca_allowed: boolean;
            verdict_ar?: string;
            rejection_reason_ar?: string;
            old_shares?: number;
            old_avg_price?: number;
            current_price?: number;
            current_loss_pct?: number;
            capital_protection_stop?: number;
            dca_budget?: number;
            budget_estimated?: boolean;
            reference_100_shares?: boolean;
            new_avg_price_t1?: number;
            new_avg_price_full?: number;
            rally_needed_before_pct?: number;
            rally_needed_after_pct?: number;
            prob_breakeven_10d_before_pct?: number | null;
            prob_breakeven_10d_after_pct?: number | null;
            hard_invalidation_stop?: number;
            estimated_fees?: number;
            leftover_cash?: number;
            tranches?: Array<{
                tranche: number;
                label: string;
                weight_pct: number;
                limit_price: number;
                shares: number;
                cost: number;
                fee: number;
                avg_after: number;
            }>;
        };
    };

};



type ChatAction = {

    label: string;

    type: "navigate" | "function";

    value: string;

};



export const AVAILABLE_AI_MODELS = [

    { id: "deepseek-chat", name: "DeepSeek Flash", badgeAr: "الأسرع ⚡", badgeEn: "Fastest ⚡", descAr: "أسرع نموذج ديب سيك — استجابة فورية لتحليلات البورصة", descEn: "Fastest DeepSeek model — instant response for stock analysis" },

    { id: "deepseek-reasoner", name: "DeepSeek Pro", badgeAr: "الأعمق 🧠", badgeEn: "Reasoner 🧠", descAr: "النموذج الاستدلالي المتقدم لقرارات التداول والتحليلات العميقة", descEn: "Advanced reasoning model for deep analysis and trade decisions" },

];



// Kept for future testing (stock analysis benchmarks):

export const EXPERIMENTAL_AI_MODELS = [

    { id: "deepseek-v4.1-flash-uncensored", name: "DeepSeek V4.1 Flash", badgeAr: "V4.1 حر 🔥", badgeEn: "V4.1 Uncensored 🔥", descAr: "إصدار ديب سيك V4.1 فلاش غير المقيد عبر Experiential Labs", descEn: "DeepSeek V4.1 Flash Uncensored via Experiential Labs" },

    { id: "gpt-6-luna-decisions", name: "GPT-6 Luna Decisions", badgeAr: "قرارات 🎯", badgeEn: "Decisions 🎯", descAr: "محرك اتخاذ القرارات وفحص الأدلة الرقمية للبورصة المصرية", descEn: "Decision engine & structured evidence verification for EGX" },

];



interface ChatContextType {

    isOpen: boolean;

    setIsOpen: (v: boolean) => void;

    messages: ChatMessage[];

    sendMessage: (text: string, imageInput?: string | string[], options?: { isVoice?: boolean; isVoiceNote?: boolean; isVoiceCall?: boolean; audioDuration?: number; voiceAudioUrl?: string }) => Promise<any>;

    stopResponding: () => void;

    isLoading: boolean;

    remainingQuota: number;

    quotaLimit?: number;

    isPro?: boolean;

    isInitializing: boolean;

    accessError: boolean;

    retryAccess: () => void;

    showUpgradeModal: boolean;

    setShowUpgradeModal: (v: boolean) => void;

    selectedModel: string;

    setSelectedModel: (model: string) => void;

    sessions: ChatSession[];

    activeSessionId: string | null;

    createNewSession: () => void;

    switchSession: (sessionId: string) => Promise<void>;

    deleteSession: (sessionId: string) => Promise<void>;

    renameSession: (sessionId: string, newTitle: string) => Promise<void>;

    isSidebarOpen: boolean;

    setIsSidebarOpen: (v: boolean) => void;

    autonomousRecommendations: boolean;

    setAutonomousRecommendations: (enabled: boolean) => void;

    isAccessReady: boolean;

}



const ChatContext = createContext<ChatContextType | undefined>(undefined);



// Local Storage Persistence Helpers
export function isTelegramSessionMeta(title?: string): boolean {
    const t = title || "";
    return t.includes("[تليجرام") || t.startsWith("📢") || t.startsWith("🔒 [بوت");
}

function getStoredSessions(): ChatSession[] {

    if (typeof window === "undefined") return [];

    try {

        const raw = localStorage.getItem("egxbots_chat_sessions_v2");

        return raw ? JSON.parse(raw) : [];

    } catch {

        return [];

    }

}



function saveStoredSessions(sessions: ChatSession[]) {

    if (typeof window === "undefined") return;

    try {

        localStorage.setItem("egxbots_chat_sessions_v2", JSON.stringify(sessions));

    } catch (e) {

        console.error("Failed to save sessions to localStorage:", e);

    }

}



function getStoredMessages(sessionId: string): ChatMessage[] {

    if (typeof window === "undefined" || !sessionId) return [];

    try {

        const raw = localStorage.getItem(`egxbots_msgs_${sessionId}`);

        return raw ? JSON.parse(raw) : [];

    } catch {

        return [];

    }

}



function saveStoredMessagesSync(sessionId: string, msgs: ChatMessage[]) {

    if (typeof window === "undefined" || !sessionId) return;

    try {

        // Preserve attached image preview URLs so user uploads persist across page refreshes

        const cleanMsgs = msgs.map(m => ({

            ...m,

            imagePreviewUrl: m.imagePreviewUrl || (m.imageUrl && m.imageUrl !== "[image]" ? m.imageUrl : undefined),

            imageUrl: m.imageUrl,

            images: m.images

        }));

        localStorage.setItem(`egxbots_msgs_${sessionId}`, JSON.stringify(cleanMsgs));

    } catch (e) {

        console.error("Failed to save messages to localStorage:", e);

    }

}



function stripMarkdownTables(text: string): string {

    // Generated tables can contain requested facts absent from the tool's

    // structured table. Never delete them merely because of their formatting.

    return text.replace(/\n{3,}/g, "\n\n").trim();

}



function cleanChatText(text: string): string {

    return stripEnvironmentLeak(sanitizeUiLabel(text || ""));

}



export function ChatProvider({ children }: { children: ReactNode }) {

    const { user, session, loading: authLoading } = useAuth();

    const userId = user?.id;

    const sessionTokenRef = useRef<string | null>(null);
    sessionTokenRef.current = session?.access_token || null;

    const getAuthHeaders = useCallback((): Record<string, string> => {
        const token = sessionTokenRef.current;
        return token ? { Authorization: `Bearer ${token}` } : {};
    }, []);

    const accessOwnerRef = useRef(userId);

    accessOwnerRef.current = userId;

    const [accessState, setAccessState] = useState<{ owner?: string; status: "loading" | "ready" | "error" }>({ status: "loading" });

    const accessRequestRef = useRef<{ owner: string; promise: Promise<void> } | null>(null);

    const accessCheckedAtRef = useRef(0);

    const isInitializing = Boolean(authLoading || (userId && (accessState.owner !== userId || accessState.status === "loading")));

    const accessError = Boolean(userId && accessState.owner === userId && accessState.status === "error");

    const chartContextRef = useRef<unknown>(undefined);

    const chartGenerationRef = useRef(0);

    const chartOwnerRef = useRef(user?.id);

    if (chartOwnerRef.current !== user?.id) {

        chartOwnerRef.current = user?.id;

        chartContextRef.current = undefined;

        chartGenerationRef.current++;

    }

    useEffect(() => {

        const receiveContext = (event: Event) => {

            const next = (event as CustomEvent).detail || undefined;

            if (JSON.stringify(next) !== JSON.stringify(chartContextRef.current)) chartGenerationRef.current++;

            chartContextRef.current = next;

        };

        window.addEventListener("strategy-lab-context", receiveContext);

        return () => window.removeEventListener("strategy-lab-context", receiveContext);

    }, []);



    const publishChartActions = (actions: unknown, requestContext: unknown, requestOwner: string | undefined, generation: number) => {

        if (!Array.isArray(actions) || !requestContext || generation !== chartGenerationRef.current || requestOwner !== chartOwnerRef.current || JSON.stringify(requestContext) !== JSON.stringify(chartContextRef.current)) return;

        for (const action of actions.slice(0, 10)) {

            window.dispatchEvent(new CustomEvent("strategy-lab-result", { detail: action }));

        }

    };



    const [isOpen, setIsOpen] = useState(false);

    const [messages, setMessages] = useState<ChatMessage[]>([]);

    const [isLoading, setIsLoading] = useState(false);

    const [remainingQuota, setRemainingQuota] = useState<number>(10);

    const [quotaLimit, setQuotaLimit] = useState<number>(10);

    const [isPro, setIsPro] = useState<boolean>(() => {

        if (typeof window !== "undefined") {

            return localStorage.getItem("egx_chat_pro_active") === "true";

        }

        return false;

    });

    const [showUpgradeModal, setShowUpgradeModal] = useState<boolean>(false);

    const [selectedModel, setSelectedModelState] = useState<string>("deepseek-chat");

    const [sessions, setSessionsState] = useState<ChatSession[]>([]);

    const [activeSessionId, setActiveSessionIdState] = useState<string | null>(null);

    const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);

    const [autonomousRecommendations, setAutonomousRecommendationsState] = useState<boolean>(false);

    const [activeMarket, setActiveMarket] = useState<"egx" | "tasi">(() => {
        if (typeof window !== "undefined") {
            return localStorage.getItem("egxbots_market") === "tasi" ? "tasi" : "egx";
        }
        return "egx";
    });

    useEffect(() => {
        if (typeof window === "undefined") return;
        const syncMarket = () => {
            setActiveMarket(localStorage.getItem("egxbots_market") === "tasi" ? "tasi" : "egx");
        };
        const onMarketChange = (event: Event) => {
            const detail = (event as CustomEvent<{ market?: string }>)?.detail;
            if (detail?.market === "tasi" || detail?.market === "egx") {
                setActiveMarket(detail.market);
            } else {
                syncMarket();
            }
        };
        const onStorage = (event: StorageEvent) => {
            if (event.key === "egxbots_market") {
                syncMarket();
            }
        };
        syncMarket();
        window.addEventListener("egxbots:market-change", onMarketChange);
        window.addEventListener("storage", onStorage);
        return () => {
            window.removeEventListener("egxbots:market-change", onMarketChange);
            window.removeEventListener("storage", onStorage);
        };
    }, []);



    useEffect(() => {

        if (typeof window !== "undefined") {

            const saved = localStorage.getItem("artoro_autonomous_recs_enabled");

            if (saved === "true") {

                setAutonomousRecommendationsState(true);

            }

        }

    }, []);



    const setAutonomousRecommendations = useCallback((enabled: boolean) => {

        setAutonomousRecommendationsState(enabled);

        if (typeof window !== "undefined") {

            localStorage.setItem("artoro_autonomous_recs_enabled", String(enabled));

            window.dispatchEvent(new CustomEvent("artoro-autonomous-recs-changed", { detail: { enabled } }));

        }

        void fetch("/api/ai-chat?action=settings", {

            method: "POST",

            headers: { "Content-Type": "application/json", ...getAuthHeaders() },

            body: JSON.stringify({ action: "update_settings", autonomous_recommendations: enabled }),

        }).catch((err) => {

            console.warn("Failed to persist autonomous recommendations to Supabase:", err);

        });

    }, []);



    useEffect(() => {

        const handleRecsChange = (e: Event) => {

            const detail = (e as CustomEvent).detail;

            if (detail && typeof detail.enabled === "boolean") {

                setAutonomousRecommendationsState(detail.enabled);

            }

        };

        window.addEventListener("artoro-autonomous-recs-changed", handleRecsChange);

        return () => window.removeEventListener("artoro-autonomous-recs-changed", handleRecsChange);

    }, []);





    useEffect(() => {

        if (typeof window !== "undefined") {

            setIsSidebarOpen(window.innerWidth >= 768);

        }

    }, []);



    const sessionMessagesCache = useRef<Record<string, ChatMessage[]>>({});

    const loadingSessionIds = useRef<Record<string, boolean>>({});
    const sessionMutationVersionRef = useRef<Record<string, number>>({});
    const lastLocalTurnAtRef = useRef<Record<string, number>>({});
    const lastSubmitRef = useRef<{ sessionId: string; text: string; ts: number } | null>(null);

    const activeSessionIdRef = useRef<string | null>(activeSessionId);

    const abortControllerRef = useRef<AbortController | null>(null);

    const saveTimersRef = useRef<Record<string, NodeJS.Timeout>>({});



    const setActiveSessionId = useCallback((id: string | null) => {

        activeSessionIdRef.current = id;

        setActiveSessionIdState(id);

    }, []);



    // Flush debounced localStorage writes for a given session

    const flushStoredMessages = useCallback((sessionId: string, msgs?: ChatMessage[]) => {

        if (saveTimersRef.current[sessionId]) {

            clearTimeout(saveTimersRef.current[sessionId]);

            delete saveTimersRef.current[sessionId];

        }

        const targetMsgs = msgs || sessionMessagesCache.current[sessionId];

        if (targetMsgs) {

            saveStoredMessagesSync(sessionId, targetMsgs);

        }

    }, []);



    // Debounce localStorage writes (400ms) to prevent synchronous serialization on every stream token

    const debouncedSaveStoredMessages = useCallback((sessionId: string, msgs: ChatMessage[]) => {

        if (saveTimersRef.current[sessionId]) {

            clearTimeout(saveTimersRef.current[sessionId]);

        }

        saveTimersRef.current[sessionId] = setTimeout(() => {

            saveStoredMessagesSync(sessionId, msgs);

            delete saveTimersRef.current[sessionId];

        }, 400);

    }, []);



    // Unified helper to update session messages cache, state (if active), and schedule debounced save

    const setSessionMessages = useCallback((sessionId: string, updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {

        const prevMsgs = sessionMessagesCache.current[sessionId] || [];

        const nextMsgs = typeof updater === "function" ? updater(prevMsgs) : updater;



        sessionMessagesCache.current[sessionId] = nextMsgs;



        if (activeSessionIdRef.current === sessionId) {

            setMessages(nextMsgs);

        }



        debouncedSaveStoredMessages(sessionId, nextMsgs);

    }, [debouncedSaveStoredMessages]);



    const stopResponding = useCallback(() => {

        if (abortControllerRef.current) {

            abortControllerRef.current.abort();

            abortControllerRef.current = null;

            setIsLoading(false);

            loadingSessionIds.current = {};

        }

    }, []);



    const setSessions = useCallback((updater: ChatSession[] | ((prev: ChatSession[]) => ChatSession[])) => {

        setSessionsState(prev => {

            const next = typeof updater === "function" ? updater(prev) : updater;

            saveStoredSessions(next);

            return next;

        });

    }, []);



    // Flush any pending localStorage saves on unmount

    useEffect(() => {

        return () => {

            Object.keys(saveTimersRef.current).forEach(sessionId => {

                if (saveTimersRef.current[sessionId]) {

                    clearTimeout(saveTimersRef.current[sessionId]);

                    const pendingMsgs = sessionMessagesCache.current[sessionId];

                    if (pendingMsgs) {

                        saveStoredMessagesSync(sessionId, pendingMsgs);

                    }

                }

            });

        };

    }, []);



    // Load initial sessions & messages from localStorage on mount

    useEffect(() => {

        const localSessions = getStoredSessions();

        if (localSessions.length > 0) {

            setSessionsState(localSessions);

            const latest = localSessions[0];

            setActiveSessionId(latest.id);

            const localMsgs = getStoredMessages(latest.id);

            if (localMsgs.length > 0) {

                const sanitizedMessages = localMsgs.map(message => ({ ...message, content: cleanChatText(message.content || ""), suggestedButtons: message.suggestedButtons?.map(cleanChatText).filter(Boolean) }));

                setMessages(sanitizedMessages);

                sessionMessagesCache.current[latest.id] = sanitizedMessages;

            }

        }

    }, [setActiveSessionId]);



    useEffect(() => {

        setMessages(prev => prev.map(message => ({

            ...message,

            content: cleanChatText(message.content || ""),

            suggestedButtons: message.suggestedButtons?.map(cleanChatText).filter(Boolean)

        })));

    }, []);



    useEffect(() => {

        const savedModel = localStorage.getItem("egxbots_selected_model");

        if (savedModel && AVAILABLE_AI_MODELS.some(m => m.id === savedModel)) {

            setSelectedModelState(savedModel);

        }

    }, []);



    const setSelectedModel = useCallback((model: string) => {

        setSelectedModelState(model);

        localStorage.setItem("egxbots_selected_model", model);

    }, []);



    // Deduplicate history reads per room. The cache is local-first; only one

    // background sync per session may hit the API at a time.

    const sessionFetchesRef = useRef<Record<string, Promise<void>>>({});

    const fetchSessionMessages = useCallback((sessionId: string): Promise<void> => {

        if (loadingSessionIds.current[sessionId]) return Promise.resolve();

        const pending = sessionFetchesRef.current[sessionId];

        if (pending) return pending;

        const request = (async () => {

            const fetchStartVersion = sessionMutationVersionRef.current[sessionId] || 0;

            try {

                const res = await fetch(`/api/ai-chat?session_id=${encodeURIComponent(sessionId)}`, {
                    headers: { ...getAuthHeaders() },
                });

                if (!res.ok) return;

                const data = await res.json();

                if (!Array.isArray(data.history) || data.history.length === 0) return;

                if (loadingSessionIds.current[sessionId] || (sessionMutationVersionRef.current[sessionId] || 0) !== fetchStartVersion) {
                    return;
                }



                const existing = sessionMessagesCache.current[sessionId] || getStoredMessages(sessionId);

                const localImageMap = new Map<number, { imageUrl?: string; imagePreviewUrl?: string; images?: string[] }>();
                const localVoiceMap = new Map<number, { voiceAudioUrl?: string; voiceDuration?: number; spokenText?: string; isVoice?: boolean; isVoiceNote?: boolean }>();
                const localTablesMap = new Map<number, ChatTable[]>();

                existing.forEach((m, idx) => {

                    if (Array.isArray(m.tables) && m.tables.length > 0) {

                        localTablesMap.set(idx, m.tables);

                    }

                    if (m.imageUrl || m.imagePreviewUrl || m.images) {

                        localImageMap.set(idx, {

                            imageUrl: m.imageUrl,

                            imagePreviewUrl: m.imagePreviewUrl,

                            images: m.images

                        });

                    }

                    if (m.voiceAudioUrl || m.isVoiceNote || m.voiceDuration) {

                        localVoiceMap.set(idx, {

                            voiceAudioUrl: m.voiceAudioUrl,

                            voiceDuration: m.voiceDuration,

                            isVoice: m.isVoice,

                            isVoiceNote: m.isVoiceNote,

                            spokenText: m.spokenText

                        });

                    }

                });



                const mergedHistory: ChatMessage[] = orderChatMessages(data.history.map((srvMsg: ChatMessage, idx: number) => {

                    const localImg = localImageMap.get(idx);
                    const localVoice = localVoiceMap.get(idx);
                    const localTables = localTablesMap.get(idx);

                    return {

                        ...srvMsg,

                        content: cleanChatText(srvMsg.content || ""),

                        tables: Array.isArray(srvMsg.tables) && srvMsg.tables.length > 0 ? srvMsg.tables : localTables,

                        suggestedButtons: srvMsg.suggestedButtons?.map(cleanChatText).filter(Boolean),

                        imagePreviewUrl: srvMsg.imagePreviewUrl || localImg?.imagePreviewUrl || srvMsg.imageUrl || localImg?.imageUrl,

                        imageUrl: srvMsg.imageUrl || localImg?.imageUrl,

                        images: srvMsg.images || localImg?.images,

                        voiceAudioUrl: srvMsg.voiceAudioUrl || localVoice?.voiceAudioUrl,

                        voiceDuration: srvMsg.voiceDuration ?? localVoice?.voiceDuration,

                        isVoice: srvMsg.isVoice ?? localVoice?.isVoice,

                        isVoiceNote: srvMsg.isVoiceNote ?? localVoice?.isVoiceNote,

                        spokenText: srvMsg.spokenText ?? localVoice?.spokenText

                    };

                }));



                const latestExisting = sessionMessagesCache.current[sessionId] || getStoredMessages(sessionId);

                if (loadingSessionIds.current[sessionId] || (sessionMutationVersionRef.current[sessionId] || 0) !== fetchStartVersion) {
                    return;
                }

                if (Date.now() - (lastLocalTurnAtRef.current[sessionId] || 0) < 15_000 && latestExisting.length > mergedHistory.length) {
                    const newestServerTs = mergedHistory.reduce((mx, m) => Math.max(mx, m.timestamp || 0), 0);
                    const newestLocalTs = latestExisting.reduce((mx, m) => Math.max(mx, m.timestamp || 0), 0);
                    if (newestLocalTs > newestServerTs) {
                        return;
                    }
                }

                // Keep an in-flight optimistic turn (both user question and streaming assistant bubble) visible while syncing history.

                if (loadingSessionIds.current[sessionId]) {

                    const streamingIdx = latestExisting.findIndex(m => m.isStreaming);

                    if (streamingIdx >= 0) {

                        const precedingUserMsg = streamingIdx > 0 && latestExisting[streamingIdx - 1]?.role === "user"
                            ? latestExisting[streamingIdx - 1]
                            : null;

                        if (
                            precedingUserMsg &&
                            !mergedHistory.some(m =>
                                (m.id && m.id === precedingUserMsg.id) ||
                                (m.role === "user" && m.timestamp === precedingUserMsg.timestamp && m.content === precedingUserMsg.content)
                            )
                        ) {

                            mergedHistory.push(precedingUserMsg);

                        }

                        const streamingMsg = latestExisting[streamingIdx];

                        if (streamingMsg && !mergedHistory.some(m => m.id === streamingMsg.id)) {

                            mergedHistory.push(streamingMsg);

                        }

                    }

                }



                // setSessionMessages updates the visible state only if this room is

                // still active, so a late response cannot replace another room.

                setSessionMessages(sessionId, mergedHistory);

                flushStoredMessages(sessionId, mergedHistory);

            } catch (e) {

                console.error("Failed to load session messages from server:", e);

            }

        })();



        sessionFetchesRef.current[sessionId] = request;

        void request.finally(() => {

            if (sessionFetchesRef.current[sessionId] === request) {

                delete sessionFetchesRef.current[sessionId];

            }

        });

        return request;

    }, [setSessionMessages, flushStoredMessages]);



    // One account-scoped request supplies both history and quota to every chat consumer.

    const fetchSessions = useCallback((owner: string, background = false): Promise<void> => {

        if (accessRequestRef.current?.owner === owner) return accessRequestRef.current.promise;

        accessCheckedAtRef.current = Date.now();

        setAccessState(previous => background && previous.owner === owner && previous.status === "ready" ? previous : { owner, status: "loading" });

        const request = { owner, promise: Promise.resolve() };

        accessRequestRef.current = request;

        request.promise = (async () => {

            try {

                const res = await fetch("/api/ai-chat?action=sessions", {
                    headers: { ...getAuthHeaders() },
                });

                if (!res.ok) throw new Error("CHAT_ACCESS_UNAVAILABLE");

                const data = await res.json();

                if (accessOwnerRef.current !== owner) return;

                if (!Array.isArray(data.sessions) || typeof data.remaining_quota !== "number") throw new Error("CHAT_ACCESS_INVALID");

                const serverSessionIds = new Set(data.sessions.map((session: ChatSession) => session.id));

                setSessions(prevLocal => {

                    // Local session metadata is only a cache. Keep entries the

                    // authenticated server confirms so a prior account's rooms

                    // cannot remain selectable after an account change.

                    const localMap = new Map(prevLocal.filter(session => serverSessionIds.has(session.id)).map(s => [s.id, s]));

                    data.sessions.forEach((srvS: ChatSession) => localMap.set(srvS.id, srvS));

                    return Array.from(localMap.values()).sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

                });



                // On first load, localStorage may point at an older room that no

                // longer exists remotely. Prefer the server's newest room in that

                // case; keep the current room when it is still a server session.

                const activeId = activeSessionIdRef.current;

                const activeSessionObj = data.sessions.find((s: ChatSession) => s.id === activeId);

                const activeExistsOnServer = !!activeId && !!activeSessionObj;

                const activeIsTelegram = activeSessionObj ? isTelegramSessionMeta(activeSessionObj.title) : false;

                const activeSessionIsSending = !!activeId && !!loadingSessionIds.current[activeId];

                if ((!activeExistsOnServer || activeIsTelegram) && !activeSessionIsSending) {

                    const webSessions = data.sessions.filter((s: ChatSession) => !isTelegramSessionMeta(s.title));

                    if (webSessions.length === 0) {

                        // Clear room or start fresh when this account has no web rooms.

                        setActiveSessionId(null);

                        setMessages([]);

                    } else {

                        const latestWebSession = [...webSessions].sort(

                            (a: ChatSession, b: ChatSession) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()

                        )[0];

                        setActiveSessionId(latestWebSession.id);

                        const localMessages = sessionMessagesCache.current[latestWebSession.id] || getStoredMessages(latestWebSession.id);

                        if (localMessages.length > 0) {

                            const sanitized = localMessages.map(message => ({

                                ...message,

                                content: cleanChatText(message.content || ""),

                                suggestedButtons: message.suggestedButtons?.map(cleanChatText).filter(Boolean)

                            }));

                            sessionMessagesCache.current[latestWebSession.id] = sanitized;

                            setMessages(sanitized);

                        } else {

                            setMessages([]);

                        }

                        void fetchSessionMessages(latestWebSession.id);

                    }

                } else if (activeId && activeExistsOnServer && !activeSessionIsSending) {

                    // Always sync latest messages for the active room from server

                    void fetchSessionMessages(activeId);

                }

                setRemainingQuota(data.remaining_quota);

                if (typeof data.quota_limit === "number") setQuotaLimit(data.quota_limit);

                if (typeof data.is_pro === "boolean") {

                    setIsPro(data.is_pro);

                    if (typeof window !== "undefined") {

                        localStorage.setItem("egx_chat_pro_active", data.is_pro ? "true" : "false");

                    }

                }

                if (typeof data.autonomous_recommendations === "boolean") {

                    const isAutonomous = Boolean(data.is_pro && data.autonomous_recommendations);

                    setAutonomousRecommendationsState(isAutonomous);

                    if (typeof window !== "undefined") {

                        localStorage.setItem("artoro_autonomous_recs_enabled", String(isAutonomous));

                    }

                }

                setAccessState({ owner, status: "ready" });

            } catch (e) {

                if (accessOwnerRef.current === owner) setAccessState(previous => background && previous.owner === owner && previous.status === "ready" ? previous : { owner, status: "error" });

                console.error("Failed to fetch chat access:", e);

            } finally {

                if (accessRequestRef.current === request) accessRequestRef.current = null;

            }

        })();

        return request.promise;

    }, [setActiveSessionId, setSessions, fetchSessionMessages]);



    const retryAccess = useCallback(() => {

        if (!authLoading && userId) void fetchSessions(userId);

    }, [authLoading, userId, fetchSessions]);



    // Payment completion is an explicit refresh; ordinary token rotation is not.

    useEffect(() => {

        const onEntitlements = (event: Event) => {

            const detail = (event as CustomEvent)?.detail;

            if (detail && typeof detail.is_pro === "boolean") {

                setIsPro(detail.is_pro);

            }

            retryAccess();

        };

        const onStorage = (event: StorageEvent) => {

            if (event.key === "egx_entitlements_timestamp" || event.key === "egx_chat_pro_active") {

                if (typeof window !== "undefined") {

                    const stored = localStorage.getItem("egx_chat_pro_active") === "true";

                    setIsPro(stored);

                }

                retryAccess();

            }

        };

        window.addEventListener("egx:entitlements-updated", onEntitlements);

        window.addEventListener("storage", onStorage);

        return () => {

            window.removeEventListener("egx:entitlements-updated", onEntitlements);

            window.removeEventListener("storage", onStorage);

        };

    }, [retryAccess]);



    // Refresh on a real return to an open chat (or when opening the chat drawer) so Telegram quota deductions reflect right away.

    useEffect(() => {

        if (!authLoading && userId && isOpen && Date.now() - accessCheckedAtRef.current >= 4_000) {

            void fetchSessions(userId, true);

        }

    }, [isOpen, authLoading, userId, fetchSessions]);

    useEffect(() => {

        const onReturn = () => {

            if (authLoading || !userId || document.visibilityState !== "visible") return;

            if (!isOpen && !window.location.pathname.startsWith("/chat")) return;

            if (Date.now() - accessCheckedAtRef.current < 4_000) return;

            void fetchSessions(userId, true);

        };

        window.addEventListener("focus", onReturn);

        document.addEventListener("visibilitychange", onReturn);

        return () => {

            window.removeEventListener("focus", onReturn);

            document.removeEventListener("visibilitychange", onReturn);

        };

    }, [authLoading, userId, isOpen, fetchSessions]);



    // Switch active session instantly while preserving state

    const switchSession = useCallback(async (sessionId: string) => {

        if (activeSessionIdRef.current) {

            flushStoredMessages(activeSessionIdRef.current);

        }



        setActiveSessionId(sessionId);



        const isTargetLoading = !!loadingSessionIds.current[sessionId];

        setIsLoading(isTargetLoading);



        // 1. Memory Cache

        if (sessionMessagesCache.current[sessionId] && sessionMessagesCache.current[sessionId].length > 0) {

                setMessages(sessionMessagesCache.current[sessionId].map(message => ({ ...message, content: cleanChatText(message.content), suggestedButtons: message.suggestedButtons?.map(cleanChatText).filter(Boolean) })));

        } else {

            // 2. localStorage

            const localMsgs = getStoredMessages(sessionId);

            if (localMsgs.length > 0) {

                const sanitizedMessages = localMsgs.map(message => ({ ...message, content: cleanChatText(message.content), suggestedButtons: message.suggestedButtons?.map(cleanChatText).filter(Boolean) }));

                sessionMessagesCache.current[sessionId] = sanitizedMessages;

                setMessages(sanitizedMessages);

                // Keep the sanitized version in memory too; otherwise a later

                // switch can reintroduce unsanitized persisted text.

                sessionMessagesCache.current[sessionId] = sanitizedMessages;

            } else {

                setMessages([]);

            }

        }



        // 3. Fetch background sync from server

        await fetchSessionMessages(sessionId);

    }, [setActiveSessionId, flushStoredMessages, fetchSessionMessages]);



    const createNewSession = useCallback(() => {

        if (activeSessionIdRef.current) {

            flushStoredMessages(activeSessionIdRef.current);

        }

        setActiveSessionId(null);

        setMessages([]);

        setIsLoading(false);

    }, [setActiveSessionId, flushStoredMessages]);



    const deleteSession = useCallback(async (sessionId: string) => {

        if (saveTimersRef.current[sessionId]) {

            clearTimeout(saveTimersRef.current[sessionId]);

            delete saveTimersRef.current[sessionId];

        }

        delete sessionMessagesCache.current[sessionId];

        delete loadingSessionIds.current[sessionId];
        delete sessionMutationVersionRef.current[sessionId];
        delete lastLocalTurnAtRef.current[sessionId];

        if (typeof window !== "undefined") {

            localStorage.removeItem(`egxbots_msgs_${sessionId}`);

        }

        setSessions(prev => prev.filter(s => s.id !== sessionId));



        if (activeSessionIdRef.current === sessionId) {

            createNewSession();

        }



        try {

            await fetch(`/api/ai-chat?session_id=${sessionId}`, {
                method: "DELETE",
                headers: { ...getAuthHeaders() },
            });

        } catch (e) {

            console.error("Failed to delete chat session from server:", e);

        }

    }, [createNewSession, setSessions]);



    const renameSession = useCallback(async (sessionId: string, newTitle: string) => {

        setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title: newTitle } : s));

        try {

            await fetch("/api/ai-chat", {

                method: "PUT",

                headers: { "Content-Type": "application/json", ...getAuthHeaders() },

                body: JSON.stringify({ session_id: sessionId, title: newTitle })

            });

        } catch (e) {

            console.error("Failed to rename session on server:", e);

        }

    }, [setSessions]);



    useEffect(() => {

        if (authLoading) return;

        if (!userId) {

            setAccessState({ status: "loading" });

            setRemainingQuota(10);

            return;

        }

        void fetchSessions(userId);

    }, [authLoading, userId, fetchSessions]);



    const sendMessage = useCallback(async (text: string, imageInput?: string | string[], options?: { isVoice?: boolean; isVoiceNote?: boolean; isVoiceCall?: boolean; audioDuration?: number; voiceAudioUrl?: string }): Promise<any> => {

        text = cleanChatText(text);

        const imagesList: string[] = Array.isArray(imageInput)

            ? imageInput

            : (imageInput ? [imageInput] : []);



        if (!text.trim() && imagesList.length === 0) return;



        const activePro = isPro || (typeof window !== "undefined" && localStorage.getItem("egx_chat_pro_active") === "true");

        if (!activePro && imagesList.length > 0) {

            setShowUpgradeModal(true);

            return;

        }



        let currentSessionId = activeSessionIdRef.current;

        const currentSessionObj = currentSessionId ? sessions.find(s => s.id === currentSessionId) : null;

        const isCurrentTelegram = currentSessionObj ? isTelegramSessionMeta(currentSessionObj.title) : false;

        if (!currentSessionId || isCurrentTelegram) {

            currentSessionId = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : "session-" + Date.now();

            setActiveSessionId(currentSessionId);



            const sessionTitle = text.trim()

                ? text.trim().substring(0, 32) + (text.length > 32 ? "..." : "")

                : (imagesList.length > 0 ? "تحليل صورة محفظة" : "محادثة جديدة");



            setSessions(prev => [{

                id: currentSessionId!,

                title: sessionTitle,

                created_at: new Date().toISOString(),

                updated_at: new Date().toISOString()

            }, ...prev]);

        }



        // One request per session at a time. The server's idempotency key is

        // intentionally per client message, so a fast double-submit otherwise

        // creates two different keys and spends quota / produces two answers.

        // The previous behavior also aborted the first request below.

        if (loadingSessionIds.current[currentSessionId]) return;

        const normSubmitText = text.trim();
        const nowSubmitTs = Date.now();
        if (
            normSubmitText
            && imagesList.length === 0
            && !options?.isVoiceNote
            && lastSubmitRef.current
            && lastSubmitRef.current.sessionId === currentSessionId
            && lastSubmitRef.current.text === normSubmitText
            && (nowSubmitTs - lastSubmitRef.current.ts) < 3000
        ) {
            return;
        }
        lastSubmitRef.current = { sessionId: currentSessionId, text: normSubmitText, ts: nowSubmitTs };



        const isVoice = Boolean(options?.isVoice || options?.isVoiceNote || options?.isVoiceCall);
        const isVoiceNote = Boolean(options?.isVoiceNote);
        const isVoiceCall = Boolean(options?.isVoiceCall ?? (options?.isVoice && !options?.isVoiceNote));

        const userMsgId = typeof crypto !== "undefined" && crypto.randomUUID
            ? `user-${crypto.randomUUID()}`
            : `user-${nowSubmitTs}-${Math.random().toString(36).slice(2, 8)}`;

        const newUserMsg: ChatMessage = {

            id: userMsgId,

            role: "user",

            content: text || (isVoiceNote ? "رسالة صوتية 🎙️" : imagesList.length > 0 ? `📷 [${imagesList.length} Images attached]` : ""),

            timestamp: Date.now(),

            imageUrl: imagesList[0] || undefined,

            imagePreviewUrl: imagesList[0] || undefined,

            images: imagesList.length > 0 ? imagesList : undefined,

            isVoice,

            isVoiceNote,

            isVoiceCall,

            voiceAudioUrl: options?.voiceAudioUrl,

            voiceDuration: options?.audioDuration,

        };



        const existingSessionMsgs = sessionMessagesCache.current[currentSessionId] || [];

        const nextMessages = [...existingSessionMsgs, newUserMsg];



        sessionMutationVersionRef.current[currentSessionId] = (sessionMutationVersionRef.current[currentSessionId] || 0) + 1;

        loadingSessionIds.current[currentSessionId] = true;

        setSessionMessages(currentSessionId, nextMessages);

        if (activeSessionIdRef.current === currentSessionId) {

            setIsLoading(true);

        }



        // Create optimistic assistant message

        const assistantMsgId = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : "msg-" + Date.now();

        const assistantMsg: ChatMessage = {

            id: assistantMsgId,

            role: "assistant",

            content: "",

            timestamp: newUserMsg.timestamp + 1,

            isStreaming: true,

            statusText: isVoiceNote ? "أرتورو يستمع للرسالة الصوتية..." : "جاري تحليل السؤال...",

            answerStages: createInitialAnswerStages({
                hasImages: imagesList.length > 0,
                isVoiceNote: Boolean(isVoiceNote),
            }),

            isVoice,

            isVoiceNote,

            isVoiceCall,

        };



        const updateAssistantMsgInState = (updatedMsg: ChatMessage) => {

            setSessionMessages(currentSessionId!, prevMsgs => {

                const existingIndex = prevMsgs.findIndex(m => m.id === updatedMsg.id);

                if (existingIndex >= 0) {

                    const updated = [...prevMsgs];

                    updated[existingIndex] = { ...updatedMsg };

                    return updated;

                } else {

                    return [...prevMsgs, { ...updatedMsg }];

                }

            });

        };



        // Render initial optimistic assistant message

        updateAssistantMsgInState(assistantMsg);



        try {

            if (remainingQuota <= 0) {

                setShowUpgradeModal(true);

                assistantMsg.content = "لقد استهلكت باقتك المجانية (10/10 رسائل). تريد تحليلاً غير محدود لمحفظتك وتوصيات الأسهم لحظة بلحظة؟ اشترك الآن في باقة Pro (200 ج.م شهرياً) واحصل على 350 رسالة شهرياً، رفع صور المحفظة، التوصيات المفتوحة، وقناة الـ VIP.";

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = undefined;

                updateAssistantMsgInState(assistantMsg);

                flushStoredMessages(currentSessionId);

                return assistantMsg.content;

            }



            if (abortControllerRef.current) {

                abortControllerRef.current.abort();

            }

            abortControllerRef.current = new AbortController();



            const requestChartContext = chartContextRef.current;

            const requestChartOwner = chartOwnerRef.current;

            const requestChartGeneration = chartGenerationRef.current;

            const chatReq = createChatRequest({

                    message: text,

                    history: existingSessionMsgs.map(m => ({ role: m.role, content: m.content })),

                    images: imagesList,

                    model: selectedModel,

                    sessionId: currentSessionId,

                    clientMessageId: `${currentSessionId}:${newUserMsg.timestamp}`,

                    chartContext: requestChartContext,

                    autonomousRecommendations,

                    isVoice,

                    isVoiceCall,

                    isVoiceNote,

                    audioDuration: options?.audioDuration,

                    voiceAudioUrl: options?.voiceAudioUrl,

                });

            const currentMarket: "egx" | "tasi" =
                typeof window !== "undefined" && localStorage.getItem("egxbots_market") === "tasi"
                    ? "tasi"
                    : activeMarket;

            const parsedChatBody = JSON.parse(chatReq.body) as Record<string, unknown>;
            parsedChatBody.market = currentMarket;

            const response = await fetch("/api/ai-chat", {

                ...chatReq,

                body: JSON.stringify(parsedChatBody),

                headers: {

                    ...chatReq.headers,

                    ...getAuthHeaders(),

                    "x-egxbots-market": currentMarket,

                },

                signal: abortControllerRef.current.signal,

            });



            if (response.status === 429) {

                setRemainingQuota(0);

                setShowUpgradeModal(true);

                let detail = "لقد استهلكت باقتك المجانية (10/10 رسائل). اشترك الآن في باقة Pro بـ 200 ج.م شهرياً واحصل على 350 رسالة شهرياً، رفع صور المحفظة، التوصيات المفتوحة، وقناة توصيات VIP!";

                try {

                    const data = await response.json();

                    if (data.detail && typeof data.detail === "string") {

                        detail = data.detail;

                    }

                } catch {}

                assistantMsg.content = detail;

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = undefined;

                updateAssistantMsgInState(assistantMsg);

                flushStoredMessages(currentSessionId);

                return assistantMsg.content;

            }



            if (response.status === 504 || response.status === 502) {

                assistantMsg.content = "استغرقت الاستجابة وقتاً أطول من المعتاد بسبب الضغط على الموديل. يرجى إعادة المحاولة أو اختيار موديل أسرع مثل Llama 3.1 8B ⚡";

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = undefined;

                updateAssistantMsgInState(assistantMsg);

                flushStoredMessages(currentSessionId);

                return assistantMsg.content;

            }



            if (response.status === 401) {

                assistantMsg.content = "تحتاج إلى تسجيل الدخول لاستخدام المساعد الذكي. سجّل دخولك من زر الحساب أعلى الصفحة ثم أعد إرسال سؤالك.";

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = undefined;

                updateAssistantMsgInState(assistantMsg);

                flushStoredMessages(currentSessionId);

                return assistantMsg.content;

            }



            if (!response.ok) {

                let errorMsg = "حدث خطأ في السيرفر أثناء معالجة الطلب. يرجى المحاولة مرة أخرى لاحقاً.";

                try {

                    const data = await response.json();

                    if (data.detail) errorMsg = data.detail;

                } catch {}

                assistantMsg.content = errorMsg;

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = undefined;

                updateAssistantMsgInState(assistantMsg);

                flushStoredMessages(currentSessionId);

                return assistantMsg.content;

            }



            const contentType = response.headers.get("content-type") || "";



            // Fallback for non-streaming JSON responses

            if (contentType.includes("application/json") || !response.body) {

                const data = await response.json();

                publishChartActions(data.chart_actions, requestChartContext, requestChartOwner, requestChartGeneration);

                if (data.enable_autonomous_recs === true) {

                    setAutonomousRecommendations(true);

                }

                if (data.remaining_quota !== undefined) {

                    setRemainingQuota(data.remaining_quota);

                    invalidateUserQuotaCache(userId);

                    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("egx:chat-quota-updated"));

                }

                if (data.quota_limit !== undefined) {

                    setQuotaLimit(data.quota_limit);

                }

                if (data.is_pro !== undefined) {

                    setIsPro(Boolean(data.is_pro));

                }

                assistantMsg.content = stripMarkdownTables(sanitizeReply(data.reply || "معذرة، لم أتمكن من معالجة هذا الطلب."));

                assistantMsg.tables = Array.isArray(data.tables) ? data.tables : undefined;

                if (typeof data.spoken_text === "string") assistantMsg.spokenText = data.spoken_text;

                assistantMsg.suggestedButtons = Array.isArray(data.suggested_buttons) ? data.suggested_buttons.map((button: unknown) => sanitizeUiLabel(String(button))).filter(Boolean) : undefined;

                assistantMsg.latencyMs = data.latency_ms || (Date.now() - newUserMsg.timestamp);

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = finalizeAnswerStages(assistantMsg.answerStages, {
                    toolsUsed: Array.isArray(data.usage?.tools_used) ? data.usage.tools_used : undefined,
                    cached: Boolean(data.cached),
                });

                updateAssistantMsgInState(assistantMsg);

                flushStoredMessages(currentSessionId);

                return assistantMsg.content;

            }



            // SSE ReadableStream reading

            const reader = response.body.getReader();

            const decoder = new TextDecoder("utf-8");

            let buffer = "";

            let currentEventName = "";

            let lastRenderTime = 0;

            let receivedDone = false;

            let receivedError = false;



            while (true) {

                const { done, value } = await reader.read();

                if (done) break;



                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split("\n");

                buffer = lines.pop() || "";



                for (const line of lines) {

                    const trimmed = line.trim();

                    if (!trimmed) {

                        currentEventName = "";

                        continue;

                    }



                    if (trimmed.startsWith("event:")) {

                        currentEventName = trimmed.slice(6).trim();

                        continue;

                    }



                    if (trimmed.startsWith("data:")) {

                        const dataStr = trimmed.slice(5).trim();

                        if (dataStr === "[DONE]") {

                            // The transport marker alone does not carry the canonical

                            // answer, tables or quota; require the JSON done event.

                            continue;

                        }



                        try {

                            const parsed = JSON.parse(dataStr);



                            if (parsed.type === "error") {

                                receivedError = true;

                                assistantMsg.content = sanitizeReply(parsed.detail || "حدث خطأ في السيرفر أثناء معالجة الطلب. يرجى المحاولة مرة أخرى لاحقاً.");

                                assistantMsg.isStreaming = false;

                                assistantMsg.statusText = undefined;

                                assistantMsg.answerStages = undefined;

                                updateAssistantMsgInState(assistantMsg);

                            } else if (currentEventName === "enable_autonomous_recs" || parsed.type === "enable_autonomous_recs") {

                                setAutonomousRecommendations(true);

                            } else if (currentEventName === "disable_autonomous_recs" || parsed.type === "disable_autonomous_recs") {

                                setAutonomousRecommendations(false);

                            } else if (parsed.type === "image_urls" && Array.isArray(parsed.image_urls) && parsed.image_urls.length > 0) {

                                setSessionMessages(currentSessionId, prevMsgs => 

                                    prevMsgs.map(m => (m.timestamp === newUserMsg.timestamp ? { ...m, imageUrl: parsed.image_urls[0], images: parsed.image_urls } : m))

                                );

                            } else if (parsed.type === "tables" && Array.isArray(parsed.data)) {

                                assistantMsg.tables = parsed.data;

                                updateAssistantMsgInState(assistantMsg);

                            } else if (currentEventName === "status" || parsed.type === "status" || parsed.event === "status" || parsed.status) {

                                const rawCandidate = parsed.message || parsed.content;

                                const statusMsg = typeof rawCandidate === "string" && !_RAW_STATUS_CODES.has(rawCandidate.trim())
                                    ? rawCandidate.trim()
                                    : undefined;

                                assistantMsg.answerStages = advanceAnswerStagesOnStatus(assistantMsg.answerStages, parsed);

                                if (statusMsg) {

                                    assistantMsg.statusText = statusMsg;

                                }

                                updateAssistantMsgInState(assistantMsg);

                            } else if (currentEventName === "token" || parsed.type === "token" || parsed.event === "token" || parsed.token !== undefined || parsed.delta !== undefined) {

                                 const token = parsed.token ?? parsed.delta ?? parsed.content ?? parsed.text ?? "";

                                 // Accumulate stream tokens raw; sanitize once after the stream ends.

                                 // sanitizeReply adds structured output/disclaimers and is not token-safe.

                                 const isFirstToken = !assistantMsg.content && Boolean(token);

                                 if (isFirstToken && assistantMsg.answerStages) {

                                     assistantMsg.answerStages = advanceAnswerStagesOnToken(assistantMsg.answerStages);

                                     assistantMsg.statusText = undefined;

                                     lastRenderTime = 0;

                                 }

                                 assistantMsg.content += token;

                                assistantMsg.isStreaming = true;

                                

                                const now = Date.now();

                                if (now - lastRenderTime > 35) {

                                    lastRenderTime = now;

                                    updateAssistantMsgInState(assistantMsg);

                                }

                            } else if (currentEventName === "done" || parsed.type === "done" || parsed.event === "done") {

                                receivedDone = true;

                                publishChartActions(parsed.chart_actions, requestChartContext, requestChartOwner, requestChartGeneration);

                                if (
                                    typeof window !== "undefined" &&
                                    Array.isArray(parsed.usage?.tools_used) &&
                                    parsed.usage.tools_used.includes("manage_portfolio")
                                ) {
                                    window.dispatchEvent(new Event("portfolio-updated"));
                                }

                                if (parsed.enable_autonomous_recs === true) {

                                    setAutonomousRecommendations(true);

                                } else if (parsed.disable_autonomous_recs === true) {

                                    setAutonomousRecommendations(false);

                                }

                                if (parsed.reply) {

                                    assistantMsg.content = stripMarkdownTables(sanitizeReply(parsed.reply));

                                } else if (assistantMsg.content) {

                                    assistantMsg.content = stripMarkdownTables(sanitizeReply(assistantMsg.content));

                                }

                                if (parsed.spoken_text || parsed.spokenText) {

                                    assistantMsg.spokenText = parsed.spoken_text || parsed.spokenText;

                                }

                                if (Array.isArray(parsed.suggested_buttons)) {

                                    assistantMsg.suggestedButtons = parsed.suggested_buttons.map((button: unknown) => sanitizeUiLabel(String(button))).filter(Boolean);

                                }

                                if (Array.isArray(parsed.tables)) assistantMsg.tables = parsed.tables;

                                if (parsed.remaining_quota !== undefined) {

                                    setRemainingQuota(parsed.remaining_quota);

                                    invalidateUserQuotaCache(userId);

                                    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("egx:chat-quota-updated"));

                                }

                                if (parsed.quota_limit !== undefined) {

                                    setQuotaLimit(parsed.quota_limit);

                                }

                                if (parsed.is_pro !== undefined) {

                                    setIsPro(Boolean(parsed.is_pro));

                                }

                                assistantMsg.latencyMs = parsed.latency_ms || (Date.now() - newUserMsg.timestamp);

                                assistantMsg.isStreaming = false;

                                assistantMsg.statusText = undefined;

                                assistantMsg.answerStages = finalizeAnswerStages(assistantMsg.answerStages, {
                                    toolsUsed: Array.isArray(parsed.usage?.tools_used) ? parsed.usage.tools_used : undefined,
                                    cached: Boolean(parsed.cached),
                                });

                                updateAssistantMsgInState(assistantMsg);

                            } else {

                                if (parsed.status || parsed.step_id) {

                                    assistantMsg.answerStages = advanceAnswerStagesOnStatus(assistantMsg.answerStages, parsed);

                                    const rawFallback = parsed.message || parsed.content;

                                    if (typeof rawFallback === "string" && !_RAW_STATUS_CODES.has(rawFallback.trim())) {

                                        assistantMsg.statusText = rawFallback.trim();

                                    }

                                }

                                if (parsed.token || parsed.delta || parsed.text) {

                                     assistantMsg.content += (parsed.token || parsed.delta || parsed.text);

                                } else if (parsed.reply && !assistantMsg.content) {

                                    assistantMsg.content = sanitizeReply(parsed.reply);

                                }

                                if (Array.isArray(parsed.suggested_buttons)) {

                                    assistantMsg.suggestedButtons = parsed.suggested_buttons.map((button: unknown) => sanitizeUiLabel(String(button))).filter(Boolean);

                                }

                                if (parsed.remaining_quota !== undefined) {

                                    setRemainingQuota(parsed.remaining_quota);

                                    invalidateUserQuotaCache(userId);

                                    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("egx:chat-quota-updated"));

                                }

                                if (parsed.quota_limit !== undefined) {

                                    setQuotaLimit(parsed.quota_limit);

                                }

                                if (parsed.is_pro !== undefined) {

                                    setIsPro(Boolean(parsed.is_pro));

                                }

                                updateAssistantMsgInState(assistantMsg);

                            }

                        } catch {

                            // Raw string token in data field

                             assistantMsg.content += dataStr;

                            assistantMsg.isStreaming = true;

                            updateAssistantMsgInState(assistantMsg);

                        }

                    }

                }

            }



            // Stream complete

            if (!receivedDone && !receivedError) {

                assistantMsg.content = assistantMsg.content

                    ? `${stripMarkdownTables(sanitizeReply(assistantMsg.content))}\n\nالرد انقطع قبل اكتماله. يمكنك الضغط على إعادة المحاولة أو إرسال: كمل الرد.`

                    : "الرد انقطع قبل اكتماله. يرجى إعادة المحاولة.";

                assistantMsg.isStreaming = false;

                assistantMsg.statusText = undefined;

                assistantMsg.answerStages = undefined;

                updateAssistantMsgInState(assistantMsg);

                return assistantMsg.content;

            }

            assistantMsg.isStreaming = false;

            assistantMsg.answerStages = receivedError ? undefined : finalizeAnswerStages(assistantMsg.answerStages);

            if (!assistantMsg.content && assistantMsg.statusText) {

                assistantMsg.content = sanitizeUiLabel(assistantMsg.statusText);

            } else {

                assistantMsg.content = stripMarkdownTables(sanitizeReply(assistantMsg.content));

            }

            assistantMsg.statusText = undefined;

            updateAssistantMsgInState(assistantMsg);

            flushStoredMessages(currentSessionId);

            return assistantMsg.content;



        } catch (err: any) {

            if (err.name === "AbortError" || err.message?.includes("aborted") || err.message === "The user aborted a request.") {

                console.log("Chat request aborted by user");

                if (!assistantMsg.content) {

                    assistantMsg.content = "تم إيقاف الاستجابة بناءً على طلبك.";

                }

            } else if (err.name === "TypeError" && (err.message?.includes("fetch") || err.message?.includes("Failed to fetch") || err.message?.includes("network"))) {

                assistantMsg.content = "تعذر الاتصال بالشبكة. يرجى التحقق من اتصالك بالإنترنت وتجربة المحاولة مرة أخرى.";

            } else {

                    assistantMsg.content = sanitizeReply(err.message || "حدث خطأ أثناء الاتصال بالذكاء الاصطناعي.");

            }

            assistantMsg.isStreaming = false;

            assistantMsg.statusText = undefined;

            assistantMsg.answerStages = undefined;

            updateAssistantMsgInState(assistantMsg);

            flushStoredMessages(currentSessionId);

            return assistantMsg.content;

        } finally {

            abortControllerRef.current = null;

            lastLocalTurnAtRef.current[currentSessionId] = Date.now();
            sessionMutationVersionRef.current[currentSessionId] = (sessionMutationVersionRef.current[currentSessionId] || 0) + 1;

            loadingSessionIds.current[currentSessionId] = false;

            if (activeSessionIdRef.current === currentSessionId) {

                setIsLoading(false);

            }

        }

    }, [remainingQuota, selectedModel, setActiveSessionId, setSessions, setSessionMessages, flushStoredMessages, autonomousRecommendations, activeMarket]);



    return (

        <ChatContext.Provider value={{

            isOpen,

            setIsOpen,

            messages,

            sendMessage,

            stopResponding,

            isLoading,

            remainingQuota,

            quotaLimit,

            isPro,

            isInitializing,

            accessError,

            retryAccess,

            showUpgradeModal,

            setShowUpgradeModal,

            selectedModel,

            setSelectedModel,

            sessions,

            activeSessionId,

            createNewSession,

            switchSession,

            deleteSession,

            renameSession,

            isSidebarOpen,

            setIsSidebarOpen,

            autonomousRecommendations,

            setAutonomousRecommendations,

            isAccessReady: accessState.status === "ready"

        }}>

            {children}

        </ChatContext.Provider>

    );

}



export function useChat() {

    const context = useContext(ChatContext);

    if (!context) throw new Error("useChat must be used within ChatProvider");

    return context;

}

