/** @jest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { FormattedChatMessage } from "../FormattedChatMessage";

jest.mock("next/navigation", () => ({
    useRouter: () => ({ push: jest.fn() })
}));

describe("Stock Card Live Price Unification Tests", () => {
    it("correctly parses live provider price row 'أحدث سعر من المزود' as 3.09 EGP instead of 0.00", () => {
        const text = `
## 📰 أخبار CRST — كريست مارك للمقاولات والتطوير العقاري

**الخلاصة:** لم يُرجع مصدر أخبار المنصة أي عنوان موثق على السهم في الفترة من **02-11-2026 حتى 09-11-2026**.

### 📊 أين يقف السهم الآن
| البند | القيمة |
|---|---|
| أحدث سعر من المزود (11:39 القاهرة، 09-11-2026) | 3.09 ج.م (−0.32%) |
| RSI | 58.25 (إيجابي، لا تشبع بيعي) |
| MACD / إشارته / الهيستوجرام | 0.0006 / −0.1083 / +0.1089 |
| الحجم النسبي | 1.94 (نشاط أعلى من متوسطه) |
| EMA 50 / EMA 200 | 2.75 / 1.91 (السعر أعلاهما) |
| مرحلة وايكوف | تجميع — جلستان متتاليتان |
| التقييم الشامل | 79/100 (A — إيجابي واعد للمتابعة) |
        `;

        render(<FormattedChatMessage role="assistant" content={text} />);

        // Price should be 3.09, NOT 0.00 and NOT —
        const priceElement = screen.getByText("3.09");
        expect(priceElement).toBeInTheDocument();

        // Change should be -0.32%
        const changeElement = screen.getByText("-0.32%");
        expect(changeElement).toBeInTheDocument();

        // Symbol should match CRST badge
        const symbolElement = screen.getAllByText(/CRST/)[0];
        expect(symbolElement).toBeInTheDocument();
    });

    it("unifies stock card price to the latest live price from the header (242.80 instead of stale 243.39)", () => {
        const text = `
## 📊 تحليل سهم العامة لاستصلاح الأراضي والتنمية والتعمير (AALR)

**السعر الأخير:** 242.80 ج.م (تغير الجلسة: −0.24% — أحدث سعر من المزود، جُلب 09-11-2026 الساعة 10:40 بتوقيت القاهرة) | **إغلاق جلسة 08-11-2026:** 243.39 ج.م (+2.26%) | **التقييم الفني العام:** 🟡 حيادي للمراقبة المشروطة

### جدول المستويات الفنية
| المستوى / النقطة | القيمة (ج.م) | الوصف الفني |
|---|---|---|
| الإغلاق الحالي | 243.39 | إغلاق جلسة 08-11-2026 |
| الدعم الأول | 171.02 | قاع 20 جلسة |
| المقاومة الأولى | 259.90 | عقبة رئيسية قريبة |
        `;

        render(<FormattedChatMessage role="assistant" content={text} />);

        // 242.80 should be present in both the header and the StockCard (at least 2 occurrences)
        const priceElements = screen.getAllByText("242.80");
        expect(priceElements.length).toBeGreaterThanOrEqual(2);

        // Change should be -0.24% on the card
        const changeElements = screen.getAllByText(/-0.24%/);
        expect(changeElements.length).toBeGreaterThanOrEqual(1);

        // Symbol should match AALR badge
        const symbolElement = screen.getAllByText(/AALR/)[0];
        expect(symbolElement).toBeInTheDocument();
    });
});
