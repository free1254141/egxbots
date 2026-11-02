import {
    buildAnalysisCacheKey,
    getVipAnalysisCache,
    setVipAnalysisCache,
    personalizeCachedAnalysis,
    sanitizeAnalysisForCache,
    resolveCacheValidity,
} from "./analysis-cache";

// Cairo is UTC+2 in winter (Nov 2026) -> 2026-11-01 is a Sunday.
const cairo = (iso: string) => new Date(`${iso}+02:00`).getTime();

describe("resolveCacheValidity (market-session aware)", () => {
    test("live session: valid for 15 minutes only", () => {
        const computed = cairo("2026-11-01T11:00:00");
        expect(resolveCacheValidity(computed, cairo("2026-11-01T11:10:00"))).toBe(true);
        expect(resolveCacheValidity(computed, cairo("2026-11-01T11:16:00"))).toBe(false);
    });

    test("after the 17:00 close job finishes (17:15 Cairo), entry lives until the next session open", () => {
        const computed = cairo("2026-11-01T17:20:00"); // Sunday after the 17:00 job finished
        expect(resolveCacheValidity(computed, cairo("2026-11-01T22:00:00"))).toBe(true);
        expect(resolveCacheValidity(computed, cairo("2026-11-02T09:30:00"))).toBe(true);
        expect(resolveCacheValidity(computed, cairo("2026-11-02T10:30:00"))).toBe(false); // next session open
    });

    test("entries computed mid-session or before 17:15 expire after 15 minutes", () => {
        const midSession = cairo("2026-11-01T14:00:00");
        expect(resolveCacheValidity(midSession, cairo("2026-11-01T20:00:00"))).toBe(false);

        const beforeCloseJobReady = cairo("2026-11-01T16:30:00");
        expect(resolveCacheValidity(beforeCloseJobReady, cairo("2026-11-01T16:40:00"))).toBe(true);
        expect(resolveCacheValidity(beforeCloseJobReady, cairo("2026-11-01T17:30:00"))).toBe(false);
    });

    test("weekend: Thursday evening data stays valid through Friday/Saturday until Sunday open", () => {
        const computed = cairo("2026-11-05T18:00:00"); // Thursday after close job
        expect(resolveCacheValidity(computed, cairo("2026-11-06T12:00:00"))).toBe(true); // Friday
        expect(resolveCacheValidity(computed, cairo("2026-11-07T23:00:00"))).toBe(true); // Saturday
        expect(resolveCacheValidity(computed, cairo("2026-11-08T10:30:00"))).toBe(false); // Sunday session
    });
});

describe("buildAnalysisCacheKey (smart intent filtering & demand-driven keys)", () => {
    test("single stock comprehensive analysis phrasings map to the same canonical key", () => {
        expect(buildAnalysisCacheKey("سهم فوري", ["FWRY"], false)).toBe("vip_stock_FWRY");
        expect(buildAnalysisCacheKey("حلل عتاقه", ["ATQA"], false)).toBe("vip_stock_ATQA");
        expect(buildAnalysisCacheKey("تحليل فني لسهم فوري", ["FWRY"], false)).toBe("vip_stock_FWRY");
        expect(buildAnalysisCacheKey("ايه رايك في سهم فوري", ["FWRY"], false)).toBe("vip_stock_FWRY");
        expect(buildAnalysisCacheKey("FWRY", ["FWRY"], false)).toBe("vip_stock_FWRY");
    });

    test("different canonical sub-intents about the same stock get distinct keys", () => {
        const analysis = buildAnalysisCacheKey("حلل فوري", ["FWRY"], false);
        const levels = buildAnalysisCacheKey("ايه دعم ومقاومة فوري", ["FWRY"], false);
        const news = buildAnalysisCacheKey("اخبار فوري اليوم", ["FWRY"], false);
        const divs = buildAnalysisCacheKey("توزيعات فوري", ["FWRY"], false);
        const sharia = buildAnalysisCacheKey("هل سهم فوري شرعي", ["FWRY"], false);
        const liq = buildAnalysisCacheKey("تحليل السيولة لـ FWRY", ["FWRY"], false);
        const fin = buildAnalysisCacheKey("التحليل المالي لسهم فوري", ["FWRY"], false);

        expect(analysis).toBe("vip_stock_FWRY");
        expect(levels).toBe("vip_stock_FWRY_levels");
        expect(news).toBe("vip_stock_FWRY_news");
        expect(divs).toBe("vip_stock_FWRY_divs");
        expect(sharia).toBe("vip_stock_FWRY_sharia");
        expect(liq).toBe("vip_stock_FWRY_liquidity");
        expect(fin).toBe("vip_stock_FWRY_financials");
        expect(new Set([analysis, levels, news, divs, sharia, liq, fin]).size).toBe(7);
    });

    test("comparison is order independent", () => {
        expect(buildAnalysisCacheKey("قارن بين فوري وموبكو", ["FWRY", "MFPC"], false)).toBe("vip_compare_FWRY_MFPC");
        expect(buildAnalysisCacheKey("ايهما افضل MFPC أم FWRY", ["MFPC", "FWRY"], false)).toBe("vip_compare_FWRY_MFPC");
    });

    test("canonical quick tools and repeatable market-wide queries are cached", () => {
        expect(buildAnalysisCacheKey("ملخص السوق وأقوى الأسهم", [], false)).toBe("vip_market_summary");
        expect(buildAnalysisCacheKey("أقوى الأسهم النهارده", [], false)).toBe("vip_top_stocks");
        expect(buildAnalysisCacheKey("أسهم التجميع والسيولة", [], false)).toBe("vip_accumulation");
        expect(buildAnalysisCacheKey("المسح الفني", [], false)).toBe("vip_tech_screener");
        expect(buildAnalysisCacheKey("أخبار السوق", [], false)).toBe("vip_market_news");
        expect(buildAnalysisCacheKey("هات كل التوصيات المفتوحه", [], false)).toBe("vip_open_recommendations");
        expect(buildAnalysisCacheKey("عايز توصيات الاسبوع الحالى", [], false)).toBe("vip_recs_this_week");
        expect(buildAnalysisCacheKey("عايز توصيات الاسبوع اللى فات", [], false)).toBe("vip_recs_last_week");
        expect(buildAnalysisCacheKey("اي القطاعات الاقوى النهارده", [], false)).toBe("vip_top_sectors");
        expect(buildAnalysisCacheKey("البنوك حالتها إيه؟", [], false)).toBe("vip_sector_البنوك");
    });

    test("open-ended dialogues (حوارات), custom numbers, custom tools, and personal questions return null (direct tool access)", () => {
        // Personal / Portfolio
        expect(buildAnalysisCacheKey("حلل محفظتي", ["FWRY"], true)).toBeNull();
        expect(buildAnalysisCacheKey("انا شاري فوري وخسران اعمل ايه", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("عندي 100 سهم فوري اعمل ايه", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("معايا 50 الف جنيه اشتري ايه", [], false)).toBeNull();
        expect(buildAnalysisCacheKey("ابيع فوري ولا احتفظ؟", ["FWRY"], false)).toBeNull();

        // Conversational follow-ups
        expect(buildAnalysisCacheKey("وايه رايك فيه كمان", [], false)).toBeNull();
        expect(buildAnalysisCacheKey("طيب والتاني", ["FWRY"], false)).toBeNull();

        // Open-ended dialogues / Why / How / What-if / Custom Prices & Indicators
        expect(buildAnalysisCacheKey("ليه سهم عتاقة بينزل كل يوم؟", ["ATQA"], false)).toBeNull();
        expect(buildAnalysisCacheKey("ازاي احسب وقف الخسارة في فوري؟", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("لو فوري كسر 16 جنيه هيروح فين؟", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("هل اشتري فوري على سعر 16.5؟", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("هل فيه دايفرجنس على مؤشر RSI في فوري؟", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("عايز أسهم RSI تحت 30 وفيها تجميع", [], false)).toBeNull();
        expect(buildAnalysisCacheKey("اختبر استراتيجية المتوسطات على سهم فوري", ["FWRY"], false)).toBeNull();
        expect(buildAnalysisCacheKey("إيه تأثير رفع الفائدة على قطاع العقارات؟", [], false)).toBeNull();
        expect(buildAnalysisCacheKey("يعني إيه مرحلة التجميع في وايكوف؟", [], false)).toBeNull();
    });
});

describe("portfolio privacy", () => {
    test("sanitize strips personal clauses and neutralises the portfolio line", () => {
        const raw = [
            "السعر الأخير: `9.04`",
            "📌 **حالة السهم في محفظتك:** مسجل لديك 100 سهم بمتوسط شراء 9.05 ج.م (خسارة غير محققة: -0.11%).",
            "الرأي التوليفي: السهم هابط. مركزك الحالي عند 9.05 قريب جداً من السعر الحالي، وأي كسر لدعم 8.25 يلغي السيناريو.",
            "ملاحظة: يفضل مراجعة محفظتك قبل أي قرار.",
        ].join("\n");
        const cleaned = sanitizeAnalysisForCache(raw);
        expect(cleaned).not.toContain("100 سهم");
        expect(cleaned).not.toContain("9.05");
        expect(cleaned).not.toContain("مركزك");
        expect(cleaned).not.toContain("مراجعة محفظتك");
        expect(cleaned).toContain("وأي كسر لدعم 8.25");
        expect(cleaned).toContain("السهم غير مسجل ضمن مراكز محفظتك");
    });

    test("multi-stock answers drop the portfolio line completely", () => {
        const raw = "مقارنة...\n📌 **حالة السهم في محفظتك:** مسجل لديك 10 سهم بمتوسط شراء 5.00 ج.م.\nخلاصة المقارنة كاملة هنا بما يكفي من النص.";
        const cleaned = sanitizeAnalysisForCache(raw, false);
        expect(cleaned).not.toContain("محفظتك");
        expect(cleaned).toContain("خلاصة المقارنة");
    });

    const supabaseWith = (row: any) => ({
        from: jest.fn().mockReturnValue({
            select: jest.fn().mockReturnThis(),
            eq: jest.fn().mockReturnThis(),
            maybeSingle: jest.fn().mockResolvedValue({ data: row, error: null }),
        }),
    });
    const base = "السعر الأخير: `9.04`\n📌 **حالة السهم في محفظتك:** السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة.\nتحليل فني كامل...";

    test("owner gets their real position", async () => {
        const out = await personalizeCachedAnalysis(
            base, "user_1", "ATQA", supabaseWith({ quantity: 100, entry_price: 9.05, status_price: 9.04 })
        );
        expect(out).toContain("مسجل لديك 100 سهم بمتوسط شراء 9.05 ج.م");
        expect(out).toContain("خسارة غير محققة");
    });

    test("non-owner and anonymous users never see a position", async () => {
        const none = await personalizeCachedAnalysis(base, "user_2", "ATQA", supabaseWith(null));
        expect(none).toContain("السهم غير مسجل");
        const anon = await personalizeCachedAnalysis(base, null, "ATQA", supabaseWith({ quantity: 100, entry_price: 9.05 }));
        expect(anon).toContain("السهم غير مسجل");
        expect(anon).not.toContain("100 سهم");
    });
});

describe("storage", () => {
    test("set -> get round trip stores only sanitized, light data", async () => {
        const upsert = jest.fn().mockResolvedValue({ error: null });
        const supabase = {
            from: jest.fn().mockReturnValue({
                select: jest.fn().mockReturnThis(),
                eq: jest.fn().mockReturnThis(),
                maybeSingle: jest.fn().mockResolvedValue({ data: null, error: null }),
                upsert,
            }),
        };
        const reply =
            "## تحليل سهم الاختبار الكامل\n📌 **حالة السهم في محفظتك:** مسجل لديك 7 سهم بمتوسط شراء 3.00 ج.م.\n" +
            "المستويات والدعوم والمقاومات والمؤشرات الفنية المفصلة هنا.";
        await setVipAnalysisCache(
            "vip_stock_TESTX",
            {
                reply,
                tables: [{ title: "جدول المحفظة" }, { title: "مستويات" }],
                tools: { results: [{ tool: "get_stock", data: { huge: true } }, { tool: "manage_portfolio", data: { positions: [1] } }] },
                extra: { suggested_buttons: ["a"] },
            },
            supabase
        );

        const saved = upsert.mock.calls[0][0].payload;
        expect(saved.reply).not.toContain("7 سهم");
        expect(saved.tables).toHaveLength(1);
        expect(saved.tools.results).toEqual([{ tool: "get_stock" }]);

        const cached = await getVipAnalysisCache("vip_stock_TESTX", supabase);
        expect(cached?.reply).toContain("تحليل سهم الاختبار");
        expect(cached?.extra?.suggested_buttons).toEqual(["a"]);
    });
});
