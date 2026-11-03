/**
 * Utility functions for ARTORO Voice Call and Speech Synthesis.
 */

/**
 * Intelligently extracts human conversational analysis and ARTORO's opinion on a stock
 * from a full financial analysis response.
 * Completely strips technical indicator acronyms (RSI, MACD, EMA), raw formula numbers,
 * markdown tables, English tickers in parentheses, and disclaimers.
 * Produces 2-3 natural spoken Egyptian Arabic sentences (~45-65 words) suitable for a phone call.
 */
export function extractVoiceAnalysisSpeech(replyText: string, userQuery: string = ""): string {
    if (!replyText) {
        return "تمام يا فندم، تم تحديث بيانات السهم والتحليل على شاشتك.";
    }

    const text = replyText;

    // 1. Look for explicit opinion/verdict sections first
    const opinionPatterns = [
        /(?:💡\s*)?(?:الرأي الفني وخلاصة أرتورو|الرأي الفني|خلاصة أرتورو|خلاصة التحليل|النظرة الفنية|التوصية الفنية|توصية أرتورو|رأي أرتورو|الخلاصة|التقييم الفني)[:\s*]+([^\n]+(?:\n[^\n]+){0,2})/i,
        /(?:🎯\s*)?(?:الرأي|التقييم|النصيحة|التوصية)[:\s*]+([^\n]+(?:\n[^\n]+)?)/i,
    ];

    let extractedOpinion = "";
    for (const pat of opinionPatterns) {
        const m = text.match(pat);
        if (m && m[1]) {
            extractedOpinion = m[1].trim();
            break;
        }
    }

    // 2. Look for stock situation / accumulation
    const accumMatch = text.match(/(?:حركة السيولة والتجميع|درجة التجميع|وضع السيولة|حالة السهم)[:\s*]+([^\n]+)/i);
    const accumText = accumMatch && accumMatch[1] ? accumMatch[1].trim() : "";

    // 3. Look for target / support levels if opinion is short
    let levelsText = "";
    const supportMatch = text.match(/(?:الدعم الأول|الدعم الرئيسي)[:\s*]+([0-9.]+\s*(?:ج\.م\.?|جم|جنيه)?)/i);
    const targetMatch = text.match(/(?:المقاومة الأولى|المستهدف|المقاومة الرئيسية)[:\s*]+([0-9.]+\s*(?:ج\.م\.?|جم|جنيه)?)/i);
    if (supportMatch && targetMatch) {
        levelsText = `مستوى الدعم عند ${supportMatch[1]} والمقاومة المستهدفة ${targetMatch[1]}`;
    }

    let candidate = "";
    if (extractedOpinion) {
        if (accumText && !extractedOpinion.includes(accumText)) {
            candidate = `${accumText}. ${extractedOpinion}`;
        } else {
            candidate = extractedOpinion;
        }
    } else if (accumText) {
        candidate = levelsText ? `${accumText}. ${levelsText}.` : accumText;
    } else {
        // Fallback: Scan non-indicator lines and reject technical noise
        const lines = text.split("\n");
        const cleanLines: string[] = [];
        for (const line of lines) {
            const l = line.trim();
            if (!l || l.startsWith("|") || l.startsWith("#") || l.startsWith("⚠️") || l.startsWith("تنبيه:") || l.startsWith("ملاحظة:")) {
                continue;
            }
            if (/\b(RSI|MACD|EMA|SMA|P\/E|ATR|Bollinger)\b/i.test(l)) {
                continue;
            }
            if (/(مؤشر القوة|مؤشر الماكد|متوسط متحرك|مضاعف الربحية|مؤشرات فنية)/i.test(l)) {
                continue;
            }
            cleanLines.push(l);
        }
        candidate = cleanLines.slice(0, 3).join(" ");
    }

    // Clean formatting, english tickers in parentheses e.g. (FWRY), markdown syntax
    candidate = candidate.replace(/\([A-Za-z0-9_.]+\)/g, "");
    candidate = candidate.replace(/[*_#`~]/g, "");
    candidate = candidate.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    candidate = candidate.replace(/[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑]/g, "");
    candidate = candidate.replace(/(?<=\d)\s*(?:ج\.م\.?|جم|EGP)(?=\s|[^\w]|$)/gi, " جنيه");
    candidate = candidate.replace(/\b(?:ج\.م\.?|جم|EGP)\b/gi, " جنيه");
    candidate = candidate.replace(/%/g, " في المية");
    candidate = candidate.replace(/\s+/g, " ").trim();

    // Ensure it smoothly finishes at a sentence boundary around 240 chars
    if (candidate.length > 240) {
        const cut = candidate.slice(0, 240);
        const lastPunct = Math.max(cut.lastIndexOf("."), cut.lastIndexOf("،"), cut.lastIndexOf("!"), cut.lastIndexOf("؟"));
        if (lastPunct > 80) {
            candidate = cut.slice(0, lastPunct + 1);
        } else {
            const lastSpace = cut.lastIndexOf(" ");
            candidate = (lastSpace > 0 ? cut.slice(0, lastSpace) : cut) + ".";
        }
    }

    return candidate.trim();
}

/**
 * Cleans rich markdown chat replies into concise, natural spoken Egyptian Arabic sentences.
 * Strips markdown tables, links, disclaimers, technical syntax, and limits speech to ~35-45 words
 * so audio synthesis is fast (<1.5s) and conversational.
 */
export function cleanVoiceText(rawText: string, maxChars: number = 180): string {
    if (!rawText) return "";

    let text = rawText;

    // 1. Remove markdown tables (| col | col |)
    text = text.replace(/\|[^\n]+\|/g, " ");

    // 2. Remove markdown links [text](url) -> text
    text = text.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");

    // 3. Remove markdown bold, italic, code, headers
    text = text.replace(/#{1,6}\s*/g, "");
    text = text.replace(/[*`_~]/g, "");

    // 4. Strip standard disclaimer paragraphs that should NOT be spoken in a phone call
    text = text.replace(/تنبيه:[\s\S]*$/gi, "");
    text = text.replace(/ملاحظة:[\s\S]*$/gi, "");
    text = text.replace(/هذا التحليل لأغراض[\s\S]*$/gi, "");
    text = text.replace(/منصة EGX BOTS[\s\S]*$/gi, "");
    text = text.replace(/إخلاء مسؤولية:[\s\S]*$/gi, "");

    // 5. Remove emojis and decorative icons
    text = text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    text = text.replace(/[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]/g, "");

    // 6. Natural spoken currency & stock terms without eating preceding digits
    text = text.replace(/(?<=\d)\s*(?:ج\.م\.?|جم|EGP)(?=\s|[^\w]|$)/gi, " جنيه");
    text = text.replace(/\b(?:ج\.م\.?|جم|EGP)\b/gi, " جنيه");
    text = text.replace(/%/g, " في المية ");
    text = text.replace(/\bEGX30\b/gi, " إيجي إكس 30 ");
    text = text.replace(/\bEGX70\b/gi, " إيجي إكس 70 ");
    text = text.replace(/\bP\/E\b/gi, " مضاعف الربحية ");

    // 7. Normalize whitespace
    text = text.replace(/\s+/g, " ").trim();

    // 8. Truncate smoothly at sentence boundary
    if (text.length > maxChars) {
        const cut = text.slice(0, maxChars);
        const lastPunct = Math.max(
            cut.lastIndexOf("."),
            cut.lastIndexOf("،"),
            cut.lastIndexOf("!"),
            cut.lastIndexOf("؟"),
            cut.lastIndexOf("\n")
        );
        if (lastPunct > 50) {
            text = cut.slice(0, lastPunct + 1);
        } else {
            const lastSpace = cut.lastIndexOf(" ");
            text = (lastSpace > 0 ? cut.slice(0, lastSpace) : cut) + "...";
        }
    }

    return text.trim();
}

/**
 * Plays a soft dual-tone synthesizer chime via Web Audio API to indicate connection
 * and pre-unlock browser AudioContext on user interaction.
 */
export function playConnectionChime(): void {
    if (typeof window === "undefined") return;
    try {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        if (ctx.state === "suspended") {
            ctx.resume();
        }

        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(520, now); // C5
        osc.frequency.exponentialRampToValueAtTime(784, now + 0.12); // G5

        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.15, now + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now);
        osc.stop(now + 0.26);
    } catch (e) {
        // Non-blocking fallback
    }
}
