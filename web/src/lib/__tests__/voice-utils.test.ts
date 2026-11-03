import { cleanVoiceText, cleanVoiceTranscript, extractVoiceAnalysisSpeech } from "../voice-utils";
import { isVoiceBetaTester, isVoiceBetaTesterEmail } from "../chat-sharing";

describe("voice-utils", () => {
    it("cleans STT syllable stuttering, phonetic misrecognitions, and word repetitions", () => {
        expect(cleanVoiceTranscript("حلحلحل لسام ابو قير")).toBe("حلل لسهم ابو قير");
        expect(cleanVoiceTranscript("هتعصبهتعصب التجميع")).toBe("هتعصب التجميع");
        expect(cleanVoiceTranscript("هلهلهل الساعههل الساعه بتاعه مصطفى")).toBe("هل الساعه بتاعه مصطفى");
        expect(cleanVoiceTranscript("فوى فوى")).toBe("فوري");
        expect(cleanVoiceTranscript("")).toBe("");
    });
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

    it("extracts clean financial decision from real production stock dashboard without speaking disclaimers or portfolio lines", () => {
        const prodFwrySample = `### 📊 تحليل سهم فوري لتكنولوجيا البنوك والمدفوعات الإلكترونية (FWRY)

**السعر الأخير:** 15.88 ج.م (تغير الجلسة: +0.83% بتاريخ 03-11-2026) | **التقييم الفني العام:** 🔴 سلبي / مخاطرة مرتفعة (سكور 32/100 — D)

**ملخص تنفيذي:**
1. **الاتجاه:** السهم في مسار هابط واضح تحت متوسطي EMA 50 (18.20) وEMA 200 (17.90).
2. **أقرب دعم حاسم:** 15.27 ج.م (قاع 20 جلسة)؛ كسره بإغلاق يفتح الطريق إلى 14.66 ج.م.
3. **القرار التنفيذي:** لا يوجد ما يبرر الشراء الاستثماري الآن؛ توجد إشارة مضاربة لحظية نشطة بوقف صارم.

### 📌 حالة السهم في محفظتك
السهم غير مسجل ضمن مراكز محفظتك الاستثمارية المحفوظة.

### الرأي التوليفي وخطة التحرك
مالياً السهم متضخم عن قيمته العادلة، وفنياً تحت كل متوسطاته مع تصريف مسيطر، فلا يوجد أساس للتجميع الاستثماري عند المستويات الحالية. الدعم الحاسم عند 15.27 ج.م والمقاومة الأولى 19.25 ج.م.

✅ تحليل EGX Bots مبني على أحدث البيانات المتاحة ومؤرّخ بمصدره — ليس نصيحة استثمارية.`;

        const speech = extractVoiceAnalysisSpeech(prodFwrySample, "حلل سهم فوري");

        // MUST be concise, professional financial opinion
        expect(speech).not.toContain("في محفظتك");
        expect(speech).not.toContain("إشارة نموذج لا إثبات");
        expect(speech).not.toContain("ليس نصيحة استثمارية");
        expect(speech).not.toContain("FWRY");
        expect(speech).not.toContain("EMA");
        expect(speech).toContain("لا يوجد ما يبرر الشراء الاستثماري");
        expect(speech.length).toBeLessThan(250);
    });

    it("handles short empty or null inputs gracefully", () => {
        expect(cleanVoiceText("")).toBe("");
        expect(cleanVoiceText("   ")).toBe("");
        expect(cleanVoiceText("أهلاً بك")).toBe("أهلاً بك");
        expect(extractVoiceAnalysisSpeech("")).toContain("تمام يا فندم");
    });

    it("strictly restricts voice features exclusively to weeessd57 and rejects all other emails", () => {
        // Allowed: primary admin
        expect(isVoiceBetaTester({ email: "weeessd57@gmail.com" })).toBe(true);
        expect(isVoiceBetaTester({ email: "weeeessd57@gmail.com" })).toBe(true);
        expect(isVoiceBetaTester({ email: "weeasd57@gmail.com" })).toBe(true);
        expect(isVoiceBetaTester({ id: "ba9c27e8-f62d-452f-8a29-dc77fd092207" })).toBe(true);
        expect(isVoiceBetaTesterEmail("weeessd57@gmail.com")).toBe(true);

        // Strictly REJECTED: secondary admin emails and regular users
        expect(isVoiceBetaTester({ email: "acursour@gmail.com" })).toBe(false);
        expect(isVoiceBetaTester({ email: "weeeenew@gmail.com" })).toBe(false);
        expect(isVoiceBetaTester({ email: "regular_user@gmail.com" })).toBe(false);
        expect(isVoiceBetaTester({ email: "test@example.com" })).toBe(false);
        expect(isVoiceBetaTester(null)).toBe(false);
        expect(isVoiceBetaTester(undefined)).toBe(false);
        expect(isVoiceBetaTesterEmail("acursour@gmail.com")).toBe(false);
        expect(isVoiceBetaTesterEmail("weeeenew@gmail.com")).toBe(false);
    });

    it("preserves 100% of answer text in cleanVoiceText without dropping tables or wiping notes", () => {
        const textWithTableAndNotes = `تحليل سهم فوري:
| السهم | السعر | الدعم | المقاومة |
|---|---|---|---|
| فوري | 15.80 ج.م | 15.20 ج.م | 16.50 ج.م |

ملاحظة: السهم يحتاج إلى تأكيد السيولة فوق مستوى 16 جنيه للمتابعة.
تنبيه: يجب تفعيل وقف الخسارة أسفل الدعم فوراً لحماية رأس المال.
خطة التداول الموصى بها هي الدخول التدريجي على دفعات.`;

        const cleaned = cleanVoiceText(textWithTableAndNotes);

        // Verify table data is spoken
        expect(cleaned).toContain("فوري");
        expect(cleaned).toContain("15.80 جنيه");
        expect(cleaned).toContain("15.20 جنيه");
        expect(cleaned).toContain("16.50 جنيه");

        // Verify notes and alerts are 100% spoken and NOT wiped out
        expect(cleaned).toContain("ملاحظة: السهم يحتاج إلى تأكيد السيولة");
        expect(cleaned).toContain("تنبيه: يجب تفعيل وقف الخسارة");
        expect(cleaned).toContain("خطة التداول الموصى بها هي الدخول التدريجي");
    });
});
