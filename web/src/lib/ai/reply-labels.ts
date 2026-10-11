/** Presentation only; never changes intent, symbols, numerical values or tools. */
const labels: Record<string, string> = {
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
