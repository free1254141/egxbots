import { cleanVoiceText } from "../voice-utils";

describe("voice-utils cleanVoiceText", () => {
    it("cleans markdown and extracts spoken summary without losing digits", () => {
        const sample = `📊 **تحليل سهم فوري (FWRY)**
السهم يتداول حالياً عند 8.45 ج.م بارتفاع +1.5%.
- **الدعم الرئيسي**: 8.20 ج.م
- **المقاومة الأولى**: 8.70 ج.م
درجة التجميع: تجميع مؤسسي ملحوظ.

| المؤشر | القيمة |
|---|---|
| RSI | 58 |

تنبيه: تحليلات منصة EGX BOTS مبنية على أحدث البيانات المتاحة ولا تعد توصية.`;

        const cleaned = cleanVoiceText(sample, 180);

        expect(cleaned).toContain("8.45 جنيه");
        expect(cleaned).toContain("8.20 جنيه");
        expect(cleaned).toContain("8.70 جنيه");
        expect(cleaned).not.toContain("تنبيه:");
        expect(cleaned).not.toContain("EGX BOTS");
        expect(cleaned).not.toContain("**");
        expect(cleaned).not.toContain("|");
        expect(cleaned.length).toBeLessThanOrEqual(185);
    });

    it("handles short empty or null inputs gracefully", () => {
        expect(cleanVoiceText("")).toBe("");
        expect(cleanVoiceText("   ")).toBe("");
        expect(cleanVoiceText("أهلاً بك")).toBe("أهلاً بك");
    });
});
