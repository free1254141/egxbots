import { NextRequest } from "next/server";
import { POST } from "../route";

jest.mock("@/lib/ai/pipeline", () => ({
    extractExplicitSymbols: jest.fn((msg: string) => {
        const syms: string[] = [];
        if (msg.includes("FWRY") || msg.includes("فوري")) syms.push("FWRY");
        if (msg.includes("TMGH") || msg.includes("طلعت مصطفى")) syms.push("TMGH");
        return syms;
    }),
    runPipeline: jest.fn(async (msg: string) => ({
        response: `## 📊 تقرير تفصيلي ممتاز لسهم (${msg})\nتم احتساب كافة المؤشرات الفنية بدقة 100%.`,
        tables: [{ title: "مستويات الدعم والمقاومة", rows: [] }],
        tools: { results: [{ tool: "wyckoff" }, { tool: "technical_indicators" }] },
        session_update: { current_symbol: "FWRY", last_symbols: ["FWRY"] },
    })),
}));

jest.mock("@/lib/supabase/route-data", () => {
    const mockStateRow = {
        telegram_user_id: 12345678,
        telegram_username: "test_investor",
        daily_count: 1,
        quota_date: "2026-11-02",
        session_state: {},
        session_summary: {},
        chat_history: [],
    };

    const mockDb: Record<string, any> = {};

    const createQueryChain = (table: string, filterVal?: any) => {
        const chain: any = {
            select: jest.fn(() => chain),
            eq: jest.fn((_col: string, val: any) => createQueryChain(table, val)),
            in: jest.fn(() => chain),
            order: jest.fn(() => chain),
            limit: jest.fn(() => chain),
            gte: jest.fn(() => chain),
            maybeSingle: jest.fn(async () => {
                if (table === "telegram_vip_chat_state") {
                    return { data: mockStateRow, error: null };
                }
                if (table === "market_cache") {
                    return { data: mockDb[filterVal] || null, error: null };
                }
                return { data: null, error: null };
            }),
            data: [],
        };
        return chain;
    };

    const mockClient = {
        from: jest.fn((table: string) => ({
            ...createQueryChain(table),
            upsert: jest.fn(async (payload: any) => {
                if (table === "market_cache") {
                    mockDb[payload.cache_key] = payload;
                }
                return { data: payload, error: null };
            }),
            insert: jest.fn().mockResolvedValue({ data: [], error: null }),
        })),
        rpc: jest.fn().mockResolvedValue({ data: [{ allowed: true }], error: null }),
    };

    return {
        getSupabaseClient: jest.fn(() => mockClient),
        getSupabaseServiceClient: jest.fn(() => mockClient),
    };
});

describe("VIP Chat Route Demand-Driven Cache & Smart Tool Bypass", () => {
    const originalEnv = process.env;

    beforeEach(() => {
        jest.clearAllMocks();
        process.env = { ...originalEnv, ADMIN_SECRET_KEY: "test_secret_123" };
    });

    afterAll(() => {
        process.env = originalEnv;
    });

    function makeRequest(body: any): NextRequest {
        return new NextRequest("http://localhost:3000/api/telegram/vip-chat", {
            method: "POST",
            headers: {
                "content-type": "application/json",
                "x-admin-key": "test_secret_123",
            },
            body: JSON.stringify(body),
        });
    }

    test("first query is a cache miss, runs pipeline, and warms cache for subsequent asks", async () => {
        const { runPipeline } = require("@/lib/ai/pipeline");

        const req1 = makeRequest({
            action: "chat",
            telegram_user_id: 12345678,
            telegram_username: "test_investor",
            message: "سهم فوري FWRY",
        });

        const res1 = await POST(req1);
        const data1 = await res1.json();

        expect(res1.status).toBe(200);
        expect(data1.ok).toBe(true);
        expect(data1.cached).toBe(false);
        expect(runPipeline).toHaveBeenCalledTimes(1);
        expect(data1.reply).toContain("تقرير تفصيلي ممتاز لسهم");

        // Second request for the same stock by a different user hits the warmed cache
        const req2 = makeRequest({
            action: "chat",
            telegram_user_id: 99999999,
            telegram_username: "another_user",
            message: "حلل فوري",
        });

        const res2 = await POST(req2);
        const data2 = await res2.json();

        expect(res2.status).toBe(200);
        expect(data2.ok).toBe(true);
        expect(data2.cached).toBe(true); // HIT!
        expect(runPipeline).toHaveBeenCalledTimes(1); // Pipeline NOT called again!
        expect(data2.reply).toBe(data1.reply);
    });

    test("market summary button warms cache on first click and hits on second click", async () => {
        const { runPipeline } = require("@/lib/ai/pipeline");
        const callCountBefore = runPipeline.mock.calls.length;

        const req1 = makeRequest({
            action: "chat",
            telegram_user_id: 11111111,
            telegram_username: "user_a",
            message: "ملخص السوق وأقوى الأسهم",
        });
        const res1 = await POST(req1);
        const data1 = await res1.json();
        expect(data1.cached).toBe(false);
        expect(runPipeline).toHaveBeenCalledTimes(callCountBefore + 1);

        const req2 = makeRequest({
            action: "chat",
            telegram_user_id: 22222222,
            telegram_username: "user_b",
            message: "ملخص السوق",
        });
        const res2 = await POST(req2);
        const data2 = await res2.json();
        expect(data2.cached).toBe(true);
        expect(runPipeline).toHaveBeenCalledTimes(callCountBefore + 1);
        expect(data2.reply).toBe(data1.reply);
    });

    test("open-ended dialogues and custom questions bypass cache and go directly to the 9 tools", async () => {
        const { runPipeline } = require("@/lib/ai/pipeline");
        const callCountBefore = runPipeline.mock.calls.length;

        // Even though FWRY is already cached as vip_stock_FWRY, a custom question about FWRY must bypass cache!
        const reqCustom = makeRequest({
            action: "chat",
            telegram_user_id: 55555555,
            telegram_username: "custom_trader",
            message: "ليه سهم فوري بينزل وهل اشتري على 16.5؟",
        });
        const resCustom = await POST(reqCustom);
        const dataCustom = await resCustom.json();
        expect(dataCustom.ok).toBe(true);
        expect(dataCustom.cached).toBe(false); // Directly executed tools!
        expect(runPipeline).toHaveBeenCalledTimes(callCountBefore + 1);
    });

    test("portfolio queries never use cache", async () => {
        const { runPipeline } = require("@/lib/ai/pipeline");
        const callCountBefore = runPipeline.mock.calls.length;

        const req1 = makeRequest({
            action: "chat",
            telegram_user_id: 33333333,
            telegram_username: "user_portfolio_1",
            message: "عندي فوري ومتعلق فيه اعمل ايه",
        });
        const res1 = await POST(req1);
        const data1 = await res1.json();
        expect(data1.cached).toBe(false);
        expect(runPipeline).toHaveBeenCalledTimes(callCountBefore + 1);

        const req2 = makeRequest({
            action: "chat",
            telegram_user_id: 44444444,
            telegram_username: "user_portfolio_2",
            message: "عندي فوري ومتعلق فيه اعمل ايه",
        });
        const res2 = await POST(req2);
        const data2 = await res2.json();
        expect(data2.cached).toBe(false);
        expect(runPipeline).toHaveBeenCalledTimes(callCountBefore + 2);
    });
});
