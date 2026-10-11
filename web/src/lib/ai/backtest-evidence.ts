import type { FactRecord } from "./facts";

/** Shared field identity for validation and evidence-only recovery. */
export const BACKTEST_METRICS: Array<{ key: string; field: FactRecord["field"]; unit: FactRecord["unit"]; label: string; pattern: RegExp }> = [
    {key:"maxDrawdownPct",field:"backtest_drawdown_pct",unit:"percent",label:"أقصى هبوط %",pattern:/هبوط|drawdown/i},
    {key:"winRatePct",field:"backtest_win_rate_pct",unit:"percent",label:"نسبة الصفقات الرابحة %",pattern:/فوز|نجاح|win.?rate|صفقات.*رابح|رابح/i},
    {key:"profitFactor",field:"backtest_profit_factor",unit:"ratio",label:"معامل الربح",pattern:/معامل.*ربح|profit.?factor/i},
    {key:"closedTrades",field:"backtest_closed_trades",unit:"count",label:"الصفقات المغلقة",pattern:/(?:عدد|إجمالي|مجموع)?\s*صفقات(?!.*(?:رابح|شراء|بيع))|trades/i},
    {key:"finalEquity",field:"backtest_final_equity",unit:"egp",label:"رأس المال النهائي",pattern:/قيمة.*نها(?:ئ|ي)|رأس.*مال.*نها(?:ئ|ي)|رصيد.*نها(?:ئ|ي)|equity/i},
    {key:"totalReturnPct",field:"backtest_return_pct",unit:"percent",label:"العائد التراكمي %",pattern:/عائد|total.?return|return/i},
];

export function renderBacktestEvidence(data: any): string | null {
    if (data?.status !== "success" || !data.symbol || !Array.isArray(data.strategy_metrics) || !data.strategy_metrics.length) return null;
    const metrics = data.strategy_metrics.filter((m: any) => m.strategy_id && BACKTEST_METRICS.every(f => Number.isFinite(m[f.key])));
    if (!metrics.length) return null;
    const format = (value: number) => value.toFixed(2);
    const lines = [`نتيجة الاختبار التاريخي على ${data.symbol}:`,
        `الفترة: ${data.start_date || "بداية الفترة المتاحة"} إلى ${data.date || "آخر جلسة متاحة"}؛ ${data.candle_count ?? "غير محدد"} شمعة يومية.`,
        "| الاستراتيجية | نسبة الصفقات الرابحة % | العائد التراكمي % | أقصى هبوط % | الصفقات المغلقة | معامل الربح | رأس المال النهائي |",
        "|---|---:|---:|---:|---:|---:|---:|"];
    for (const m of metrics) lines.push(`| ${m.strategy_name || m.strategy_id} | ${format(m.winRatePct)} | ${format(m.totalReturnPct)} | ${format(m.maxDrawdownPct)} | ${m.closedTrades} | ${format(m.profitFactor)} | ${format(m.finalEquity)} |`);
    if ([data.assumptions?.initialCapital, data.assumptions?.commissionBps, data.assumptions?.slippageBps].every(Number.isFinite)) lines.push(`رأس المال الافتراضي ${data.assumptions.initialCapital} جنيه؛ العمولة ${data.assumptions.commissionBps} نقطة أساس والانزلاق ${data.assumptions.slippageBps} نقطة أساس.`);
    lines.push("نسبة النجاح محسوبة من الصفقات المغلقة، والعائد تاريخي وليس ضمانًا لأداء قادم. تعديل الأسعار للأحداث الرأسمالية غير متحقق منه.");
    if (metrics.some((m: any) => m.closedTrades < 10)) lines.push("عينة الصفقات المغلقة صغيرة؛ لا تكفي لتقدير نجاح موثوق.");
    return lines.join("\n");
}
