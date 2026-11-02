import {
    buildAnalysisCacheKey,
    getVipAnalysisCache,
    setVipAnalysisCache,
    ANALYSIS_CACHE_TTL_MS,
} from "./analysis-cache";

describe("VIP Analysis Cache", () => {
    test("buildAnalysisCacheKey returns correct key for single stock", () => {
        expect(buildAnalysisCacheKey("سهم فوري", ["FWRY"], false)).toBe("vip_stock_FWRY");
        expect(buildAnalysisCacheKey("حلل طلعت مصطفى", ["TMGH"], false)).toBe("vip_stock_TMGH");
        expect(buildAnalysisCacheKey("FWRY", ["FWRY"], false)).toBe("vip_stock_FWRY");
    });

    test("buildAnalysisCacheKey returns correct key for stock comparison", () => {
        expect(buildAnalysisCacheKey("قارن بين فوري وموبكو", ["FWRY", "MFPC"], false)).toBe(
            "vip_compare_FWRY_MFPC"
        );
        expect(buildAnalysisCacheKey("ايهما افضل MFPC أم FWRY", ["MFPC", "FWRY"], false)).toBe(
            "vip_compare_FWRY_MFPC"
        );
    });

    test("buildAnalysisCacheKey returns correct key for quick tools", () => {
        expect(buildAnalysisCacheKey("ملخص السوق وأقوى الأسهم", [], false)).toBe("vip_market_summary");
        expect(buildAnalysisCacheKey("أسهم التجميع والسيولة", [], false)).toBe("vip_accumulation");
        expect(buildAnalysisCacheKey("المسح الفني", [], false)).toBe("vip_tech_screener");
        expect(buildAnalysisCacheKey("أخبار السوق", [], false)).toBe("vip_market_news");
        expect(buildAnalysisCacheKey("التوصيات المفتوحة", [], false)).toBe("vip_open_recommendations");
    });

    test("buildAnalysisCacheKey returns null for personal or portfolio queries", () => {
        expect(buildAnalysisCacheKey("حلل محفظتي", ["FWRY"], true)).toBeNull();
        expect(buildAnalysisCacheKey("انا شاري فوري وخسران اعمل ايه", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("متوسطي في طلعت مصطفى 80", ["TMGH"], false)).toBeNull();
    });

    test("in-memory set and get works correctly", async () => {
        const mockSupabase = {
            from: jest.fn().mockReturnValue({
                select: jest.fn().mockReturnThis(),
                eq: jest.fn().mockReturnThis(),
                maybeSingle: jest.fn().mockResolvedValue({ data: null, error: null }),
                upsert: jest.fn().mockResolvedValue({ data: null, error: null }),
            }),
        };

        const testKey = "vip_stock_TEST_SYM";
        const payload = {
            reply: "## 📊 تقرير التحليل الفني المفصل لسهم الاختبار...\nهذا تحليل متكامل يحتوي على مستويات الدعم والمقاومة ومؤشرات السيولة.",
            tables: [],
            tools: { results: [{ tool: "wyckoff" }], formattedText: "" },
            summary_state: { test: true },
        };

        await setVipAnalysisCache(testKey, payload, mockSupabase);

        const cached = await getVipAnalysisCache(testKey, mockSupabase);
        expect(cached).not.toBeNull();
        expect(cached?.reply).toBe(payload.reply);
        expect(cached?.tools.results[0].tool).toBe("wyckoff");
        expect(cached?.age_ms).toBeLessThan(1000);
    });
});
