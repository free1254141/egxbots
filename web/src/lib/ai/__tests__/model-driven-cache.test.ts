import { resolveToolCallToCacheKey, setVipAnalysisCache, getVipAnalysisCache, clearVipAnalysisMemoryCache } from "../analysis-cache";
import { runAgenticPipelineStream } from "../agentic-pipeline";

jest.mock("../server-secrets", () => ({ getDeepSeekApiKey: () => "offline-fake-key" }));
jest.mock("../live-stock-updater", () => ({
    fetchLiveStockIndicators: jest.fn().mockResolvedValue({ success: false, error: "offline_test" }),
    isEgxSessionOpen: jest.fn().mockReturnValue(false),
}));

describe("resolveToolCallToCacheKey (Model-Driven Caching Router)", () => {
    test("maps get_recommendations to canonical open recs key", () => {
        expect(resolveToolCallToCacheKey("get_recommendations", {})).toBe("vip_open_recommendations");
        expect(resolveToolCallToCacheKey("get_recommendations", { timeframe: "this_week" })).toBe("vip_recs_this_week");
        expect(resolveToolCallToCacheKey("get_recommendations", { timeframe: "last_week" })).toBe("vip_recs_last_week");
    });

    test("maps get_accumulation_stocks to canonical accumulation key", () => {
        expect(resolveToolCallToCacheKey("get_accumulation_stocks", {})).toBe("vip_accumulation");
    });

    test("maps get_market to summary or top stocks or sectors", () => {
        expect(resolveToolCallToCacheKey("get_market", {})).toBe("vip_market_summary");
        expect(resolveToolCallToCacheKey("get_market", { metric: "top_gainers" })).toBe("vip_top_stocks");
        expect(resolveToolCallToCacheKey("get_market", { type: "sectors" })).toBe("vip_top_sectors");
    });

    test("maps get_technical_scan and screen_stocks to tech screener", () => {
        expect(resolveToolCallToCacheKey("get_technical_scan", {})).toBe("vip_tech_screener");
        expect(resolveToolCallToCacheKey("screen_stocks", {})).toBe("vip_tech_screener");
    });

    test("maps get_stock and get_stock_levels to stock key", () => {
        expect(resolveToolCallToCacheKey("get_stock", { symbol: "TMGH" })).toBe("vip_stock_TMGH");
        expect(resolveToolCallToCacheKey("get_stock", { symbol: "FWRY.CA" })).toBe("vip_stock_FWRY");
        expect(resolveToolCallToCacheKey("get_stock_levels", { symbol: "cire" })).toBe("vip_stock_CIRE");
    });

    test("maps get_comparison to sorted pair key", () => {
        expect(resolveToolCallToCacheKey("get_comparison", { symbols: ["HRHO", "COMI"] })).toBe("vip_compare_COMI_HRHO");
        expect(resolveToolCallToCacheKey("get_comparison", { symbol1: "fwrY", symbol2: "eLka" })).toBe("vip_compare_ELKA_FWRY");
    });

    test("maps get_fair_value to undervalue list or specific stock", () => {
        expect(resolveToolCallToCacheKey("get_fair_value", {})).toBe("vip_fair_value_undervalued");
        expect(resolveToolCallToCacheKey("get_fair_value", { symbol: "ABUK" })).toBe("vip_fair_value_ABUK");
    });

    test("maps get_price_traps to wyckoff traps key", () => {
        expect(resolveToolCallToCacheKey("get_price_traps", {})).toBe("vip_price_traps");
    });

    test("maps get_news to market or stock news", () => {
        expect(resolveToolCallToCacheKey("get_news", {})).toBe("vip_market_news");
        expect(resolveToolCallToCacheKey("get_news", { symbol: "SWDY" })).toBe("vip_news_SWDY");
    });

    test("returns null for private portfolio or custom operations", () => {
        expect(resolveToolCallToCacheKey("manage_portfolio", { operation: "view" })).toBeNull();
        expect(resolveToolCallToCacheKey("rebalance_portfolio", {})).toBeNull();
        expect(resolveToolCallToCacheKey("analyze_portfolio_risk", {})).toBeNull();
        expect(resolveToolCallToCacheKey("unknown_tool", {})).toBeNull();
    });
});

describe("Model-Driven Cache Runtime Integration", () => {
    beforeEach(() => {
        clearVipAnalysisMemoryCache();
        jest.clearAllMocks();
    });

    const mockDb = () => {
        const chain: any = {
            select: () => chain,
            insert: () => chain,
            update: () => chain,
            upsert: () => chain,
            eq: () => chain,
            limit: () => chain,
            maybeSingle: () => Promise.resolve({ data: null, error: null }),
            then: (resolve: any) => Promise.resolve(resolve({ data: null, error: null })),
        };
        return {
            from: () => chain,
        } as any;
    };

    function response(message: any) {
        return {
            ok: true,
            json: async () => ({
                choices: [{ message, finish_reason: "stop" }],
                usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
            }),
        };
    }

    test("clearing memory cache empties tier-1 cache", async () => {
        const dummyClient = mockDb();
        const testReport = "تقرير اختبار مفصل لسهم التجاري الدولي مع مستويات الدعم والمقاومة والسيولة المؤسسية.";
        await setVipAnalysisCache("vip_stock_TEST", { reply: testReport, tables: [], tools: {} }, dummyClient);
        const hitBefore = await getVipAnalysisCache("vip_stock_TEST", dummyClient);
        expect(hitBefore).not.toBeNull();

        clearVipAnalysisMemoryCache();
        const hitAfter = await getVipAnalysisCache("vip_stock_TEST", dummyClient);
        expect(hitAfter).toBeNull();
    });

    test("short-circuits in Round 0 to cache when skipCache is false and single tool matches", async () => {
        const dummyClient = mockDb();
        const cachedReport = "تقرير سهم فوري: السهم يتداول عند 8.50 جنيه وهو في مسار صاعد قوي مع سيولة مؤسسية.";
        await setVipAnalysisCache("vip_stock_FWRY", { reply: cachedReport, tables: [], tools: {} }, dummyClient);

        // Model emits tool call get_stock({ symbol: "FWRY" })
        const fetchMock = jest.fn().mockResolvedValueOnce(response({
            tool_calls: [{
                id: "call-1",
                type: "function",
                function: { name: "get_stock", arguments: JSON.stringify({ symbol: "FWRY" }) },
            }],
        }));
        global.fetch = fetchMock as any;

        const events: any[] = [];
        for await (const e of runAgenticPipelineStream(
            "تحليل سهم فوري",
            [],
            { current_symbol: null, last_symbols: [], summary: null },
            null,
            [],
            dummyClient,
            [],
            "test-user",
            "test-session",
            "test-msg",
            "deepseek-chat",
            { timeoutMs: 5000, skipCache: false }
        )) {
            events.push(e);
        }

        const done = events.find(e => e.type === "done")?.data;
        expect(done).toBeDefined();
        expect(done.response_origin).toBe("cache");
        expect(done.cached).toBe(true);
        expect(done.response).toContain("تقرير سهم فوري");
        // DeepSeek fetch called only once for round 0 intent, second synthesis call skipped!
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    test("bypasses cache when conversation has history (multi-turn follow-up)", async () => {
        const dummyClient = mockDb();
        const cachedReport = "تقرير سهم فوري القديم المستقل";
        await setVipAnalysisCache("vip_stock_FWRY", { reply: cachedReport, tables: [], tools: {} }, dummyClient);

        // Fetch mock for 1) tool call, 2) writer synthesis, 3) reviewer
        const fetchMock = jest.fn()
            .mockResolvedValueOnce(response({
                tool_calls: [{
                    id: "call-1",
                    type: "function",
                    function: { name: "get_stock", arguments: JSON.stringify({ symbol: "FWRY" }) },
                }],
            }))
            .mockResolvedValueOnce(response({ content: "إجابة متابعة خاصة بالسياق" }))
            .mockResolvedValueOnce(response({ content: JSON.stringify({ passed: true, reasons: [] }) }));
        global.fetch = fetchMock as any;

        const events: any[] = [];
        for await (const e of runAgenticPipelineStream(
            "طب اشتري بكام دلوقتي؟",
            [],
            { current_symbol: null, last_symbols: [], summary: null },
            null,
            [{ role: "user", content: "حلل فوري" }, { role: "assistant", content: "فوري عند 8.50" }],
            dummyClient,
            [],
            "test-user",
            "test-session",
            "test-msg",
            "deepseek-chat",
            { timeoutMs: 5000, skipCache: false }
        )) {
            events.push(e);
        }

        const done = events.find(e => e.type === "done")?.data;
        expect(done).toBeDefined();
        // Since multi-turn history exists, cache check is bypassed and tools proceed
        expect(done.response_origin).not.toBe("cache");
    });

    test("bypasses cache when parallel tool calls are emitted", async () => {
        const dummyClient = mockDb();
        await setVipAnalysisCache("vip_stock_FWRY", { reply: "تقرير فوري", tables: [], tools: {} }, dummyClient);

        // Fetch mock for 1) 2 parallel tool calls (get_stock + get_news)
        const fetchMock = jest.fn()
            .mockResolvedValueOnce(response({
                tool_calls: [
                    { id: "call-1", type: "function", function: { name: "get_stock", arguments: JSON.stringify({ symbol: "FWRY" }) } },
                    { id: "call-2", type: "function", function: { name: "get_news", arguments: JSON.stringify({ symbol: "FWRY" }) } },
                ],
            }))
            .mockResolvedValueOnce(response({ content: "تقرير مدمج فوري وأخبارها" }))
            .mockResolvedValueOnce(response({ content: JSON.stringify({ passed: true, reasons: [] }) }));
        global.fetch = fetchMock as any;

        const events: any[] = [];
        for await (const e of runAgenticPipelineStream(
            "فوري وأخبارها إيه؟",
            [],
            { current_symbol: null, last_symbols: [], summary: null },
            null,
            [],
            dummyClient,
            [],
            "test-user",
            "test-session",
            "test-msg",
            "deepseek-chat",
            { timeoutMs: 5000, skipCache: false }
        )) {
            events.push(e);
        }

        const done = events.find(e => e.type === "done")?.data;
        expect(done).toBeDefined();
        // Parallel calls must not be hijacked by single-tool cache
        expect(done.response_origin).not.toBe("cache");
    });
});

