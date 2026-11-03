import { cleanVoiceText, extractVoiceAnalysisSpeech } from "../voice-utils";

describe("voice-utils", () => {
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

    it("extracts conversational financial analysis and chatbot opinion without technical jargon", () => {
        const sample = `📊 **تحليل سهم فوري (FWRY)**
السعر الحالي: 8.45 ج.م (+1.5%)

🔍 **المؤشرات الفنية**:
- RSI: 58 (منطقة محايدة)
- MACD: تقاطع إيجابي أعلى الصفر
- متوسط متحرك 50: أعلى من 200

📈 **حركة السيولة والتجميع**:
السهم يمر بمرحلة تجميع مؤسسي ملحوظ مع دخول سيولة شرائية ذكية.

🎯 **الدعوم والمقاومات**:
- الدعم الأول: 8.20 ج.م
- المقاومة الأولى: 8.70 ج.م
- المستهدف: 9.20 ج.م
- وقف الخسارة: كسر 8.00 ج.م

💡 **الرأي الفني وخلاصة أرتورو**:
نظرة أرتورو إيجابية على السهم. نرى السهم فرصة جيدة للاحتفاظ أو الشراء التراكمي قرب 8.20 جنيه مستهدفاً 8.70 ثم 9.20 جنيه، مع وقف الخسارة كسر 8.00 جنيه.

⚠️ تنبيه: تحليلات منصة EGX BOTS مبنية على أحدث البيانات المتاحة.`;

        const voiceSpeech = extractVoiceAnalysisSpeech(sample, "حلل سهم فوري");

        // Must contain chatbot opinion and accumulation
        expect(voiceSpeech).toContain("نظرة أرتورو إيجابية على السهم");
        expect(voiceSpeech).toContain("تجميع مؤسسي");
        expect(voiceSpeech).toContain("8.20 جنيه");

        // Must NOT contain technical acronyms or noise
        expect(voiceSpeech).not.toContain("RSI");
        expect(voiceSpeech).not.toContain("MACD");
        expect(voiceSpeech).not.toContain("FWRY");
        expect(voiceSpeech).not.toContain("تنبيه:");
        expect(voiceSpeech).not.toContain("EGX BOTS");
        expect(voiceSpeech).not.toContain("|");
        expect(voiceSpeech).not.toContain("**");
    });

    it("handles short empty or null inputs gracefully", () => {
        expect(cleanVoiceText("")).toBe("");
        expect(cleanVoiceText("   ")).toBe("");
        expect(cleanVoiceText("أهلاً بك")).toBe("أهلاً بك");
        expect(extractVoiceAnalysisSpeech("")).toContain("تمام يا فندم");
    });
});
