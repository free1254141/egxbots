import { extractFallbackStocks } from "../portfolio-extract";

describe("portfolio-extract", () => {
    describe("extractFallbackStocks", () => {
        it("extracts ticker from user query and price from assistant text (e.g. MOED scenario)", () => {
            const text = `السعر: 0.404 ج.م (تغيّر الجلسة: −5.39%)
التقييم الفني العام: 🔴 سلبي / مخاطرة مرتفعة.
📌 حالة السهم في محفظتك: غير مسجل ضمن مراكز محفظتك المحفوظة (ACGC، ACAP، ACAMD، ABUK).
الدعم الأول: 0.39
المقاومة الأولى: 0.72`;
            const userQuery = "moed";
            const buttons = [
                "اختبر الاتجاه وMACD على MOED واعرض نسبة النجاح والعائد التراكمي",
                "قارن الاستراتيجيات القابلة للاختبار على MOED",
            ];

            const result = extractFallbackStocks(text, userQuery, buttons);
            expect(result.length).toBe(1);
            expect(result[0].symbol).toBe("MOED");
            expect(result[0].price).toBe(0.404);
            expect(result[0].quantity).toBe(100);
        });

        it("extracts ticker from suggested buttons if user query is not a single ticker", () => {
            const text = `السعر الحالي | 34.50 | آخر إغلاق
المقاومة: 38.00`;
            const userQuery = "حلل لي السهم ده سريعاً";
            const buttons = ["اختبر الاتجاه وMACD على SKPC", "قارن بـ COMI"];

            const result = extractFallbackStocks(text, userQuery, buttons);
            expect(result.some(s => s.symbol === "SKPC")).toBe(true);
            const skpc = result.find(s => s.symbol === "SKPC");
            expect(skpc?.price).toBe(34.5);
        });

        it("ignores system words and acronyms like RSI, MACD, EMA, EGX", () => {
            const text = "مؤشر RSI عند 45 ومؤشر MACD سالب";
            const userQuery = "ما رأيك في المؤشرات؟";
            const buttons: any[] = [];

            const result = extractFallbackStocks(text, userQuery, buttons);
            expect(result.length).toBe(0);
        });
    });
});
