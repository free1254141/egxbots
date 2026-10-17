import { checkAgenticDraft, safeAgenticFallback, toAgenticEvidence } from "../agentic-publication";
import { fallbackEvidence } from "../agentic-recovery";
import { renderStockRecovery } from "../stock-recovery";
import { runAgenticRuntime } from "../agentic-runtime";
import { executeRequestTool } from "../request-data-tools";

jest.mock("../server-secrets", () => ({ getDeepSeekApiKey: () => "offline-fake-key" }));
jest.mock("../request-data-tools", () => ({ ...jest.requireActual("../request-data-tools"), executeRequestTool: jest.fn() }));

const stocks = [
    { symbol: "ATQA", name: "عتاقة", date: "2026-10-14", close: 11.27, rsi_14: 29.3367, macd: -0.146616, macd_signal: -0.009249, macd_hist: -0.137367, ema_50: 11.644948, ema_200: 10.552196 },
    { symbol: "ORWE", name: "النساجون", date: "2026-10-14", close: 27.11, rsi_14: 45, macd: 0.039177, macd_signal: 0.147601, macd_hist: -0.108424, ema_50: 26.468406, ema_200: 24.463225 },
    { symbol: "ALCN", name: "الإسكندرية للحاويات", date: "2026-10-14", close: 32.93, rsi_14: 44.3756, macd: 0.427162, macd_signal: 0.588527, macd_hist: -0.161365, ema_50: 32.309999, ema_200: 29.236792 },
];
const levels = stocks.map((s, i) => ({ symbol: s.symbol, date: s.date, close: s.close,
    support: [10.61, 26.01, 30.55][i], resistance: [13.7, 28.61, 36.18][i] }));
const evidence = [toAgenticEvidence("get_stock", { symbols: stocks.map(s => s.symbol) }, { status: "success", stocks }),
    toAgenticEvidence("get_stock_levels", { symbols: stocks.map(s => s.symbol) }, { status: "success", levels })];
const table = "| السهم | الإغلاق | RSI | MACD / الإشارة / الهيستوجرام |\n|---|---|---|---|\n| ATQA | 11.27 | 29.34 | -0.147 / -0.009 / -0.137 |\n| ORWE | 27.11 | 45.00 | 0.039 / 0.148 / -0.108 |\n| ALCN | 32.93 | 44.38 | 0.427 / 0.589 / -0.161 |";

test("production three-stock column accepts correctly rounded ordered MACD metrics", () => {
    expect(checkAgenticDraft(table, evidence)).toEqual([]);
});
test.each([
    ["0.039 / 0.148 / -0.108", "0.148 / 0.039 / -0.108"],
    ["-0.147 / -0.009 / -0.137", "-0.147 / 0.009 / -0.137"],
    ["0.427 / 0.589 / -0.161", "0.039 / 0.148 / -0.108"],
    ["0.039 / 0.148 / -0.108", "0.039 / 0.148"],
])("wrong metric order, sign, stock or missing metric remains rejected", (old, invalid) => {
    expect(checkAgenticDraft(table.replace(old, invalid), evidence).length).toBeGreaterThan(0);
});
test("transposed comparison and reversed declared order bind each component separately", () => {
    const transposed = "| المؤشر | ATQA | ORWE | ALCN |\n|---|---|---|---|\n| الإشارة / MACD / الهيستوجرام | -0.009 / -0.147 / -0.137 | 0.148 / 0.039 / -0.108 | 0.589 / 0.427 / -0.161 |";
    expect(checkAgenticDraft(transposed, evidence)).toEqual([]);
    expect(checkAgenticDraft(transposed.replace("0.148 / 0.039", "0.039 / 0.148"), evidence).length).toBeGreaterThan(0);
});
test.each(["verification_incomplete", "request_failed_or_aborted", "MODEL_HTTP_503"])("stock recovery explains facts even when %s", reason => {
    const reply = safeAgenticFallback(fallbackEvidence(evidence, stocks.map(s => s.symbol)), reason);
    for (const s of stocks) expect(reply).toContain(s.symbol);
    expect(reply).toContain("الصورة مختلطة");
    expect(reply).toContain("السعر فوق متوسطاته");
    expect(reply).toContain("MACD تحت خط إشارته");
    expect(reply).toContain("الدعم عند 10.61");
    expect(reply).toContain("المقاومة عند 13.7");
    expect(reply).toContain("الخلاصة:");
    expect(reply).not.toContain("| السهم |");
    expect(reply).not.toContain("RSI =");
    expect(reply).not.toContain("MACD =");
    expect(reply).not.toContain(reason);
});
test("stale indicators or older levels cannot attach to a newer quote", () => {
    const reply = renderStockRecovery([{ ...stocks[0], support: 10.61 },
        { symbol: "ATQA", close: 20, date: "2026-10-15", indicators_stale: true, rsi_14: 29 }]);
    expect(reply).toContain("20 جنيه");
    expect(reply).toContain("المؤشرات لا تطابق");
    expect(reply).not.toContain("10.61");
    expect(reply).not.toContain("القوة النسبية 29");
});
test("comparison evidence has the same explanatory recovery, missing evidence invents no indicators", () => {
    const reply = safeAgenticFallback([toAgenticEvidence("get_comparison", {}, { comparison: stocks, status: "success" })], "");
    expect(reply).toContain("الزخم الحالي ضعيف");
    expect(reply).not.toContain("| البند |");
    const missing = safeAgenticFallback([], "MODEL_HTTP_503");
    expect(missing).not.toContain("MACD");
    expect(missing).not.toContain("ATQA");
});

const toolCall = { id: "stock-call", type: "function", function: { name: "get_stock", arguments: JSON.stringify({ symbols: stocks.map(s => s.symbol) }) } };
const providerResponse = (content: any) => ({ ok: true, json: async () => ({ choices: [{ message: content, finish_reason: "stop" }] }) });
async function runRuntime() {
    const events: any[] = [];
    for await (const event of runAgenticRuntime({ userMessage: "عتاقه والنساجون والإسكندرية", images: [],
        sessionState: { current_symbol: "EGCH", last_symbols: ["EGCH"], summary: null }, sessionSummary: null, history: [],
        supabase: {}, apiKeys: [], userId: "offline-user", sessionId: "offline-session", messageId: "offline-message",
        options: { timeoutMs: 20000 }, systemPrompt: "حلل البيانات المتاحة", toolsSchema: [{ function: { name: "get_stock" } }] })) events.push(event);
    return { events, done: events.find(e => e.type === "done")?.data };
}
test("actual runtime publishes the combined-column analysis instead of entering recovery", async () => {
    (executeRequestTool as jest.Mock).mockResolvedValue({ status: "success", stocks });
    const fetchMock = jest.spyOn(global, "fetch").mockResolvedValueOnce(providerResponse({ tool_calls: [toolCall] }) as any)
        .mockResolvedValueOnce(providerResponse({ content: table + "\nالزخم الحالي ضعيف؛ MACD تحت خط إشارته في الأسهم الثلاثة." }) as any)
        .mockResolvedValueOnce(providerResponse({ content: JSON.stringify({ passed: true, issues: [], notes: [] }) }) as any);
    try {
        const { done } = await runRuntime();
        expect(done.response_origin).toBe("llm");
        expect(done.publication_review.final_passed).toBe(true);
        expect(done.response).toContain("الزخم الحالي ضعيف");
        expect(fetchMock).toHaveBeenCalledTimes(3);
    } finally { fetchMock.mockRestore(); }
});
test.each(["provider_failure", "rejected_repair"])("actual runtime %s cannot publish the dry dump or old stock", async failure => {
    (executeRequestTool as jest.Mock).mockResolvedValue({ status: "success", stocks });
    const fetchMock = jest.spyOn(global, "fetch").mockResolvedValueOnce(providerResponse({ tool_calls: [toolCall] }) as any);
    if (failure === "provider_failure") fetchMock.mockRejectedValue(new Error("offline provider unavailable"));
    else {
        const invalid = table.replace("0.039 / 0.148 / -0.108", "0.148 / 0.039 / -0.108");
        fetchMock.mockResolvedValueOnce(providerResponse({ content: invalid }) as any)
            .mockResolvedValueOnce(providerResponse({ content: JSON.stringify({ passed: true, issues: [], notes: [] }) }) as any)
            .mockResolvedValueOnce(providerResponse({ content: invalid }) as any)
            .mockResolvedValueOnce(providerResponse({ content: JSON.stringify({ passed: true, issues: [], notes: [] }) }) as any);
    }
    try {
        const { done, events } = await runRuntime();
        if (failure === "rejected_repair") {
            // A rejected writer draft is replaced by a deterministic dashboard that passes the same grounding checker.
            expect(["safe_fallback", "deterministic_dashboard"]).toContain(done.response_origin);
            for (const s of stocks) expect(done.response).toContain(s.symbol);
            expect(done.response).not.toContain("0.148 / 0.039 / -0.108");
        } else {
            expect(done.response_origin).toBe("safe_fallback");
            expect(done.response).toContain("الزخم الحالي ضعيف");
        }
        expect(done.response).not.toContain("EGCH");
        for (const event of events.filter(e => e.type === "token")) {
            expect(event.data).not.toContain("RSI =");
            expect(event.data).not.toContain("| السهم |");
        }
    } finally { fetchMock.mockRestore(); }
});
