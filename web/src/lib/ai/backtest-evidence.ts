import type { FactRecord } from "./facts";

/** Shared field identity for validation and evidence-only recovery. */
export const BACKTEST_METRICS: Array<{ key: string; field: FactRecord["field"]; unit: FactRecord["unit"]; label: string; pattern: RegExp }> = [
    {key:"maxDrawdownPct",field:"backtest_drawdown_pct",unit:"percent",label:"أقصى هبوط %",pattern:/(?:أقصى|اقصى|أكبر|اكبر|متوسط|وسيط)\s+(?:هبوط|تراجع)|(?:هبوط|تراجع)\s+ل?رأس\s+المال|(?:هبوط|تراجع)(?=[^\n.!؟؛]*من قمة[^\n.!؟؛]*قاع)|drawdown|^\s*(?:ال)?هبوط\s*[%٪]?\s*$/i},
    {key:"winRatePct",field:"backtest_win_rate_pct",unit:"percent",label:"نسبة الصفقات الرابحة %",pattern:/فوز|نجاح|win.?rate|صفقات.*رابح|رابح/i},
    {key:"profitFactor",field:"backtest_profit_factor",unit:"ratio",label:"معامل الربح",pattern:/معامل.*ربح|profit.?factor/i},
    {key:"closedTrades",field:"backtest_closed_trades",unit:"count",label:"الصفقات المغلقة",pattern:/(?:عدد|إجمالي|مجموع)?\s*صفقات(?!.*(?:رابح|شراء|بيع))|trades/i},
    {key:"finalEquity",field:"backtest_final_equity",unit:"egp",label:"رأس المال النهائي",pattern:/قيمة.*نها(?:ئ|ي)|رأس.*مال.*نها(?:ئ|ي)|رصيد.*نها(?:ئ|ي)|equity/i},
    {key:"totalReturnPct",field:"backtest_return_pct",unit:"percent",label:"العائد التراكمي %",pattern:/عائد|total.?return|return/i},
];

export function renderBacktestEvidence(data: any): string | null {
    if (data?.status !== "success" || !data.symbol || !Array.isArray(data.strategy_metrics) || !data.strategy_metrics.length) return null;
    const metrics = data.strategy_metrics.filter((m: any) => m.strategy_id && BACKTEST_METRICS.every(f => Number.isFinite(m[f.key]) || (f.key === "profitFactor" && m.profitFactor === null && m.closedTrades === 0)));
    if (!metrics.length) return null;
    const format = (value: number) => value.toFixed(2);
    const lines = [`نتيجة الاختبار التاريخي على ${data.symbol}:`,
        `الفترة: ${data.start_date || "بداية الفترة المتاحة"} إلى ${data.date || "آخر جلسة متاحة"}؛ ${data.candle_count ?? "غير محدد"} شمعة يومية.`,
        "| الاستراتيجية | نسبة الصفقات الرابحة % | العائد التراكمي % | أقصى هبوط % | الصفقات المغلقة | معامل الربح | رأس المال النهائي |",
        "|---|---:|---:|---:|---:|---:|---:|"];
    for (const m of metrics) lines.push(`| ${m.strategy_name || m.strategy_id} | ${format(m.winRatePct)} | ${format(m.totalReturnPct)} | ${format(m.maxDrawdownPct)} | ${m.closedTrades} | ${m.profitFactor === null ? "غير متاح (لا صفقات مغلقة)" : format(m.profitFactor)} | ${format(m.finalEquity)} |`);
    if ([data.assumptions?.initialCapital, data.assumptions?.commissionBps, data.assumptions?.slippageBps].every(Number.isFinite)) lines.push(`رأس المال الافتراضي ${data.assumptions.initialCapital} جنيه؛ العمولة ${data.assumptions.commissionBps} نقطة أساس والانزلاق ${data.assumptions.slippageBps} نقطة أساس.`);
    lines.push("نسبة النجاح محسوبة من الصفقات المغلقة، والعائد تاريخي وليس ضمانًا لأداء قادم. تعديل الأسعار للأحداث الرأسمالية غير متحقق منه.");
    if (metrics.some((m: any) => m.closedTrades < 10)) lines.push("عينة الصفقات المغلقة صغيرة؛ لا تكفي لتقدير نجاح موثوق.");
    return lines.join("\n");
}

/** Targeted, non-blocking correction of a mislabeled backtest statistic. */
export function advisoryBacktestMetricMeaning(reply: string, hasBacktest: boolean): string[] {
    if (!hasBacktest) return [];
    const clauses = reply.split(/[\n،؛.!?]/);
    const mislabeled = clauses.some(clause =>
        /(?:هبوط|drawdown)\s*(?:ال)?(?:وسيط|متوسط|median|average|mean)|(?:وسيط|متوسط)\s*(?:ال)?هبوط|(?:median|average|mean)\s*drawdown/i.test(clause)
        && /[0-9٠-٩۰-۹]/.test(clause)
        && !/(?:ليس|ليست|لا يمثل|لا يُمثل|غير متاح|غير محسوب|not|unavailable)/i.test(clause));
    return mislabeled ? ["مقياس الهبوط في الاختبار هو أقصى هبوط (maxDrawdownPct)، وليس متوسطاً أو وسيطاً. صحّح وصفه مع الاحتفاظ بالرقم وباقي الإجابة."] : [];
}
