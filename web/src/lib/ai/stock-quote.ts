/** Prices and indicators are refreshed independently. Never date old indicators
 * as a new quote, or use the indicator snapshot as proof of the newest close. */
export async function reconcileStockQuote(client: any, symbol: string, snapshot: any) {
    const { data } = await client.from("stock_prices")
        .select("date,close").eq("exchange", "EGX").eq("symbol", symbol)
        .order("date", { ascending: false }).limit(2);
    const prices = (data || []).filter((p: any) => p.date && p.close != null
        && Number.isFinite(Number(p.close)) && Number(p.close) > 0);
    const newest = prices[0];
    if (!newest || (snapshot?.date && String(newest.date) < String(snapshot.date)))
        return snapshot ? { ...snapshot, quote_source: "stock_technical_indicators", indicators_date: snapshot.date, indicators_stale: false } : null;
    const close = Number(newest.close);
    const stale = Boolean(snapshot && (String(snapshot.date) !== String(newest.date)
        || snapshot.close == null || Math.abs(Number(snapshot.close) - close) > 1e-8));
    const previous = prices[1];
    const change = previous ? (close / Number(previous.close) - 1) * 100
        : !stale ? snapshot?.change_pct ?? null : null;
    const result = { ...(snapshot || {}), date: newest.date, close, change_pct: change,
        quote_source: "stock_prices", indicators_date: snapshot?.date ?? null,
        indicators_stale: stale, indicators_available: Boolean(snapshot) && !stale };
    // A mismatched same-day snapshot is as unsafe to combine as an older one.
    if (stale) for (const field of ["volume", "r_vol", "rsi_14", "macd", "macd_signal", "macd_histogram",
        "bb_upper", "bb_lower", "ema_50", "ema_200", "king_ai_score", "egx_ai_score"]) result[field] = null;
    return result;
}
