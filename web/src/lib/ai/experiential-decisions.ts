import { awaitExecution, executionFetch } from "./execution";
import type { AgenticToolCall } from "./agentic-pipeline";
import { getExperientialApiKey } from "./server-secrets";

export const LUNA_DECISIONS_MODEL = "gpt-6-luna-decisions";
export const EXPERIENTIAL_DECISIONS_URL = "https://api.experientiallabs.ai/v1/decisions";

export interface LunaQuestionChoice {
    value: string;
    description: string;
}

export type LunaDecisionQuestion =
    | {
          type: "choice";
          name: string;
          instructions: string;
          choices: LunaQuestionChoice[];
      }
    | {
          type: "predicate";
          name: string;
          instructions: string;
      }
    | {
          type: "score";
          name: string;
          instructions: string;
          min: number;
          max: number;
      };

export interface LunaDecisionAnswer {
    type: "choice" | "predicate" | "score";
    name: string;
    choice?: string;
    answer?: boolean;
    probability?: number;
    probability_true?: number;
    expected?: number;
    confidence?: number;
    probabilities?: Array<{ value: string; probability: number }>;
}

export interface LunaDecisionsResponse {
    model: string;
    answers: LunaDecisionAnswer[];
    usage?: {
        input_tokens?: number;
        output_tokens?: number;
        total_tokens?: number;
        cost?: number;
    };
}

export async function callLunaDecisions(
    input: string,
    questions: LunaDecisionQuestion[],
    apiKey?: string | null
): Promise<LunaDecisionsResponse> {
    const key = (apiKey || getExperientialApiKey())?.trim();
    if (!key) {
        throw new Error("EXPERIENTIAL_API_KEY_UNAVAILABLE");
    }

    const payload = {
        model: LUNA_DECISIONS_MODEL,
        input,
        questions,
    };

    const response = await executionFetch(EXPERIENTIAL_DECISIONS_URL, {
        method: "POST",
        headers: {
            Authorization: `Bearer ${key}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errText = await awaitExecution(response.text().catch(() => ""));
        throw new Error(`LUNA_DECISIONS_HTTP_${response.status}: ${errText.slice(0, 240)}`);
    }

    return (await awaitExecution(response.json())) as LunaDecisionsResponse;
}

export function getAnswerByName(
    result: LunaDecisionsResponse | null | undefined,
    name: string
): LunaDecisionAnswer | undefined {
    return result?.answers?.find((a) => a.name === name);
}

/**
 * Uses gpt-6-luna-decisions (/v1/decisions) to decide which platform tools to invoke
 * for the user's Arabic query and session context.
 */
export async function decideToolsWithLuna(
    userMessage: string,
    symbolHints: Array<{ symbol?: string; symbols?: string[]; name?: string; name_ar?: string | null; name_en?: string | null }>,
    sessionSymbols: string[],
    apiKey?: string | null
): Promise<{
    intent: string;
    calls: AgenticToolCall[];
    socialGreeting: boolean;
    usage?: LunaDecisionsResponse["usage"];
}> {
    const extractedHintSymbols = symbolHints.flatMap((h) => [
        ...(h.symbol ? [String(h.symbol).toUpperCase()] : []),
        ...(Array.isArray(h.symbols) ? h.symbols.map((s) => String(s || "").toUpperCase()) : []),
    ]).filter(Boolean);

    const candidateSymbols = Array.from(
        new Set([
            ...extractedHintSymbols,
            ...sessionSymbols.map((s) => String(s || "").toUpperCase()).filter(Boolean),
        ])
    ).slice(0, 5);

    const decisionInput = JSON.stringify({
        user_query: userMessage,
        matched_symbols_in_query: symbolHints,
        previous_session_symbols: sessionSymbols.slice(0, 5),
    });

    const questions: LunaDecisionQuestion[] = [
        {
            type: "choice",
            name: "primary_intent",
            instructions:
                "Determine the user's primary intent for the Egyptian Exchange (EGX) assistant based on user_query and matched_symbols_in_query.",
            choices: [
                {
                    value: "analyze_stock",
                    description:
                        "Analyze one or more specific stocks (technical analysis, support/resistance levels, fundamentals, news, or opinion on a stock).",
                },
                {
                    value: "compare_stocks",
                    description: "Compare two or more stocks side-by-side.",
                },
                {
                    value: "market_summary",
                    description:
                        "General market summary, EGX30 index status, top gainers, top losers, or market breadth.",
                },
                {
                    value: "recommendations",
                    description:
                        "Active buy recommendations, trading signals, speculation requests (سهم للمضاربة / زيرو / رشحلي سهم), or past recommendation performance.",
                },
                {
                    value: "accumulation",
                    description:
                        "Smart money accumulation stocks (أسهم التجميع / السيولة الذكية / وايكوف).",
                },
                {
                    value: "technical_scan",
                    description:
                        "Technical scanner preset (momentum and volume, RSI oversold, MACD golden cross).",
                },
                {
                    value: "news",
                    description: "Latest market news or stock disclosures.",
                },
                {
                    value: "portfolio",
                    description: "View or analyze the user's saved investment portfolio.",
                },
                {
                    value: "social_greeting",
                    description:
                        "Simple greeting, hello, thank you, or who are you without any market or stock question.",
                },
            ],
        },
        {
            type: "choice",
            name: "scan_preset",
            instructions:
                "If the user is asking for a technical scan, select the closest preset.",
            choices: [
                {
                    value: "momentum_and_volume",
                    description: "Strongest momentum and relative volume",
                },
                {
                    value: "rsi_oversold",
                    description: "Oversold stocks (low RSI < 30)",
                },
                {
                    value: "macd_cross",
                    description: "Bullish MACD crossover",
                },
                {
                    value: "smart_money_flow",
                    description: "Smart money liquidity inflow",
                },
            ],
        },
    ];

    const decisionRes = await callLunaDecisions(decisionInput, questions, apiKey);
    const primaryIntent =
        getAnswerByName(decisionRes, "primary_intent")?.choice ||
        (candidateSymbols.length > 0 ? "analyze_stock" : "market_summary");
    const scanPreset =
        getAnswerByName(decisionRes, "scan_preset")?.choice || "momentum_and_volume";

    if (primaryIntent === "social_greeting" && extractedHintSymbols.length === 0) {
        return {
            intent: "social_greeting",
            calls: [],
            socialGreeting: true,
            usage: decisionRes.usage,
        };
    }

    const calls: AgenticToolCall[] = [];
    const addCall = (name: string, args: Record<string, any>) => {
        calls.push({
            id: `luna_call_${calls.length + 1}_${Date.now()}`,
            type: "function",
            function: {
                name,
                arguments: JSON.stringify(args),
            },
        });
    };

    const targetSymbols =
        extractedHintSymbols.length > 0
            ? extractedHintSymbols.slice(0, 4)
            : candidateSymbols.slice(0, 2);

    if (primaryIntent === "compare_stocks" && targetSymbols.length >= 2) {
        addCall("get_comparison", { symbols: targetSymbols });
        addCall("get_stock_levels", { symbols: targetSymbols });
    } else if (primaryIntent === "analyze_stock" || (targetSymbols.length > 0 && primaryIntent !== "recommendations")) {
        const syms = targetSymbols.length > 0 ? targetSymbols : ["COMI"];
        addCall("get_stock", { symbols: syms });
        addCall("get_stock_levels", { symbols: syms });
        for (const sym of syms.slice(0, 2)) {
            addCall("get_fundamentals", { symbol: sym });
            addCall("get_corporate_actions", { symbol: sym });
        }
        addCall("get_news", { symbols: syms });
    } else if (primaryIntent === "recommendations") {
        addCall("get_recommendations", { status: "open" });
        addCall("get_market", {});
    } else if (primaryIntent === "accumulation") {
        addCall("get_accumulation_stocks", { limit: 10 });
    } else if (primaryIntent === "technical_scan") {
        addCall("get_technical_scan", { preset: scanPreset });
    } else if (primaryIntent === "news") {
        addCall("get_news", targetSymbols.length ? { symbols: targetSymbols } : {});
    } else if (primaryIntent === "portfolio") {
        addCall("manage_portfolio", { operation: "view" });
    } else {
        addCall("get_market", {});
        addCall("get_market_breadth", {});
    }

    return {
        intent: primaryIntent,
        calls,
        socialGreeting: false,
        usage: decisionRes.usage,
    };
}

export function renderLunaStockDashboard(
    evidence: any[],
    savedPositions: Array<{ symbol: string; quantity?: number; entry_price?: number }> = []
): string | null {
    const stockEv = evidence.find((e) => e.tool === "get_stock" && e.availability === "available");
    const levelsEv = evidence.find((e) => e.tool === "get_stock_levels" && e.availability === "available");
    const stocks: any[] = stockEv?.data?.stocks || [];
    const levelsList: any[] = levelsEv?.data?.levels || [];
    if (!stocks.length && !levelsList.length) return null;

    const symbols = Array.from(
        new Set([...stocks.map((s) => s.symbol), ...levelsList.map((l) => l.symbol)].filter(Boolean))
    );
    if (!symbols.length) return null;

    const fmt = (v: unknown) =>
        typeof v === "number" && Number.isFinite(v)
            ? v.toLocaleString("en-US", { maximumFractionDigits: 2 })
            : null;

    const sections: string[] = [];
    for (const sym of symbols.slice(0, 4)) {
        const s = stocks.find((row) => row.symbol === sym) || {};
        const l = levelsList.find((row) => row.symbol === sym) || {};
        const fundEv = evidence.find(
            (e) => e.tool === "get_fundamentals" && e.symbols?.includes(sym) && e.availability === "available"
        );
        const f = fundEv?.data?.fundamentals || fundEv?.data || {};
        const newsEv = evidence.find((e) => e.tool === "get_news" && e.availability === "available");
        const newsItems = (newsEv?.data?.news || []).filter(
            (n: any) => !n.symbol || String(n.symbol).toUpperCase() === sym
        );

        const nameAr = s.name_ar || l.name_ar || s.name || l.name || sym;
        const close = s.close ?? l.close ?? s.current_price;
        const date = String(s.date || l.date || "").slice(0, 10);
        const changePct = s.change_pct ?? l.change_pct;
        const rsi = s.rsi_14 ?? l.rsi_14;
        const macd = s.macd ?? l.macd;
        const macdSignal = s.macd_signal ?? l.macd_signal;
        const ema50 = s.ema_50 ?? l.ema_50;
        const ema200 = s.ema_200 ?? l.ema_200;
        const rvol = s.r_vol ?? l.r_vol;

        let badge = "🟡 حيادي للمراقبة";
        if (typeof close === "number" && typeof ema50 === "number" && typeof rsi === "number") {
            if (close > ema50 && rsi >= 52 && rsi <= 70) badge = "🟢 إيجابي / زخم صاعد";
            else if (close < ema50 && rsi < 45) badge = "🔴 سلبي / ضغوط بيعية";
        }

        const pos = savedPositions.find((p) => String(p.symbol || "").toUpperCase() === sym);
        const posLine =
            pos && pos.quantity && pos.entry_price && typeof close === "number"
                ? `📌 **حالة السهم في محفظتك:** مسجل لديك ${fmt(pos.quantity)} سهم بمتوسط شراء ${fmt(pos.entry_price)} ج.م (العائد غير المحقق: ${(((close - pos.entry_price) / pos.entry_price) * 100).toFixed(2)}%).`
                : `📌 **حالة السهم في محفظتك:** السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة.`;

        const levelRows: string[] = [];
        if (fmt(close)) levelRows.push(`| الإغلاق الحالي | ${fmt(close)} | آخر إغلاق يومي مسجل (${date || "مؤرخ"}) |`);
        if (fmt(l.support)) levelRows.push(`| الدعم الأول | ${fmt(l.support)} | منطقة ارتكاز أولى؛ كسرها يضعف السيناريو |`);
        if (fmt(l.support_2)) levelRows.push(`| الدعم الثاني | ${fmt(l.support_2)} | دعم تاريخي طويل المدى |`);
        if (fmt(l.resistance)) levelRows.push(`| المقاومة الأولى | ${fmt(l.resistance)} | حاجز عرض قريب؛ اختراقه يدعم الإيجابية |`);
        if (fmt(l.resistance_2)) levelRows.push(`| المقاومة الثانية | ${fmt(l.resistance_2)} | قمة تاريخية ومقاومة رئيسية |`);

        if (l.has_active_recommendation && l.active_recommendation) {
            const rec = l.active_recommendation;
            if (fmt(rec.entry_price)) levelRows.push(`| سعر الدخول المعتمد | ${fmt(rec.entry_price)} | وفق إشارة المنصة المفتوحة |`);
            if (fmt(rec.stop_loss)) levelRows.push(`| وقف الخسارة (Stop Loss) | ${fmt(rec.stop_loss)} | حماية صارمة لرأس المال |`);
            if (fmt(rec.target_price)) levelRows.push(`| المستهدف الفني | ${fmt(rec.target_price)} | منطقة جني أرباح معتمدة |`);
        }

        const indRows: string[] = [];
        if (fmt(rsi)) {
            const rsiDesc = rsi < 30 ? "منطقة تشبع بيعي" : rsi > 70 ? "منطقة تشبع شرائي" : "نطاق متوازن بين التشبعين";
            indRows.push(`| مؤشر القوة النسبية (RSI) | ${fmt(rsi)} | ${rsiDesc} |`);
        }
        if (fmt(macd) && fmt(macdSignal)) {
            const macdDesc = macd > macdSignal ? "أعلى خط الإشارة (زخم داعم)" : "أسفل خط الإشارة (زخم ضعيف)";
            indRows.push(`| مؤشر الماكد (MACD) | ${fmt(macd)} | ${macdDesc} |`);
        }
        if (fmt(ema50)) {
            indRows.push(`| متوسط EMA 50 | ${fmt(ema50)} | ${close > ema50 ? "السعر يتداول أعلاه" : "السعر يتداول دونه"} |`);
        }
        if (fmt(ema200)) {
            indRows.push(`| متوسط EMA 200 | ${fmt(ema200)} | ${close > ema200 ? "اتجاه عام صاعد" : "تحت المتوسط الطويل"} |`);
        }
        if (fmt(rvol)) {
            indRows.push(`| الحجم النسبي (r_vol) | ${fmt(rvol)}x | ${rvol >= 1 ? "نشاط سيولة أعلى من المتوسط" : "سيولة أقل من المتوسط"} |`);
        }
        if (fmt(f.pe_ratio)) {
            indRows.push(`| مضاعف الربحية (P/E) | ${fmt(f.pe_ratio)}x | تقييم مكرر الربحية |`);
        }
        if (fmt(f.eps)) {
            indRows.push(`| ربحية السهم (EPS) | ${fmt(f.eps)} ج.م | نصيب السهم من الأرباح |`);
        }

        const changeStr =
            typeof changePct === "number" && Number.isFinite(changePct)
                ? ` (${changePct >= 0 ? "+" : ""}${fmt(changePct)}% بتاريخ ${date})`
                : date
                ? ` (بتاريخ ${date})`
                : "";

        const newsLines =
            newsItems.length > 0
                ? newsItems
                      .slice(0, 3)
                      .map((n: any) => {
                          const dStr = String(n.date || n.published_at || n.record_date || "").slice(0, 10);
                          const textStr = Array.isArray(n.headlines) && n.headlines.length > 0
                              ? n.headlines.slice(0, 3).join(" | ")
                              : n.headline || n.title || "لا توجد تفاصيل";
                          return `- **${dStr}:** ${textStr}`;
                      })
                      .join("\n")
                : "- لا توجد إفصاحات أو أخبار جوهرية مسجلة للسهم خلال آخر 7 أيام.";

        const card = [
            `### 📊 تحليل سهم ${nameAr} (${sym})`,
            `**السعر الأخير:** ${fmt(close) || "—"} ج.م${changeStr} | **التقييم الفني العام:** ${badge}`,
            posLine,
            "",
            `#### 🎯 المستويات الفنية والمحاور السعرية`,
            `| المستوى / النقطة | القيمة (ج.م) | الوصف الفني |`,
            `|---|---:|---|`,
            ...levelRows,
            "",
            `#### 📈 المؤشرات الفنية والبيانات الأساسية`,
            `| المؤشر / المقياس | القيمة | القراءة والتقييم |`,
            `|---|---:|---|`,
            ...indRows,
            "",
            `#### 📰 أحدث الأخبار والإفصاحات`,
            newsLines,
        ].join("\n");

        sections.push(card);
    }

    return sections.join("\n\n---\n\n");
}

/**
 * Uses gpt-6-luna-decisions (/v1/decisions) to review a proposed response draft
 * against the supplied tool evidence and produce a structured analytical decision card.
 */
export async function reviewAndSynthesizeWithLuna(
    userMessage: string,
    compactEvidences: any[],
    draftReply: string,
    apiKey?: string | null
): Promise<{
    reviewChoice: "accept" | "review";
    technicalStance: string;
    actionPlan: string;
    confidencePct: number;
    decisionCardAr: string;
    usage?: LunaDecisionsResponse["usage"];
}> {
    const availableEvidences = compactEvidences
        .filter((e) => e && e.availability === "available")
        .map((e) => ({ tool: e.tool, symbols: e.symbols, data: e.data }));
    const inputPayload = [
        `Task: Provide an Egyptian Exchange (EGX) market/stock analysis for the user query: "${userMessage}".`,
        `Supplied Database Evidence: ${JSON.stringify(availableEvidences.slice(0, 4)).slice(0, 2600)}`,
        `Generated Analysis Card: ${draftReply.slice(0, 2200)}`,
    ].join("\n\n");

    const questions: LunaDecisionQuestion[] = [
        {
            type: "choice",
            name: "grounding_verdict",
            instructions:
                "Are the prices, support/resistance levels, and technical indicators in Generated Analysis Card derived from Supplied Database Evidence?",
            choices: [
                {
                    value: "verified",
                    description:
                        "Yes, the prices, levels, and indicators in Generated Analysis Card are derived from Supplied Database Evidence.",
                },
                {
                    value: "ungrounded",
                    description:
                        "No, Generated Analysis Card invents fake stock prices that contradict Supplied Database Evidence.",
                },
            ],
        },
        {
            type: "choice",
            name: "technical_stance",
            instructions:
                "Based on Verified Tool Evidence, select the overall technical assessment.",
            choices: [
                {
                    value: "bullish_positive",
                    description:
                        "Positive / Bullish momentum supported by technical indicators above key support.",
                },
                {
                    value: "neutral_consolidation",
                    description:
                        "Neutral / Sideways consolidation between support and resistance; requires monitoring.",
                },
                {
                    value: "bearish_caution",
                    description:
                        "Bearish / Selling pressure or negative momentum; requires caution and strict support watch.",
                },
                {
                    value: "oversold_watch",
                    description:
                        "Oversold territory near support levels; watch for reversal confirmation before acting.",
                },
            ],
        },
        {
            type: "choice",
            name: "action_plan",
            instructions:
                "Select the most disciplined risk-management action plan supported by the platform evidence.",
            choices: [
                {
                    value: "follow_active_signal",
                    description:
                        "An official open recommendation exists: follow its approved entry zone, stop loss, and target levels.",
                },
                {
                    value: "monitor_support_level",
                    description:
                        "No active buy signal: monitor the primary support level for stability and avoid premature entry.",
                },
                {
                    value: "watch_resistance_breakout",
                    description:
                        "Monitor price action near first resistance for a confirmed high-volume breakout.",
                },
                {
                    value: "preserve_liquidity",
                    description:
                        "Maintain liquidity discipline and wait for confirmed algorithmic signals before entering new positions.",
                },
            ],
        },
    ];

    const res = await callLunaDecisions(inputPayload, questions, apiKey);
    const reviewAns = getAnswerByName(res, "grounding_verdict") || getAnswerByName(res, "review");
    const stanceAns = getAnswerByName(res, "technical_stance");
    const planAns = getAnswerByName(res, "action_plan");

    const reviewChoice: "accept" | "review" =
        reviewAns?.choice === "ungrounded" || reviewAns?.choice === "review" ? "review" : "accept";
    const technicalStance = stanceAns?.choice || "neutral_consolidation";
    const actionPlan = planAns?.choice || "monitor_support_level";
    const rawConf = stanceAns?.confidence ?? reviewAns?.confidence ?? 0.92;
    const confidencePct = Math.round(Math.max(0.5, Math.min(1, Number(rawConf))) * 100);

    const stanceMapAr: Record<string, string> = {
        bullish_positive: "🟢 **إيجابي / زخم فني داعم** أعلى مناطق الارتكاز",
        neutral_consolidation: "🟡 **حيادي / حركة عرضية للمراقبة** بين الدعم والمقاومة",
        bearish_caution: "🔴 **سلبي / ضغوط بيعية** تستوجب الحذر ومراقبة ثبات الدعم",
        oversold_watch: "🟣 **تشبع بيعي قرب الدعم** — للمراقبة لحين تأكيد إشارة ارتداد",
    };

    const planMapAr: Record<string, string> = {
        follow_active_signal:
            "الالتزام الكامل بمستويات التوصية المفتوحة المعتمدة من المنصة وتفعيل وقف الخسارة الصارم لحماية رأس المال.",
        monitor_support_level:
            "المراقبة الفنية عند مستوى الدعم الأول وعدم التسرع في بناء مراكز شرائية قبل ظهور إشارة تأكيد رسمية.",
        watch_resistance_breakout:
            "متابعة قدرة السعر على اختراق المقاومة الأولى المصحوب بارتفاع في أحجام التداول النسبية.",
        preserve_liquidity:
            "الحفاظ على السيولة النقدية والانضباط الاستثماري لحين توافر إشارات فنية مكتملة الشروط.",
    };

    const reviewBadgeAr =
        reviewChoice === "accept"
            ? "✅ **معتمد ومطابق للأدلة الرقابية (Accepted)**"
            : "⚠️ **تحت المراجعة الرقابية (Needs Review)**";

    const decisionCardAr = [
        `### 🧠 قرار وتقييم محرك القرارات (GPT-6 Luna Decisions)`,
        `- **التقييم الفني المرجح:** ${stanceMapAr[technicalStance] || stanceMapAr.neutral_consolidation} *(درجة الثقة: ${confidencePct}%)*`,
        `- **خطة التحرك وإدارة المخاطر:** ${planMapAr[actionPlan] || planMapAr.monitor_support_level}`,
        `- **فحص مطابقة البيانات (Decision Gate):** ${reviewBadgeAr}`,
    ].join("\n");

    return {
        reviewChoice,
        technicalStance,
        actionPlan,
        confidencePct,
        decisionCardAr,
        usage: res.usage,
    };
}

