/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import StockCard from "../StockCard";
import { FormattedChatMessage } from "../FormattedChatMessage";

// Mock next/navigation useRouter
const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
    useRouter: () => ({
        push: mockPush,
    }),
}));

describe("StockCard Component", () => {
    beforeEach(() => {
        jest.clearAllMocks();
        Object.assign(navigator, {
            clipboard: {
                writeText: jest.fn().mockImplementation(() => Promise.resolve()),
            },
        });
    });

    test("renders composite score badge when composite_score is present", () => {
        const sampleStock = {
            symbol: "AFMC",
            nameAr: "مطاحن الإسكندرية",
            price: 124.50,
            changePercent: 13.09,
            composite_score: 84,
            composite_grade: "A+",
            composite_verdict: "فرصة استثمارية ممتازة",
            rsi: 62.0,
        };

        render(<StockCard stock={sampleStock} />);
        expect(screen.getByText(/سكور: 84\/100/)).toBeTruthy();
        expect(screen.getByText(/\(A\+\)/)).toBeTruthy();
    });

    test("renders stock opportunity card with quantitative metrics and domain badges", () => {
        const sampleStock = {
            symbol: "TMGH",
            nameAr: "طلعت مصطفى",
            price: 58.20,
            changePercent: 3.45,
            entryRange: "57.50 - 58.50 ج.م",
            target1: "62.50 ج.م (+7.4%)",
            stopLoss: "55.80 ج.م (-4.1%)",
            riskReward: "1 : 2.2 🎯",
            rsi: 58.2,
            rVol: 2.4,
            king_ai_score: 0.685,
            sector: "التطوير العقاري",
            isShariah: true,
            signalType: "فرصة مضاربة",
        };

        render(<StockCard stock={sampleStock} />);

        // Basic Info
        expect(screen.getByText("#TMGH")).toBeTruthy();
        expect(screen.getByText("طلعت مصطفى")).toBeTruthy();
        expect(screen.getByText("التطوير العقاري")).toBeTruthy();
        expect(screen.getByText("+3.45%")).toBeTruthy();

        // Badges
        expect(screen.getByText(/EGX33 شرعي/)).toBeTruthy();
        expect(screen.getByText("فرصة مضاربة")).toBeTruthy();
        expect(screen.getByText(/68.5%/)).toBeTruthy();

        // Quantitative Trading Plan Metrics
        expect(screen.getByText("57.50 - 58.50 ج.م")).toBeTruthy();
        expect(screen.getByText("62.50 ج.م (+7.4%)")).toBeTruthy();
        expect(screen.getByText("55.80 ج.م (-4.1%)")).toBeTruthy();
        expect(screen.getByText("1 : 2.2 🎯")).toBeTruthy();

        // Momentum / RSI
        expect(screen.getByText("58.2")).toBeTruthy();
        expect(screen.getByText(/2.4/)).toBeTruthy();

        // Buttons
        expect(screen.getByText("فتح الشارت والمستويات اللحظية")).toBeTruthy();
        expect(screen.getByText("أضف للمحفظة")).toBeTruthy();
        expect(screen.getByText("آخر الأخبار")).toBeTruthy();
    });

    test("clicking chart button navigates to /chart?symbol=TMGH", () => {
        const sampleStock = {
            symbol: "TMGH",
            nameAr: "طلعت مصطفى",
            price: 58.20,
        };

        render(<StockCard stock={sampleStock} />);
        const chartBtn = screen.getByText("فتح الشارت والمستويات اللحظية");
        fireEvent.click(chartBtn);

        expect(mockPush).toHaveBeenCalledWith("/chart?symbol=TMGH");
    });

    test("clicking add to portfolio triggers callback and updates button text", () => {
        const sampleStock = {
            symbol: "COMI",
            nameAr: "التجاري الدولي",
            price: 85.50,
        };
        const mockAdd = jest.fn();

        render(<StockCard stock={sampleStock} onAddToPortfolio={mockAdd} />);
        const addBtn = screen.getByText("أضف للمحفظة");
        fireEvent.click(addBtn);

        expect(mockAdd).toHaveBeenCalledWith("COMI");
        expect(screen.getByText("تمت الإضافة للمحفظة ✅")).toBeTruthy();
    });

    test("clicking copy button copies formatted signal card text to clipboard", () => {
        const sampleStock = {
            symbol: "FWRY",
            nameAr: "فوري",
            price: 8.50,
            target1: "9.20 ج.م",
        };

        render(<StockCard stock={sampleStock} />);
        const copyBtn = screen.getByTitle("نسخ ملخص الإشارة");
        fireEvent.click(copyBtn);

        expect(navigator.clipboard.writeText).toHaveBeenCalled();
    });

    test("FormattedChatMessage renders multiple stock cards in responsive 2-column grid", () => {
        const jsonContent = `
إليك أفضل الفرص المرصودة حالياً في السوق:

\`\`\`json
[
  {
    "type": "stock_card",
    "symbol": "TMGH",
    "nameAr": "طلعت مصطفى",
    "price": 58.20,
    "entryRange": "57.50 - 58.50 ج.م",
    "target1": "62.50 ج.م",
    "stopLoss": "55.80 ج.م"
  },
  {
    "type": "stock_card",
    "symbol": "COMI",
    "nameAr": "التجاري الدولي",
    "price": 85.50,
    "entryRange": "84.00 - 85.50 ج.م",
    "target1": "91.00 ج.م",
    "stopLoss": "82.50 ج.م"
  }
]
\`\`\`
نتمنى لك تداولاً موفقاً!
        `;

        render(<FormattedChatMessage role="assistant" content={jsonContent} />);

        expect(screen.getByText("#TMGH")).toBeTruthy();
        expect(screen.getByText("طلعت مصطفى")).toBeTruthy();
        expect(screen.getByText("#COMI")).toBeTruthy();
        expect(screen.getByText("التجاري الدولي")).toBeTruthy();
    });

    test("FormattedChatMessage automatically converts standard stock analysis table to interactive StockCard", () => {
        const markdownAnalysis = `
### 📊 تحليل سهم طلعت مصطفى (TMGH)
السعر الأخير: 80.40 ج.م (تغير الجلسة: +0.31% بتاريخ 29-10-2026) | التقييم الفني العام: 🟡 حيادي للمراقبة

| المستوى / النقطة | القيمة (ج.م) | الوصف الفني |
|---|---|---|
| الإغلاق الحالي | 80.40 | آخر إغلاق متاح |
| الدعم الأول | 79.40 | منطقة اختبار حرجة |
| الدعم الثاني | 76.22 | الدعم التالي عند كسر الأول |
| المقاومة الأولى | 93.00 | عقبة رئيسية |
| المقاومة الثانية | 100.90 | مقاومة بعيدة |
| RSI (14) | 39.08 | ضعف نسبي |

الرأي التوليفي: السهم متوافق مع الشريعة (EGX33).
        `;

        render(<FormattedChatMessage role="assistant" content={markdownAnalysis} />);

        // Stock Card should be rendered
        expect(screen.getByText("#TMGH")).toBeTruthy();
        expect(screen.getAllByText("80.40").length).toBeGreaterThan(0);
        expect(screen.getByText("EGX33 شرعي")).toBeTruthy();
        expect(screen.getByText(/فتح الشارت/)).toBeTruthy();
        expect(screen.getByText("أضف للمحفظة")).toBeTruthy();

        // Technical levels must be displayed instead of recommendation trading plan labels
        expect(screen.getAllByText("الدعم الأول").length).toBeGreaterThan(0);
        expect(screen.getAllByText("المقاومة الأولى").length).toBeGreaterThan(0);
        expect(screen.getAllByText("الدعم الحاسم (2)").length).toBeGreaterThan(0);
        expect(screen.getAllByText("المقاومة 2").length).toBeGreaterThan(0);
        expect(screen.queryByText("نطاق الدخول")).toBeNull();
        expect(screen.queryByText("المستهدف 1")).toBeNull();
        expect(screen.queryByText("وقف الخسارة")).toBeNull();
    });

    test("FormattedChatMessage automatically converts recommendations table to interactive StockCard grid", () => {
        const recTableMarkdown = `
إليك قائمة التوصيات المفتوحة الحالية:

| السهم | الدخول | المستهدف 1 | المستهدف 2 | وقف الخسارة | العائد الحالي |
|---|---|---|---|---|---|
| CRST | 2.49 | 2.64 | 2.73 | 2.40 | 0.00% |
| LCSW (شرعي) | 35.73 | 37.34 | 38.41 | 35.73 | +2.07% |

بالتوفيق في تداولاتك!
        `;

        render(<FormattedChatMessage role="assistant" content={recTableMarkdown} />);

        // Both stock cards should be rendered
        expect(screen.getByText("#CRST")).toBeTruthy();
        expect(screen.getAllByText("2.49").length).toBeGreaterThan(0);
        expect(screen.getByText("#LCSW")).toBeTruthy();
        expect(screen.getAllByText("35.73").length).toBeGreaterThan(0);
    });

    test("FormattedChatMessage parses KING AI and EGX AI scores from analysis table", () => {
        const kingTableMarkdown = `
### 📊 تحليل سهم طلعت مصطفى (TMGH)
السعر الأخير: 80.40 ج.م

| المؤشر / المقياس | القيمة | القراءة والتقييم |
|---|---|---|
| RSI (14) | 55.40 | منطقة حيادية |
| تقييم نموذج KING AI | 74.2% | ثقة صعود جيدة |
| تقييم نموذج EGX AI | 68.0% | إيجابي |
        `;

        render(<FormattedChatMessage role="assistant" content={kingTableMarkdown} />);

        expect(screen.getByText("#TMGH")).toBeTruthy();
        expect(screen.getByText(/تقييم KING AI:/)).toBeTruthy();
        expect(screen.getAllByText("74.2%").length).toBeGreaterThan(0);
    });

    test("FormattedChatMessage accurately extracts price and change when price is in preceding text like ATQA", () => {
        const atqaMarkdown = `
عتاقة — مصر الوطنية للصلب (ATQA) ✅ متوافق مع الشريعة ومدرج ضمن مؤشر EGX 33
آخر إغلاق متاح: 9.05 ج.م (جلسة 29-10-2026، +0.56%)

| المؤشر / المقياس | القيمة | القراءة |
|---|---|---|
| RSI (14) | 26.77 | تشبع بيعي |
| MACD | -0.150 | سالب |
| EMA 50 | 9.80 | السعر أدناه |
| EMA 200 | 8.90 | السعر أعلاه |
| الحجم النسبي | 1.45 | نشاط مرتفع |
| مرحلة وايكوف | تجميع قوي | تجميع مؤسسي |

رأي التحليل الفني للمراقبة.
        `;

        render(<FormattedChatMessage role="assistant" content={atqaMarkdown} />);

        expect(screen.getByText("#ATQA")).toBeTruthy();
        expect(screen.getAllByText("9.05").length).toBeGreaterThan(0);
        expect(screen.getByText("+0.56%")).toBeTruthy();
        expect(screen.getAllByText(/تجميع قوي/).length).toBeGreaterThan(0);
        expect(screen.getByText(/EMA 50:/)).toBeTruthy();
    });

    test("FormattedChatMessage distinguishes تاريخ الدخول from سعر الدخول correctly", () => {
        const fullTableMarkdown = `
| السهم | نوع الإشارة | تاريخ الدخول | سعر الدخول | السعر الحالي | العائد الحالي | المستهدف 1 | المستهدف 2 | وقف الخسارة | الأفق |
|---|---|---|---|---|---|---|---|---|---|
| **CRST** | اختراق 🚀 | 30-10-2026 | 2.49 | 2.49 | 0.00% | 2.64 | 2.73 | 2.40 | 1–3 جلسات |
| **EDFM** | انفجار حجم ⚡ | 30-10-2026 | 376.05 | 376.05 | 0.00% | 392.97 | 404.25 | 364.77 | 1–3 جلسات |
        `;

        render(<FormattedChatMessage role="assistant" content={fullTableMarkdown} />);

        // CRST must be 2.49, NOT 30.00
        expect(screen.getByText("#CRST")).toBeTruthy();
        expect(screen.getAllByText("2.49").length).toBeGreaterThan(0);
        expect(screen.queryByText("30.00")).toBeNull();

        // EDFM must be 376.05, NOT 30.00
        expect(screen.getByText("#EDFM")).toBeTruthy();
        expect(screen.getAllByText("376.05").length).toBeGreaterThan(0);
        expect(screen.getByText("392.97 ج.م")).toBeTruthy();
    });

    test("FormattedChatMessage parses MAAL with full Arabic name, Unicode minus changePct, and enriches RSI from second table", () => {
        const maalMarkdown = `## 📊 تحليل سهم مرسيليا المصرية الخليجية للاستثمار العقاري (MAAL)
آخر إغلاق متاح: 6.90 ج.م (جلسة 05-11-2026، −0.86%) | التقييم الفني العام: 🔴 سلبي / أداء فني ضعيف (سكور 49/100 — C)

### المستويات الفنية
| المستوى | السعر (ج.م) | المسافة من الإغلاق | الدلالة |
|---|---|---|---|
| الإغلاق الحالي | 6.90 | — | جلسة 05-11-2026 |
| الدعم الأول | 4.88 | −29.28% | قاع 20 جلسة |
| الدعم الثاني | 4.68 | −32.17% | دعم تالي |
| المقاومة الأولى | 10.90 | +57.97% | قمة 20 جلسة |
| المقاومة الثانية | 12.25 | +77.54% | قمة أبعد |

### المؤشرات الفنية والبيانات الأساسية
| المؤشر | القيمة | القراءة |
|---|---|---|
| RSI (14) | 44.80 | حيادي |
| EMA 50 | 8.17 | السعر أسفله |
| EMA 200 | 6.95 | السعر أسفله |
| الحجم النسبي | 0.50 | نشاط ضعيف |
| KING AI | 59.05% | حيادي |
| EGX AI | 45.41% | ضعيف |`;

        render(<FormattedChatMessage role="assistant" content={maalMarkdown} />);

        expect(screen.getByText("#MAAL")).toBeTruthy();
        expect(screen.getByText("مرسيليا المصرية الخليجية للاستثمار العقاري")).toBeTruthy();
        expect(screen.getByText("-0.86%")).toBeTruthy();
        expect(screen.getByText("44.8")).toBeTruthy();
        expect(screen.getByText(/سكور: 49\/100/)).toBeTruthy();
        expect(screen.getByText("🔴 سلبي / أداء فني ضعيف")).toBeTruthy();
    });

    test("FormattedChatMessage renders disclosure PDF iframe card once and deduplicates pdf + image links for the same UUID", () => {
        const duplicateDisclosureMd = [
            "## 🔗 مصدر إفصاح IEEC — بيع داخلي 11,000 سهم",
            "",
            "**المستند الرسمي (PDF):**",
            "[📄 فتح مستند الـ PDF الأصلي — البورصة المصرية](/api/disclosures/pdf/0e2f2da5-234f-41ac-89f6-d4beb0266d00)",
            "",
            "**صورة الإفصاح:**",
            "[🖼️ عرض صورة الإفصاح](/api/disclosures/image/0e2f2da5-234f-41ac-89f6-d4beb0266d00)",
            "",
            "**بيانات السجل:** كود الإفصاح `0e2f2da5-234f-41ac-89f6-d4beb0266d00` — النوع: تعاملات داخليين."
        ].join("\n");

        const { container } = render(<FormattedChatMessage role="assistant" content={duplicateDisclosureMd} />);

        const iframes = container.querySelectorAll("iframe");
        expect(iframes.length).toBe(1);
        expect(iframes[0].getAttribute("src")).toContain("/api/disclosures/pdf/0e2f2da5-234f-41ac-89f6-d4beb0266d00");
        expect(screen.queryByText(/صورة الإفصاح/)).toBeNull();
    });

    test("FormattedChatMessage parses multi-stock comparison table (NIPH vs MPCI) into accurate side-by-side StockCards without 60100/100 or 0.00 bugs", () => {
        const comparisonMd = `## ⚖️ مقارنة: النيل للأدوية (NIPH) مقابل ممفيس للأدوية (MPCI)

| البند | النيل للأدوية (NIPH) | ممفيس للأدوية (MPCI) |
|---|---|---|
| **السعر** | 277.25 ج.م (-1.33%) | **251.57 ج.م (+0.63%)** |
| **السكور الكلي** | 60/100 — B (مراقبة) | 56/100 — B (مراقبة) |
| **الشرعية** | ✅ متوافق (EGX33) | ✅ متوافق (EGX33) |
| **RSI (14)** | **48.8** (حيادي متوازن) | 40.2 (يميل للضعف) |
| **MACD / الإشارة / الهيستوجرام** | -7.745 / -11.952 / **+4.207** | -1.494 / -0.453 / -1.042 |
| **EMA 50 / EMA 200** | 286.95 / 219.52 | 253.68 / 201.95 |
| **الدعم / المقاومة الأولى** | 205.00 / 313.00 | 228.00 / 289.99 |
| **المسافة للمقاومة الأولى** | +12.9% | **+15.3%** |
| **الدعم والمقاومة الثانية** | 190.10 / 338.00 | 215.05 / 298.00 |
| **الحجم النسبي** | 0.50x (ضعيف) | 0.44x (ضعيف) |
| **وايكوف** | تجميع ضعيف (55) | محايد |
| **KING AI / EGX AI** | 50.2% / 57.5% | **60.8%** / 57.7% |
| **مضاعف الربحية P/E** | 45.4x | **9.66x** |`;

        render(<FormattedChatMessage role="assistant" content={comparisonMd} />);

        expect(screen.getByText("#NIPH")).toBeTruthy();
        expect(screen.getByText("#MPCI")).toBeTruthy();

        expect(screen.getByText("سكور: 60/100")).toBeTruthy();
        expect(screen.getByText("سكور: 56/100")).toBeTruthy();
        expect(screen.queryByText(/60100/)).toBeNull();

        expect(screen.getAllByText("277.25").length).toBeGreaterThan(0);
        expect(screen.getAllByText("251.57").length).toBeGreaterThan(0);
        expect(screen.queryByText("0.00")).toBeNull();

        expect(screen.getByText("205.00 ج.م")).toBeTruthy();
        expect(screen.getByText("313.00 ج.م")).toBeTruthy();
        expect(screen.getByText("190.10 ج.م")).toBeTruthy();
        expect(screen.getByText("338.00 ج.م")).toBeTruthy();

        expect(screen.getAllByText("-7.745 / -11.952 / +4.207").length).toBeGreaterThan(0);
        expect(screen.queryByText(/\*\*\+4\.207\*\*/)).toBeNull();
    });
});
