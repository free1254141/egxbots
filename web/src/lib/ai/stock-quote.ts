import { todayInCairo } from "./cairo-date";
import { fetchLiveStockIndicators, isEgxSessionOpen } from "./live-stock-updater";
import { isDailySyncComplete, shouldPreferLiveBeforeSync } from "./sync-gate";

export function stockPricePresentation(date: unknown, sessionComplete = false) {
    const currentSession = typeof date === "string" && date.slice(0,10) >= todayInCairo();
    return { price_type: currentSession && !sessionComplete ? "current_session_snapshot" : "daily_close",
        final_close_confirmed: sessionComplete,
        price_label: currentSession && !sessionComplete ? "آخر سعر متاح للجلسة، وليس إغلاقاً نهائياً مؤكداً" : "آخر إغلاق متاح" };
}
/** Prices and indicators are refreshed independently. Never date old indicators
 * as a new quote, or use the indicator snapshot as proof of the newest close. */
export function stockQuoteMetadata(row: any) {
    const keys = ['price_type', 'price_label', 'final_close_confirmed', 'session_complete', 'live_quote_available',
        'live_quote_error', 'quote_time', 'fetched_at', 'fetched_at_cairo', 'provider_delay', 'from_cache',
        'market_session_open', 'indicators_source', 'indicators_observed_at', 'limitations'];
    return Object.fromEntries(keys.filter(key => row?.[key] !== undefined).map(key => [key, row[key]]));
}

export async function reconcileStockQuote(client: any, symbol: string, snapshot: any, options: { preferLive?: boolean } = {}) {
    // Intent stays with the LLM. Source freshness is enforced for every tool
    // that values a stock, even if the writer did not request get_live_quote.
    const sessionOpen = isEgxSessionOpen();
    const pendingClose = shouldPreferLiveBeforeSync();
    const sessionComplete = !sessionOpen && pendingClose && await isDailySyncComplete(client, undefined, symbol);
    let liveFailure: string | undefined;
    if (options.preferLive !== false && (sessionOpen || pendingClose && !sessionComplete)) {
        const live = await fetchLiveStockIndicators(symbol, client, { allowClosedMarket: true });
        if (live.success && live.data) {
            const d = live.data;
            return { ...snapshot, symbol, close: d.close, change_pct: d.change_pct, volume: d.volume,
                rsi_14: d.rsi_14, macd: d.macd, macd_signal: d.macd_signal,
                macd_histogram: d.macd != null && d.macd_signal != null ? d.macd - d.macd_signal : null,
                ema_50: d.ema_50, ema_200: d.ema_200, bb_upper: d.bb_upper, bb_lower: d.bb_lower,
                r_vol: null, king_ai_score: null, egx_ai_score: null,
                date: null, quote_time: null, fetched_at: d.updated_at,
                fetched_at_cairo: new Intl.DateTimeFormat('en-GB', { timeZone: 'Africa/Cairo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(d.updated_at)),
                quote_source: 'tradingview', price_type: 'provider_quote', price_label: 'أحدث سعر متاح من المزود',
                live_quote_available: true, provider_delay: 'unknown', from_cache: live.from_cache === true,
                market_session_open: sessionOpen, session_complete: false, final_close_confirmed: false,
                indicators_date: null, indicators_source: 'tradingview', indicators_observed_at: d.updated_at,
                indicators_stale: false, indicators_available: true,
                limitations: ['وقت الجلب ليس وقت آخر صفقة؛ تأخير المزود غير موثق، وهذه ليست شهادة إغلاق نهائي.'] };
        }
        liveFailure = live.error || 'تعذر جلب سعر جديد من المزود';
    }
    const { data } = await client.from("stock_prices")
        .select("date,close").eq("exchange", "EGX").eq("symbol", symbol)
        .order("date", { ascending: false }).limit(2);
    const prices = (data || []).filter((p: any) => p.date && p.close != null
        && Number.isFinite(Number(p.close)) && Number(p.close) > 0);
    const newest = prices[0];
    if (!newest || (snapshot?.date && String(newest.date) < String(snapshot.date)))
        return snapshot ? { ...snapshot, ...stockPricePresentation(snapshot.date, sessionComplete && snapshot.date === todayInCairo()), quote_source: "stock_technical_indicators", indicators_date: snapshot.date, indicators_stale: false,
            ...(liveFailure ? { live_quote_available: false, live_quote_error: liveFailure, limitations: ['تعذر التحقق من سعر جديد؛ القيمة المعروضة من البيانات المخزنة وتاريخها موضح.'] } : {}) } : null;
    const close = Number(newest.close);
    const stale = Boolean(snapshot && (String(snapshot.date) !== String(newest.date)
        || snapshot.close == null || Math.abs(Number(snapshot.close) - close) > 1e-8));
    const previous = prices[1];
    const change = previous ? (close / Number(previous.close) - 1) * 100
        : !stale ? snapshot?.change_pct ?? null : null;
    const result = { ...(snapshot || {}), ...stockPricePresentation(newest.date, sessionComplete && newest.date === todayInCairo()), date: newest.date, close, change_pct: change,
        quote_source: "stock_prices", indicators_date: snapshot?.date ?? null,
        indicators_stale: stale, indicators_available: Boolean(snapshot) && !stale,
        ...(liveFailure ? { live_quote_available: false, live_quote_error: liveFailure, limitations: ['تعذر التحقق من سعر جديد؛ القيمة المعروضة من البيانات المخزنة وتاريخها موضح.'] } : {}) };
    // A mismatched same-day snapshot is as unsafe to combine as an older one.
    if (stale) for (const field of ["volume", "r_vol", "rsi_14", "macd", "macd_signal", "macd_histogram",
        "bb_upper", "bb_lower", "ema_50", "ema_200", "king_ai_score", "egx_ai_score"]) result[field] = null;
    return result;
}
