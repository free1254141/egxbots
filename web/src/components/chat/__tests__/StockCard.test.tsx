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
        expect(screen.getByText("2.49")).toBeTruthy();
        expect(screen.getByText("#LCSW")).toBeTruthy();
        expect(screen.getAllByText("35.73").length).toBeGreaterThan(0);
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
});
