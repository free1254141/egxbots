/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import StockCard from "../StockCard";
import { FormattedChatMessage } from "../FormattedChatMessage";
import {
    ComparisonMirrorCard,
    ConceptDiagramCard,
    detectConceptDiagrams,
    DisclosuresTimelineCard,
    FairValueGaugeCard,
    MarketBreadthAccumulationCard,
    MiniPriceChartSvg,
    MomentumLiquidityGauges,
    PortfolioVisualCard,
    PriceLadderSvg,
    PriceTrapsRadarCard,
    QuantIntelligenceCard,
    RecommendationsTrackerCard,
    ShariaPurificationCard,
    SmartDcaPlanCard,
} from "../StockVisuals";

jest.mock("next/navigation", () => ({
    useRouter: () => ({ push: jest.fn() }),
}));

describe("StockVisuals & Website Chat Visual Enrichment", () => {
    test("PriceLadderSvg calculates Risk:Reward, switches breakout scenario, and safely ignores insufficient levels", () => {
        const { container: emptyContainer } = render(<PriceLadderSvg price={100} />);
        expect(emptyContainer.firstChild).toBeNull();

        render(
            <PriceLadderSvg
                price={108.5}
                stopLoss={101}
                support1={106}
                resistance1={114.5}
                target1={114.5}
                target2={121}
                currency="ج.م"
            />
        );
        expect(screen.getByTestId("price-ladder-svg")).toBeTruthy();
        // Reward (114.5 - 108.5 = 6.0) / Risk (108.5 - 101 = 7.5) = 0.8
        expect(screen.getByText("R:R 1:0.8")).toBeTruthy();

        const breakoutBtn = screen.getByText(/اختراق 114.5 ج\.م/);
        fireEvent.click(breakoutBtn);
        // Breakout entry 114.5, stop 110.49 (~4.01), target2 121 (+6.5) -> 1:1.6
        expect(screen.getByText(/R:R 1:1\.\d/)).toBeTruthy();
        expect(screen.getByText("دخول الاختراق")).toBeTruthy();
    });

    test("MiniPriceChartSvg renders SVG curve, handles hover crosshair and overlay toggles", () => {
        const { container: tooFew } = render(
            <MiniPriceChartSvg
                symbol="COMI"
                chartData={{ series: [{ d: "2026-11-15", c: 100 }, { d: "2026-11-16", c: 102 }] }}
            />
        );
        expect(tooFew.firstChild).toBeNull();

        render(
            <MiniPriceChartSvg
                symbol="COMI"
                currency="ج.م"
                support1={101}
                resistance1={112}
                chartData={{
                    series: [
                        { d: "2026-11-10", c: 102, v: 900000 },
                        { d: "2026-11-11", c: 104, v: 1100000 },
                        { d: "2026-11-12", c: 105.5, v: 1300000 },
                        { d: "2026-11-16", c: 108.5, v: 1850000 },
                    ],
                    ema50: 103.2,
                }}
            />
        );

        expect(screen.getByTestId("mini-price-chart")).toBeTruthy();
        expect(screen.getByText(/2026-11-16 — 108.5 ج\.م/)).toBeTruthy();

        const svg = screen.getByLabelText("ميني شارت COMI");
        Object.defineProperty(svg, "getBoundingClientRect", {
            value: () => ({ left: 0, width: 580, top: 0, height: 152, right: 580, bottom: 152 }),
        });
        fireEvent.mouseMove(svg, { clientX: 20 });
        expect(screen.getByText(/2026-11-10 — 102.0 ج\.م/)).toBeTruthy();

        fireEvent.mouseLeave(svg);
        expect(screen.getByText(/2026-11-16 — 108.5 ج\.م/)).toBeTruthy();

        fireEvent.click(screen.getByText("EMA50"));
        expect(screen.queryByText(/EMA 103\.2/)).toBeNull();
    });

    test("MomentumLiquidityGauges renders RSI speedometer needle, RVol, KING AI, and EMA alignment", () => {
        render(
            <MomentumLiquidityGauges
                rsi={28.5}
                rVol={1.85}
                kingScore={0.78}
                wyckoffPhase="Phase D"
                ema50={50}
                ema200={45}
                price={55}
            />
        );
        expect(screen.getByTestId("momentum-liquidity-gauges")).toBeTruthy();
        expect(screen.getByText("RSI 28.5")).toBeTruthy();
        expect(screen.getByText("تشبع بيعي (منطقة ارتداد)")).toBeTruthy();
        expect(screen.getByText("RVol 1.85x")).toBeTruthy();
        expect(screen.getByText("78%")).toBeTruthy();
        expect(screen.getByText("أعلى EMA50 ✓")).toBeTruthy();
        expect(screen.getByText("أعلى EMA200 ✓")).toBeTruthy();
    });

    test("detectConceptDiagrams & ConceptDiagramCard match educational technical explanations", () => {
        expect(detectConceptDiagrams("نص قصير")).toEqual([]);
        const prose =
            "السهم يتحرك داخل نطاق تجميع وايكوف (Wyckoff) بعد ما عمل كسر وهمي للدعم ثم ارتد بقوة، " +
            "وهذا يشبه مصيدة الدببة (Bear Trap) وكذلك اختبار مصيدة الثيران لو فشل عند القمة.";
        const detected = detectConceptDiagrams(prose);
        expect(detected).toEqual(["wyckoff_spring", "bear_trap"]);

        render(<ConceptDiagramCard concept="wyckoff_spring" />);
        expect(screen.getByTestId("concept-diagram-wyckoff_spring")).toBeTruthy();
        fireEvent.click(screen.getByText("إخفاء"));
        expect(screen.getByText("إظهار الرسم")).toBeTruthy();
    });

    test("FormattedChatMessage auto-enriches StockCard with table charts & renders Saudi currency cleanly", () => {
        const markdownReply = [
            "### 📊 تحليل سهم أرامكو السعودية (2222) — TASI",
            "آخر إغلاق متاح: 28.50 ر.س (جلسة 16-11-2026، +1.42%)",
            "",
            "السهم يشهد مرحلة تجميع وايكوف مع كسر وهمي (Spring) أعلى منطقة الدعم ثم ارتداد ملحوظ بسيولة شرائية قوية.",
            "",
            "### المستويات الفنية",
            "| المستوى | السعر (ر.س) | الدلالة |",
            "|---|---|---|",
            "| الإغلاق الحالي | 28.50 | أحدث جلسة |",
            "| الدعم الأول | 27.90 | قاع قريب |",
            "| الدعم الثاني | 27.10 | دعم تالي |",
            "| المقاومة الأولى | 29.40 | قمة قريبة |",
            "",
            "| المؤشر | القيمة | القراءة |",
            "|---|---|---|",
            "| RSI (14) | 56.40 | زخم إيجابي |",
            "| الحجم النسبي | 1.65 | نشاط مرتفع |",
        ].join("\n");

        render(
            <FormattedChatMessage
                role="assistant"
                content={markdownReply}
                isStreaming={false}
                tables={[
                    {
                        id: "t1",
                        title: "التحليل الفني لسهم أرامكو السعودية (2222)",
                        headers: ["الكود"],
                        rows: [["2222"]],
                        charts: {
                            "2222": {
                                series: [
                                    { d: "2026-11-12", c: 27.8, v: 4100000 },
                                    { d: "2026-11-15", c: 28.1, v: 5200000 },
                                    { d: "2026-11-16", c: 28.5, v: 6400000 },
                                ],
                                ema50: 28.0,
                                support1: 27.9,
                                resistance1: 29.4,
                            },
                        },
                    },
                ]}
            />
        );

        expect(screen.getByTestId("price-ladder-svg")).toBeTruthy();
        expect(screen.getByTestId("mini-price-chart")).toBeTruthy();
        expect(screen.getByTestId("concept-diagram-wyckoff_spring")).toBeTruthy();
        expect(screen.getAllByText(/ر\.س/).length).toBeGreaterThan(0);
        expect(screen.queryByText(/28\.5\d?\s*ج\.م/)).toBeNull();
        expect(screen.queryByText(/27\.9\d?\s*ج\.م/)).toBeNull();
        expect(screen.queryByText(/29\.4\d?\s*ج\.م/)).toBeNull();
        // Toggle to Momentum & Liquidity gauges inside StockCard
        fireEvent.click(screen.getByText("بوصلة الزخم والسيولة"));
        expect(screen.getByTestId("momentum-liquidity-gauges")).toBeTruthy();
    });

    test("StockCard opens mini-chart automatically if chartData arrives after streaming finishes", () => {
        const baseStock = { symbol: "COMI", nameAr: "التجاري الدولي", price: 108.5 };
        const { rerender } = render(<StockCard stock={baseStock} />);
        expect(screen.queryByTestId("mini-price-chart")).toBeNull();

        rerender(
            <StockCard
                stock={{
                    ...baseStock,
                    chartData: {
                        series: [
                            { d: "2026-11-12", c: 105, v: 100 },
                            { d: "2026-11-15", c: 107, v: 120 },
                            { d: "2026-11-16", c: 108.5, v: 150 },
                        ],
                    },
                }}
            />
        );
        expect(screen.getByTestId("mini-price-chart")).toBeTruthy();
    });

    test("ComparisonMirrorCard, PortfolioVisualCard, MarketBreadthAccumulationCard & FairValueGaugeCard render all common visuals cleanly", () => {
        render(
            <>
                <ComparisonMirrorCard
                    stocks={[
                        { symbol: "COMI", name_ar: "التجاري الدولي", close: 108.5, rsi_14: 58, r_vol: 1.4, king_ai_score: 0.74, resistance_1: 115.0, currency: "ج.م" },
                        { symbol: "TMGH", name_ar: "طلعت مصطفى", close: 58.2, rsi_14: 64, r_vol: 2.3, king_ai_score: 0.82, resistance_1: 64.0, currency: "ج.م" },
                        { symbol: "FWRY", name_ar: "فوري", close: 8.5, rsi_14: 52, r_vol: 1.9, king_ai_score: 0.79, resistance_1: 9.5, currency: "ج.م" },
                    ]}
                />
                <PortfolioVisualCard
                    portfolio={{
                        cash_balance: 5000,
                        positions: [
                            { symbol: "EPPK", market: "EGX", currency: "ج.م", market_value: 20000, profit_pct: -3.8, profit_value: -790 },
                            { symbol: "VALU", market: "EGX", currency: "ج.م", market_value: 10000, profit_pct: 5.2, profit_value: 495 },
                            { symbol: "2222", market: "TASI", currency: "ر.س", market_value: 8000, profit_pct: 4.1, profit_value: 315 },
                        ],
                    }}
                />
                <MarketBreadthAccumulationCard
                    breadth={{ market: "EGX", index_name: "EGX30", index_close: 52200, index_change_pct: 0.45, advancing: 82, declining: 90, unchanged: 28, total_stocks: 200 }}
                    accumulation={[
                        { symbol: "TMGH", accumulation_score: 91, r_vol: 2.4, consecutive_acc_days: 5 },
                        { symbol: "HRHO", accumulation_score: 84, r_vol: 1.9, consecutive_acc_days: 3 },
                    ]}
                />
                <FairValueGaugeCard
                    items={[
                        { symbol: "RACC", currency: "ج.م", current_price: 7.17, fair_value: 9.8, upside_pct: 36.7 },
                        { symbol: "ABUK", currency: "ج.م", current_price: 62.0, fair_value: 55.0, upside_pct: -11.3 },
                    ]}
                />
            </>
        );

        expect(screen.getByTestId("comparison-mirror-card")).toBeTruthy();
        expect(screen.getByText(/أفضلية نسبية: TMGH/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "FWRY" }));
        expect(screen.getAllByText(/FWRY/).length).toBeGreaterThan(0);

        expect(screen.getByTestId("portfolio-visual-card")).toBeTruthy();
        expect(screen.getByText(/تركز مرتفع في EPPK/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "TASI" }));
        expect(screen.getByText("توزيع أوزان المحفظة والأرباح (TASI)")).toBeTruthy();

        expect(screen.getByTestId("market-breadth-card")).toBeTruthy();
        expect(screen.getByText(/صاعد 82 \(41%\)/)).toBeTruthy();
        expect(screen.getByTestId("accumulation-heatmap-card")).toBeTruthy();
        expect(screen.getByText("91/100")).toBeTruthy();

        expect(screen.getByTestId("fair-value-gauge-card")).toBeTruthy();
        expect(screen.getByText(/صعود محتمل \+36\.7%/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /ABUK/ }));
        expect(screen.getByText(/متضخم \(-11\.3%\)/)).toBeTruthy();
    });

    test("FormattedChatMessage skips empty ExportableTable when carrier table only has visuals payload", () => {
        render(
            <FormattedChatMessage
                role="assistant"
                content="هذا ملخص محفظتك الحالية."
                isStreaming={false}
                tables={[
                    {
                        id: "visuals_1",
                        title: "",
                        headers: [],
                        rows: [],
                        visuals: {
                            portfolio: {
                                cash_balance: 2000,
                                positions: [
                                    { symbol: "VALU", market: "EGX", currency: "ج.م", market_value: 5000, profit_pct: 3.5, profit_value: 170 },
                                ],
                            },
                        },
                    },
                ]}
            />
        );
        expect(screen.queryByText("جدول البيانات والتحليل")).toBeNull();
        expect(screen.getByTestId("portfolio-visual-card")).toBeTruthy();
    });

    test("Round-3 visuals (RecommendationsTracker, ShariaPurification slider, PriceTrapsRadar, DisclosuresTimeline) render accurately", () => {
        render(
            <>
                <RecommendationsTrackerCard
                    items={[
                        { symbol: "AMES", currency: "ج.م", entry_price: 51.1, stop_loss: 48.0, target_price: 56.5, last_close: 50.1, date: "2026-11-11" },
                        { symbol: "ATQA", currency: "ج.م", entry_price: 9.0, stop_loss: 8.5, target_price: 10.2, last_close: 9.61, date: "2026-11-14" },
                    ]}
                />
                <ShariaPurificationCard
                    sharia={{
                        symbol: "ABUK",
                        currency: "ج.م",
                        is_sharia_compliant: true,
                        sharia_index: "EGX33 Shariah",
                        shares_count: 1000,
                        coupon_per_share: 2.0,
                        purification_rate_pct: 5.0,
                        zakat_amount: 155.0,
                    }}
                />
                <PriceTrapsRadarCard
                    traps={{
                        currency: "ج.م",
                        bearTraps: [{ symbol: "HRHO", close: 24.5, conviction: 84, relativeVolume: 2.1 }],
                        bullTraps: [{ symbol: "CRST", close: 2.44, conviction: 76, wickPct: 48.2 }],
                    }}
                />
                <DisclosuresTimelineCard
                    items={[
                        { symbol: "COMI", title: "شراء رئيس مجلس الإدارة", sentiment: "positive", disclosure_date: "2026-11-16" },
                        { symbol: "POUL", title: "توزيع نقدي 1.90 ج.م", sentiment: "positive", disclosure_date: "2026-11-16" },
                    ]}
                />
            </>
        );

        expect(screen.getByTestId("recommendations-tracker-card")).toBeTruthy();
        expect(screen.getByText(/تحت الدخول التاريخي \(-2\.0%\)/)).toBeTruthy();
        expect(screen.getByText(/صعود عن الدخول \(\+6\.8%\)/)).toBeTruthy();

        expect(screen.getByTestId("sharia-purification-card")).toBeTruthy();
        expect(screen.getByText(/صافي حلال: 1900\.0 ج\.م/)).toBeTruthy();
        expect(screen.getByText(/تطهير: 100\.0 ج\.م/)).toBeTruthy();
        const slider = screen.getByLabelText("عدد الأسهم لحساب التطهير");
        fireEvent.change(slider, { target: { value: "2000" } });
        expect(screen.getByText(/صافي حلال: 3800\.0 ج\.م/)).toBeTruthy();
        expect(screen.getByText(/تطهير: 200\.0 ج\.م/)).toBeTruthy();

        expect(screen.getByTestId("price-traps-radar-card")).toBeTruthy();
        expect(screen.getByText(/ثقة 84%/)).toBeTruthy();
        expect(screen.getByText(/تحذير 76%/)).toBeTruthy();

        expect(screen.getByTestId("disclosures-timeline-card")).toBeTruthy();
        expect(screen.getByText(/المزاج: غالب إيجابي/)).toBeTruthy();
        expect(screen.getByText("شراء رئيس مجلس الإدارة")).toBeTruthy();
    });

    test("RecommendationsTrackerCard spaces tight/extreme levels cleanly & ShariaPurificationCard spans 100% when rate is 0", () => {
        const { container } = render(
            <>
                <RecommendationsTrackerCard
                    items={[
                        { symbol: "TIGHT", currency: "ج.م", entry_price: 50.0, stop_loss: 55.0, target_price: 55.0, last_close: 120.0 },
                    ]}
                />
                <ShariaPurificationCard
                    sharia={{
                        symbol: "PURE",
                        currency: "ج.م",
                        is_sharia_compliant: true,
                        shares_count: 500,
                        coupon_per_share: 4.0,
                        purification_rate_pct: 0,
                    }}
                />
            </>
        );

        // Invalid stop_loss (55 >= entry 50) must fallback to entry * 0.94 = 47.00
        const stopTxt = screen.getByText("وقف 47.00");
        const entryTxt = screen.getByText("دخول 50.00");
        const targetTxt = screen.getByText("هدف 55.00");
        const x1 = Number(stopTxt.getAttribute("x"));
        const x2 = Number(entryTxt.getAttribute("x"));
        const x3 = Number(targetTxt.getAttribute("x"));
        expect(x1).toBeGreaterThanOrEqual(64);
        expect(x2 - x1).toBeGreaterThanOrEqual(89);
        expect(x3 - x2).toBeGreaterThanOrEqual(89);
        expect(x3).toBeLessThanOrEqual(516);

        const curTxt = screen.getByText(/الآن 120\.0 ج\.م/);
        const cx = Number(curTxt.getAttribute("x"));
        expect(cx).toBeLessThanOrEqual(504);

        const halalBar = container.querySelector('[data-testid="sharia-purification-card"] .bg-emerald-500\\/85');
        expect(halalBar?.getAttribute("style")).toContain("width: 100%");
        expect(screen.queryByText(/تطهير:\s*\d/)).toBeNull();
    });

    test("QuantIntelligenceCard and SmartDcaPlanCard (allowed & blocked) render cleanly", () => {
        render(
            <>
                <QuantIntelligenceCard
                    items={[
                        {
                            symbol: "MFPC",
                            name_ar: "موبكو للأسمدة",
                            currency: "ج.م",
                            setup_regime: "value_in_downtrend",
                            setup_regime_label_ar: "⚖️ قيمة مالية في تصحيح فني — مراقبة الانعكاس",
                            conflict_resolution_ar: "تعارض واضح: رخيص مالياً لكن هابط فنياً",
                            technical_score: 36,
                            fundamental_score: 82,
                            conviction_score: 54,
                            bull_case: ["تحت القيمة العادلة بنسبة +48%"],
                            bear_case: ["كسر متوسط EMA50"],
                            monte_carlo: {
                                paths_count: 5000,
                                horizon_days: 10,
                                daily_limit_pct: 20,
                                target_barrier: 39.8,
                                stop_barrier: 34.5,
                                prob_hit_target_first_pct: 38.4,
                                prob_hit_stop_first_pct: 31.2,
                                prob_stay_in_range_pct: 30.4,
                                expected_10d_range: { p10: 33.8, p50: 36.7, p90: 40.9 },
                            },
                            self_learning: {
                                learned_lesson_ar: "معايرة بايزية بسجل السهم (40 نافذة)",
                            },
                            macro_sensitivity: {
                                summary_ar: "تحوط الماكرو: ارتباط الدولار +0.35",
                            },
                        },
                    ]}
                />
                <SmartDcaPlanCard
                    plan={{
                        symbol: "MFPC",
                        currency: "ج.م",
                        dca_allowed: true,
                        old_avg_price: 38.15,
                        new_avg_price_full: 37.1,
                        prob_breakeven_10d_before_pct: 29.0,
                        prob_breakeven_10d_after_pct: 46.5,
                        hard_invalidation_stop: 33.4,
                        tranches: [
                            { tranche: 1, label: "الدفعة الأولى", weight_pct: 45, limit_price: 36.2, shares: 120, cost: 4344, fee: 7.82, avg_after: 37.9 },
                            { tranche: 2, label: "الدفعة الثانية", weight_pct: 55, limit_price: 34.5, shares: 155, cost: 5347.5, fee: 9.63, avg_after: 37.1 },
                        ],
                    }}
                />
                <SmartDcaPlanCard
                    plan={{
                        symbol: "CRST",
                        currency: "ج.م",
                        dca_allowed: false,
                        verdict_ar: "⛔ غير مناسب للتبريد حالياً",
                        rejection_reason_ar: "رصد تصريف مؤسسي قوي (80/100)",
                        current_loss_pct: -24.5,
                        capital_protection_stop: 1.48,
                    }}
                />
            </>
        );

        expect(screen.getByTestId("quant-intelligence-card")).toBeTruthy();
        expect(screen.getByText(/ثقة كمية 54\/100/)).toBeTruthy();
        expect(screen.getByText(/هدف \(39\.8\): 38\.4%/)).toBeTruthy();
        expect(screen.getByText(/تحت القيمة العادلة بنسبة \+48%/)).toBeTruthy();

        const dcaCards = screen.getAllByTestId("smart-dca-plan-card");
        expect(dcaCards.length).toBe(2);
        expect(screen.getByText(/احتمال التعادل خلال 10 جلسات: 29% ⬅️ 46\.5%/)).toBeTruthy();
        expect(screen.getByText(/حارس التبريد — CRST/)).toBeTruthy();
        expect(screen.getByText(/رصد تصريف مؤسسي قوي \(80\/100\)/)).toBeTruthy();
    });
});
