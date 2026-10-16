import type { AgenticEvidence } from './agentic-publication';
import { evidenceRows } from './agentic-publication';
import { normalizeEvidenceNumbers } from './numeric-evidence';

/** Scoped suggestions for the existing bounded repair pass; never an answer veto. */
export function advisoryFactRelations(reply: string, evidence: AgenticEvidence[]): string[] {
    const rows = evidence.filter(e => e.availability !== 'error').flatMap(e => evidenceRows(e.data));
    const latest = new Map<string, any>();
    for (const row of rows) {
        if (!row.symbol) continue;
        const previous = latest.get(row.symbol);
        const date = String(row.current_date || row.date || '').slice(0, 10);
        const previousDate = String(previous?.current_date || previous?.date || '').slice(0, 10);
        if (!previous || date >= previousDate) latest.set(row.symbol, date === previousDate ? {...previous, ...row} : {...row});
    }
    const symbols = [...latest.keys()];
    let owner: string | null = symbols.length === 1 ? symbols[0] : null;
    const findings: string[] = [];
    const number = (value: unknown) => {
        if (value == null || typeof value === 'boolean' || String(value).trim() === '') return null;
        const parsed = Number(normalizeEvidenceNumbers(String(value)));
        return Number.isFinite(parsed) ? parsed : null;
    };
    const named = (text: string) => symbols.filter(s => new RegExp(`\\b${s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(text));
    const add = (quote: string, correction: string) => findings.push(`راجع الجملة «${quote.trim().slice(0, 220)}»: ${correction} احتفظ بباقي الإجابة.`);
    for (const raw of normalizeEvidenceNumbers(reply).replace(/[*_`]/g, '').split(/\n|[؛!?؟]\s*/)) {
        if (raw.trim().startsWith('|')) continue;
        const names = named(raw);
        if (names.length === 1) owner = names[0];
        else if (names.length > 1) owner = null;
        for (const clause of raw.split(/[،;]|\.(?=\s|$)/)) {
            const local = named(clause);
            const subject = local.length === 1 ? local[0] : local.length > 1
                ? /(?:أحدث|أقدم)/.test(clause) ? local.sort((a, b) => clause.toUpperCase().indexOf(a) - clause.toUpperCase().indexOf(b))[0] : null
                : owner;
            // Conditional/negated interpretations are not asserted observations.
            const uncertain = /(?:^|[\s،؛:])(?:[وف]?لا|[وف]?ليس(?:ت)?|مش|[وف]?لم|غير|[وفب]?دون|بلا|لو|إذا|اذا|هل|قد|ربما|احتمال(?:ية)?|لازم\s+نتحقق)(?=$|[\s،؛:])/.test(clause);
            if (!subject || uncertain) continue;
            const row = latest.get(subject);
            const close = number(row.close ?? row.current_price), support = number(row.support), resistance = number(row.resistance);
            const closer = /أقرب\s*(?:نسبياً\s*)?(?:(?:إلى|الى)\s*|ل)?\s*(?:ال|ل)?(دعم|مقاوم[ةه])/.exec(clause);
            if (closer && close !== null && support !== null && resistance !== null) {
                const ds = Math.abs(close-support), dr = Math.abs(resistance-close);
                if ((closer[1] === 'دعم' && dr < ds-1e-8) || (closer[1] !== 'دعم' && ds < dr-1e-8))
                    add(clause, `المسافة من الإغلاق ${close} للدعم ${support} هي ${ds.toFixed(4)}، وللمقاومة ${resistance} هي ${dr.toFixed(4)}؛ السعر أقرب ${ds < dr ? 'للدعم' : 'للمقاومة'} حسابياً.`);
            }
            const macd = number(row.macd), signal = number(row.macd_signal);
            const relation = /MACD\s*(?:(?:حالي[ًاا]*|هو|حالياً)\s*)?(فوق|تحت|أعلى\s+من|أدنى\s+من|اعلى\s+من|ادنى\s+من|يساوي|مساو[ٍي]*)\s*(?:خط\s*)?(?:ال)?(?:إشار|اشار|signal)/i.exec(clause);
            if (relation && macd !== null && signal !== null) {
                const expected = macd > signal ? 'فوق' : macd < signal ? 'تحت' : 'يساوي';
                const asserted = /فوق|أعلى|اعلى/.test(relation[1]) ? 'فوق' : /تحت|أدنى|ادنى/.test(relation[1]) ? 'تحت' : 'يساوي';
                if (asserted !== expected) add(clause, `MACD ${expected} الإشارة حسابياً (${macd} مقابل ${signal})؛ الإشارة السالبة لا تعكس ترتيب الأرقام.`);
            }
            const entry = number(row.entry_price), current = number(row.current_price ?? row.close);
            const pathClaim = /(?:عاد|رجع|رجوع)\s*(?:(?:إلى|الى)\s*(?:سعر\s*|نقطة\s*)?الدخول|ل(?:سعر\s*الدخول|نقطة\s*الدخول|لدخول))|لم\s+يتحرك|(?:ثابت|استقر)\s*(?:طوال|طول)\s*الفترة/.test(clause);
            const hasHistory = rows.some(r => r.symbol === subject && [r.history, r.price_history, r.prices].some(v => Array.isArray(v) && v.length > 2));
            if (pathClaim && entry !== null && current !== null && entry === current && !hasHistory)
                add(clause, 'تساوي آخر سعر وسعر الدخول يثبت عائداً حالياً صفراً فقط؛ لا يثبت أنه عاد أو بقي ثابتاً دون مسار أسعار موثق.');
            if (/(?:شراء|نشاط|تجميع|دخول|تدفق|تدفقات).{0,25}(?:مؤسس|صناديق)|(?:المؤسسات|الصناديق).{0,25}(?:تشتري|اشترت|بتشتري|شراء|تدخل)/.test(clause)
                && !rows.some(r => r.symbol === subject && (r.institutional_ownership != null || r.institutional_flows != null)))
                add(clause, 'مؤشرات التجميع والزخم لا تثبت شراء المؤسسات؛ افصل النمط الفني عن ملكية أو تدفقات مؤسسية غير متاحة.');
            const other = /(?:أحدث|أقدم).{0,40}\b([A-Z]{2,10})\b/i.exec(clause);
            if (other && latest.has(other[1].toUpperCase()) && /(?:سعر|إغلاق|اغلاق|جلسة|تاريخ)/.test(clause)) {
                const firstDate = String(row.current_date || row.date || '').slice(0, 10);
                const peer = latest.get(other[1].toUpperCase());
                const secondDate = String(peer.current_date || peer.date || '').slice(0, 10);
                if (/^\d{4}-\d{2}-\d{2}$/.test(firstDate) && /^\d{4}-\d{2}-\d{2}$/.test(secondDate)) {
                    const newer = /أحدث/.test(other[0]);
                    if (newer ? firstDate <= secondDate : firstDate >= secondDate)
                        add(clause, `تاريخ آخر سعر ${subject} هو ${firstDate}، وتاريخ ${other[1].toUpperCase()} هو ${secondDate}؛ قارن التاريخين كما هما دون تغيير تاريخ نشر التوصية.`);
                }
            }
            const strategies = Array.isArray(row.strategy_metrics) ? row.strategy_metrics : [];
            if (/(?:الأقل|أقل)\s*(?:في\s*)?هبوط|least\s*drawdown/i.test(clause) && strategies.length > 1) {
                const metrics = strategies.map((m: any) => ({...m, loss: number(m.maxDrawdownPct)})).filter((m: any) => m.loss !== null);
                const selected = metrics.filter((m: any) => [m.strategy_id, m.strategy_name].some(n => n && clause.toLowerCase().includes(String(n).toLowerCase())));
                if (selected.length === 1 && metrics.some((m: any) => Math.abs(m.loss) < Math.abs(selected[0].loss))) {
                    const minimum = Math.min(...metrics.map((m: any) => Math.abs(m.loss)));
                    const winners = metrics.filter((m: any) => Math.abs(m.loss) === minimum).map((m: any) => m.strategy_name || m.strategy_id);
                    add(clause, `الأقل هبوطاً ${winners.join(' و ')} بمقدار ${minimum}%؛ قارن مقدار الخسارة، واحتفظ بالتعادل إن وجد.`);
                }
            }
        }
    }
    return [...new Set(findings)];
}
