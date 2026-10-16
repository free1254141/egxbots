import { evidenceRows, type AgenticEvidence } from "./agentic-publication";
import { todayInCairo } from "./cairo-date";

/** Review published claims only. These suggestions never classify a user request
 * and never enter the deterministic rejection reasons. */
export function advisoryMarketMeaning(reply: string, evidence: AgenticEvidence[], today = todayInCairo()): string[] {
    const latest = new Map<string, any>();
    for (const record of evidence.filter(e => e.availability !== "error")) for (const row of evidenceRows(record.data)) {
        if (!row.symbol) continue;
        const previous = latest.get(row.symbol);
        if (!previous || String(row.date || "") >= String(previous.date || "")) latest.set(row.symbol, {...previous, ...row});
    }
    const notes = new Set<string>();
    let section: string | null = latest.size === 1 ? [...latest.keys()][0] : null;
    for (const line of reply.split("\n")) {
        const named = [...latest.keys()].filter(symbol => new RegExp(`\\b${symbol}\\b`, "i").test(line));
        if (named.length === 1) section = named[0];
        if (named.length > 1) section = null;
        for (const clause of line.split(/[،,؛.!?]/)) {
            const row = section ? latest.get(section) : null;
            const negated = /(?:[وف]?لا\s+(?:يثبت|تثبت|يعني|تعني|يعد|تعد|يمثل|تمثل|يدل|تدل|يؤكد|تؤكد|إثبات|اثبات|دليل)|[وف]?ليس(?:ت)?|[وفب]?دون\s+(?:تأكيد|دليل|اكتمال|إثبات|اثبات)|بلا\s+(?:دليل|تأكيد|إثبات|اثبات)|غير\s+(?:مؤكد|مثبت|نهائي)|not\s+(?:proof|confirmed|final))/i.test(clause);
            if (row && String(row.date || "").slice(0,10) === today && row.session_complete !== true && row.final_close_confirmed !== true
                && /إغلاق|اغلاق|closing\s+price|final\s+close/i.test(clause) && !negated)
                notes.add(`سعر ${section} بتاريخ اليوم هو آخر سعر/لقطة متاحة للجلسة؛ لا تصفه بإغلاق نهائي دون دليل انتهاء الجلسة. احتفظ بالسعر والتاريخ.`);
            const rsi = row?.rsi_14 ?? row?.rsi;
            if (typeof rsi === "number" && rsi < 30 && /RSI|تشبع|ذروة/i.test(clause) && /(?:قريب|قرب|يقترب|اقترب|near).{0,30}(?:تشبع|ذروة|oversold)/i.test(clause) && !negated)
                notes.add(`RSI للسهم ${section} أقل من 30، فهو داخل النطاق التقليدي للتشبع البيعي، لا مجرد قريب منه؛ لا يثبت انعكاساً أو فرصة شراء بمفرده.`);
            if (row && Number.isFinite(row.macd) && Number.isFinite(row.macd_signal) && row.macd < 0 && row.macd > row.macd_signal
                && /MACD/i.test(clause) && /(?:تحت|أدنى|اقل|أقل|below).{0,20}(?:إشار|اشار|signal)/i.test(clause) && !negated)
                notes.add(`MACD للسهم ${section} سالب بالنسبة إلى الصفر لكنه أعلى خط إشارته. افصل العلاقة بالصفر عن العلاقة بخط الإشارة، ولا تستنتج تقاطعاً جديداً من لقطة واحدة.`);
            if (row && /استقرار|مستقر|ثبات|ثابت|stabil/i.test(clause) && /(?:تساو|متساو|يساوي|مساو|equal)/i.test(clause) && !negated)
                notes.add(`تساوي قيم ${section} في اللقطة الحالية لا يثبت ثباتها عبر الزمن. صف التعادل الحالي فقط ما لم توجد سلسلة مؤرخة تثبت الاستقرار.`);
            if (row && /(?:تجميع|accumulation)/i.test(clause) && /مؤسس|institution/i.test(clause) && !negated)
                notes.add(`درجة التجميع أو وايكوف للسهم ${section} إشارة نموذج وليست إثباتاً لشراء مؤسسات أو هوية المتداولين. صغ الاستنتاج كاحتمال وحدوده، دون حذف الدرجة المدعومة.`);
        }
    }
    for (const record of evidence.filter(e => e.availability !== "error")) {
        const metrics = record.data?.strategy_metrics;
        if (!Array.isArray(metrics) || metrics.length < 2) continue;
        const valid = metrics.filter(m => typeof m.maxDrawdownPct === "number" && Number.isFinite(m.maxDrawdownPct));
        const minimum = Math.min(...valid.map(m => Math.abs(m.maxDrawdownPct)));
        for (const clause of reply.split(/[\n،,؛.!?]/)) {
            if (!/(?:أقل|اقل|الأقل|الاقل|lowest|least).{0,35}(?:هبوط|drawdown)|(?:هبوط|drawdown).{0,35}(?:أقل|اقل|lowest|least)/i.test(clause)) continue;
            if (/(?:ليس|ليست|لا\s+يعني|not)/i.test(clause)) continue;
            const named = valid.filter(m => clause.includes(m.strategy_id) || (m.strategy_name && clause.includes(m.strategy_name)));
            if (named.length === 1 && Math.abs(named[0].maxDrawdownPct) > minimum + 0.02)
                notes.add("راجع ترتيب أقصى الهبوط: الأصغر في مقدار maxDrawdownPct هو الأقل هبوطاً في نفس الاختبار؛ لا ترتبه بالعائد أو بوصف عام للمخاطرة، واذكر التعادل عند تساويه.");
        }
    }
    return [...notes];
}

export const advisoryObservedChatClaims = advisoryMarketMeaning;
