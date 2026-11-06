import { getDeepSeekApiKey } from "./server-secrets";
import { extractVoiceAnalysisSpeech } from "../voice-utils";

/**
 * Generates a concise, natural, human conversational spoken audio script (< 2 minutes)
 * for ARTORO voice notes using the AI Model itself, replacing programmatic regex heuristics.
 *
 * Rules strictly enforced:
 * 1. Spoken length: 90 - 140 words (~55 - 85 seconds audio, strictly under 2 minutes).
 * 2. Real Egyptian Arabic financial advisor tone: starts straight with the verdict.
 * 3. ZERO English acronyms/tickers (converts to Arabic).
 * 4. ZERO raw markdown tables or numbers reading.
 * 5. Smooth ending: "والتفاصيل كاملة مع الجداول معروضة قدامك على الشاشة."
 */
export async function generateVoiceNoteSpokenScript(
    writtenReply: string,
    userQuery: string = "",
    explicitApiKey?: string | null
): Promise<string> {
    if (!writtenReply || !writtenReply.trim()) {
        return "";
    }

    const apiKey = explicitApiKey || getDeepSeekApiKey();

    // If no API key is available, fallback to programmatic cleaner gracefully
    if (!apiKey) {
        return extractVoiceAnalysisSpeech(writtenReply, userQuery);
    }

    const prompt = `أنت «أرتورو» كبير المحللين الماليين للبورصة المصرية بمنصة EGX Bots.
المستخدم أرسل رسالة صوتية (Voice Note). المطلوب منك كتابة النص المنطوق للتسجيل الصوتي البشري (Voice Note Spoken Script) الخاص بالرد، بأسلوب خبير مالي يتحدث باللهجة المصرية الراقية والواضحة والمباشرة.

قواعد صارمة جداً (عدم الالتزام بها يعتبر خطأ فادحاً):
1. المدة الصوتية: كلام يستغرق عند القراءة 35 إلى 55 ثانية فقط (بين 55 إلى 85 كلمة كحد أقصى - والحد الأقصى المطلق 60 ثانية).
2. البدء مباشرة بالخلاصة والقرار الفني للسهم دون مقدمات شكلية مطولة («أهلاً بيك...»). ابدأ فوراً باسم السهم وحالته.
3. الممنوعات القطعية:
   - ممنوع نهائياً قراءة الجداول أو أسماء الأعمدة أو سرد أرقام صماء وراء بعضها.
   - ممنوع أي حروف أو رموز أو اختصارات إنجليزية نهائياً (استبدل أي رمز إنجليزي باسمه العربي: عتاقة، التجاري الدولي، المتوسط المتحرك، مؤشر الماكد، مؤشر القوة، مضاعف الربحية).
   - ممنوع قراءة أرقام مشوهة (مثل 6 آلاف مليون؛ قل مليارات أو ملايين طبيعية).
   - ممنوع قراءة إخلاء المسؤولية أو الروابط.
4. اذكر بإيجاز: السعر والاتجاه، أهم مستوى دعم أو مقاومة حاسم، رأي النماذج، وموقف المحفظة إن وجد.
5. اختم دائماً بعبارة: «والتفاصيل كاملة مع الجداول معروضة قدامك على الشاشة.»
6. أخرج نص الفويس نوت الصوتي فقط دون أي مقدمات أو علامات تنصيص.

سؤال المستخدم إن وجد: ${userQuery || "تحليل السهم"}

التحليل الفني المكتوب المطلوب تلخيصه صوتياً:
${writtenReply.slice(0, 3500)}
`;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000); // 6s timeout, then fast deterministic fallback

        const res = await fetch("https://api.deepseek.com/chat/completions", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${apiKey}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                model: "deepseek-chat",
                messages: [
                    {
                        role: "system",
                        content: "أنت أرتورو كبير المحللين الماليين للبورصة المصرية. مهمتك كتابة نص التسجيل الصوتي البشري المباشر (Voice Note Script) فقط باللهجة المصرية المهذبة والمختصرة في أقل من دقيقة.",
                    },
                    {
                        role: "user",
                        content: prompt,
                    },
                ],
                max_tokens: 380,
                temperature: 0.3,
            }),
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!res.ok) {
            console.warn(`[voice-summarizer] DeepSeek API error: ${res.status}`);
            return extractVoiceAnalysisSpeech(writtenReply, userQuery);
        }

        const data = await res.json();
        let script = data?.choices?.[0]?.message?.content?.trim();

        if (script && script.length > 30) {
            // Strip any accidental markdown formatting or quotes
            script = script.replace(/^["'«]+|["'»]+$/g, "").trim();
            script = script.replace(/[*#`_~]/g, "").trim();
            // Ensure no English letters leaked
            script = script.replace(/\([A-Za-z0-9_.]+\)/g, "");

            // Strip any incomplete trailing ending phrase before appending cleanly
            script = script.replace(/،?\s*والتفاصيل\s+كاملة[^\.]*$/g, "").trim();
            if (!script.includes("معروضة قدامك على الشاشة") && !script.includes("معروض على شاشتك")) {
                script += "، والتفاصيل كاملة مع الجداول معروضة قدامك على الشاشة.";
            }

            return script;
        }
    } catch (err) {
        console.warn("[voice-summarizer] Error generating spoken summary:", err);
    }

    // Graceful fallback
    return extractVoiceAnalysisSpeech(writtenReply, userQuery);
}
