/** Presentation only; never changes intent, symbols, numerical values or tools. */
const labels: Record<string, string> = {
    stale: "قديمة", price_to_book: "مضاعف الدفترية", revenue_growth_pct: "نمو الإيرادات",
    financial_period: "الفترة المالية", snapshot_updated_at: "تاريخ تحديث اللقطة",
    industry: "الصناعة", sector: "القطاع", classification_basis: "أساس التصنيف",
    quote_time: "وقت آخر صفقة", fetched_at: "وقت الجلب", fetched_at_cairo: "وقت الجلب بالقاهرة",
    king_ai_score: "تقييم KING", egx_ai_score: "تقييم EGX",
    accumulation_score: "درجة التجميع", distribution_score: "درجة التوزيع",
    wyckoff_phase: "مرحلة وايكوف", r_vol: "الحجم النسبي",
    momentum_and_volume: "الزخم والنشاط النسبي", top_gainers: "الأكثر ارتفاعاً",
    top_losers: "الأكثر انخفاضاً", rsi_oversold: "التشبع البيعي",
    macd_cross: "تقاطع MACD", smart_money_flow: "التجميع والسيولة",
};
const pattern = new RegExp(`\\b(?:${Object.keys(labels).join("|")})\\b`, "g");
export function presentReplyLabels(reply: string): string {
    return reply.replace(pattern, key => labels[key]);
}
