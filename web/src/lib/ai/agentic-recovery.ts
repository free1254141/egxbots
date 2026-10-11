import type { VisionContext } from "./types";
import { evidenceRows, type AgenticEvidence } from "./agentic-publication";

const displayNumber = (value: unknown) => typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "غير ظاهر";
export function safePortfolioImageReply(vision: VisionContext | null, request: string): string | null {
    if (!vision || vision.image_type !== "portfolio" || !vision.symbols?.length) return null;
    const symbols = vision.symbols;
    const stocks = symbols.filter(row => row.asset_type === "stock").length;
    const funds = symbols.filter(row => row.asset_type === "fund").length;
    const unknown = symbols.filter(row => !row.asset_type || row.asset_type === "unknown").length;
    const rows = symbols.map(({ symbol, source_image_index, asset_type, visible_values: v }) => {
        const returnPct = v.return_pct ?? (v.profit_loss != null ? v.change_pct : null);
        return `| ${source_image_index ? `صورة ${source_image_index}` : "—"} | ${symbol} | ${asset_type === "fund" ? "صندوق" : asset_type === "stock" ? "سهم" : "غير محدد"} | ${displayNumber(v.quantity)} | ${displayNumber(v.average_price)} | ${displayNumber(v.price)} | ${displayNumber(v.market_value)} | ${displayNumber(v.cost_basis)} | ${displayNumber(v.profit_loss)} | ${displayNumber(v.cash_dividends ?? null)} | ${displayNumber(returnPct)}${returnPct == null ? "" : "%"} |`;
    });
    const missing = symbols.filter(row => row.visible_values.quantity == null || row.visible_values.average_price == null)
        .map(row => row.symbol);
    const lines = [`قرأت ${vision.symbols.some(row => row.source_image_index) ? "الصور المرفقة" : "الصورة"}. هذه قراءة مباشرة للقيم التي أمكن استخراجها، من دون استنتاج أسعار أو أوزان غير ظاهرة:`,
        `الرموز المقروءة: ${symbols.length}${stocks ? ` أسهم: ${stocks}` : ""}${funds ? `، صناديق: ${funds}` : ""}${unknown ? `، وتصنيف غير مؤكد: ${unknown}` : ""}.`,
        "| المصدر | الرمز | النوع | الكمية | متوسط الشراء | السعر الظاهر | قيمة المركز | التكلفة | ربح/خسارة | توزيعات نقدية | العائد |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|", ...rows];
    if (missing.length) lines.push(`الكمية أو متوسط الشراء غير ظاهرين لبعض المراكز (${missing.join("، ")})؛ لذلك لا أستنتج أوزانها أو أسجلها كمراكز مؤكدة.`);
    lines.push("لا تكفي الرموز وحدها لإثبات القطاعات، كما أن ظهور مركز مصنف صندوقاً لا يحدد إن كان نشط الإدارة أو يثبت الحاجة لإضافة صندوق آخر.");
    if (/صناديق|صندوق|نشط|اداره|إدارة/.test(request)) lines.push("للمقارنة النوعية بين صندوق نشط وصندوق يتبع مؤشراً، راجع رسوم الإدارة، سياسة الاستثمار، والأفق الزمني؛ لا تحسم الصورة وحدها قرار الإضافة أو البيع.");
    return lines.join("\n");
}
export function safeImageEvidenceReply(vision: VisionContext | null, request: string): string | null {
    if (!vision) return null;
    if (vision.image_type === "portfolio") return safePortfolioImageReply(vision, request);
    const lines = [`قرأت الصورة${vision.symbols.some(item => item.source_image_index) ? "/الصور المرفقة" : ""}. هذه البيانات التي استخرجتها الرؤية، مع إبقاء كل قيمة مرتبطة بمصدرها:`];
    if (vision.symbols.length) {
        lines.push("| المصدر | الرمز | السعر | التغير % | الكمية |", "|---|---|---:|---:|---:|");
        for (const item of vision.symbols) lines.push(`| ${item.source_image_index ? `صورة ${item.source_image_index}` : "—"} | ${item.symbol} | ${displayNumber(item.visible_values.price)} | ${displayNumber(item.visible_values.change_pct)} | ${displayNumber(item.visible_values.quantity)} |`);
    }
    const observations = vision.technical_observations.filter(item => item.value !== null);
    if (observations.length) {
        lines.push("المؤشرات والملاحظات الظاهرة:");
        observations.forEach(item => lines.push(`• ${item.symbol}: ${item.indicator} = ${displayNumber(item.value)}${item.meaning ? ` — ${item.meaning}` : ""}`));
    }
    const depth = vision.market_depth;
    if (depth.total_bid != null || depth.total_ask != null || depth.spread != null) lines.push(`عمق السوق الظاهر: طلب ${displayNumber(depth.total_bid)}، عرض ${displayNumber(depth.total_ask)}، فرق ${displayNumber(depth.spread)}.`);
    if (vision.user_relevant_summary) lines.push(`ملاحظة الرؤية: ${vision.user_relevant_summary}`);
    if (vision.uncertainties.length) lines.push(`قيم غير محسومة: ${vision.uncertainties.join("؛ ")}.`);
    if (lines.length === 1) lines.push("لم تُستخرج أرقام مؤكدة من الصورة؛ وضّح الجزء المطلوب أو أرسل نسخة أوضح.");
    return lines.join("\n");
}
export function fallbackEvidence(evidence: AgenticEvidence[], activeSymbols?: string[]) {
    const matched = evidence.filter(e => e.data?.persisted === true || (e.data?.status === "success"
        && ["screen_stocks", "analyze_portfolio_risk", "calculate_position", "get_comparison", "compare_strategies_history", "get_stock", "get_stock_levels", "get_market", "get_news", "get_recommendations"].includes(e.tool) && e.availability !== "error")
        || (e.tool === "get_comparison" && e.availability !== "error" && evidenceRows(e.data).length > 0));
    if (activeSymbols && activeSymbols.length > 0) {
        const symbolSet = new Set(activeSymbols.map(s => String(s).toUpperCase()));
        const scoped = matched.filter(e => (e.symbols || []).some(s => symbolSet.has(String(s).toUpperCase())));
        return scoped.length > 0 ? scoped : matched.filter(e => e.data?.persisted === true);
    }
    return matched;
}
