/** Explain verified stock snapshots without dumping raw indicator records. */
type StockSnapshot = Record<string, any>;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const number = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 2 });

export function renderStockRecovery(rows: StockSnapshot[]): string {
    const snapshots = new Map<string, StockSnapshot>();
    for (const row of rows) {
        if (!row.symbol || !finite(row.close ?? row.current_price)) continue;
        const date = String(row.date || row.current_date || "").slice(0, 10);
        const old = snapshots.get(row.symbol);
        const oldDate = String(old?.date || old?.current_date || "").slice(0, 10);
        if (!old || date > oldDate) snapshots.set(row.symbol, { ...row });
        else if (date === oldDate) snapshots.set(row.symbol, { ...old, ...row });
    }
    if (!snapshots.size) return "";
    const lines: string[] = [];
    for (const row of [...snapshots.values()].slice(0, 10)) {
        const close = row.close ?? row.current_price;
        const date = String(row.date || row.current_date || "").slice(0, 10);
        lines.push(`**${row.name_ar || row.name || row.symbol}${row.name_ar || row.name ? ` (${row.symbol})` : ""}** — آخر إغلاق متاح ${number(close)} جنيه${date ? ` بتاريخ ${date}` : ""}.`);
        const comments: string[] = [];
        const indicatorsDate = String(row.indicators_date || date).slice(0, 10);
        const indicatorsUsable = !row.indicators_stale && row.indicators_available !== false && indicatorsDate === date;
        if (indicatorsUsable) {
            if (finite(row.ema_50) && finite(row.ema_200)) comments.push(close > row.ema_50 && close > row.ema_200
                ? "السعر فوق متوسطاته القصيرة والطويلة؛ موقعه الحالي أقوى، لكنه وحده لا يثبت استمرار الصعود."
                : close < row.ema_50 && close < row.ema_200
                    ? "السعر تحت متوسطاته القصيرة والطويلة؛ الصورة الحالية ضعيفة وتحتاج تأكيدًا قبل الدخول."
                    : "السعر بين متوسطاته القصيرة والطويلة؛ الصورة مختلطة وتحتاج تأكيد اتجاه.");
            if (finite(row.rsi_14)) comments.push(row.rsi_14 < 30
                ? `القوة النسبية ${number(row.rsi_14)} في منطقة التشبع البيعي؛ الارتداد محتمل، لكن انخفاض المؤشر لا يثبت أن البيع انتهى.`
                : row.rsi_14 > 70
                    ? `القوة النسبية ${number(row.rsi_14)} في منطقة التشبع الشرائي؛ راقب خطر التراجع بدل مطاردة الحركة.`
                    : `القوة النسبية ${number(row.rsi_14)} بين منطقتي التشبع، فلا تعطي وحدها إشارة شراء أو بيع.`);
            if (finite(row.macd) && finite(row.macd_signal)) comments.push(row.macd < row.macd_signal
                ? "الزخم الحالي ضعيف: MACD تحت خط إشارته، وليس ذلك دليلًا على حدوث تقاطع جديد."
                : row.macd > row.macd_signal
                    ? "MACD فوق خط إشارته؛ العلاقة الحالية تدعم الزخم، لكنها لا تثبت تقاطعًا جديدًا أو صعودًا مضمونًا."
                    : "MACD يساوي خط إشارته؛ لا توجد أفضلية زخم واضحة من هذه القراءة.");
        } else comments.push("المؤشرات لا تطابق تاريخ السعر المتاح؛ لذلك لا أخلطها معه في الحكم الفني.");
        // Levels describe their own dated snapshot, not a replacement live quote.
        if (finite(row.support) && row.support < close) comments.push(`الدعم عند ${number(row.support)}: كسره يضعف السيناريو.`);
        if (finite(row.resistance) && row.resistance > close) comments.push(`المقاومة عند ${number(row.resistance)}: تجاوزها والثبات فوقها شرط لتأكيد تحسن الحركة.`);
        if (!comments.length) comments.push("السعر وحده لا يكفي لترجيح الدخول؛ يلزم تأكيد الزخم والمستويات الفنية.");
        lines.push(comments.join(" "), "");
    }
    lines.push("الخلاصة: اربط قرارك بتأكيد الحركة وحدود المخاطرة؛ قرب الدعم أو التشبع البيعي وحده لا يكفي للدخول. هذه إغلاقات مخزنة وليست أسعارًا لحظية، والمستويات سيناريوهات فنية غير مضمونة.");
    return lines.join("\n");
}
