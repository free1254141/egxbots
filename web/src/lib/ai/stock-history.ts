/** Bounded stored price history; calendar dates stay in Cairo, never UTC slices. */
const finite = (n: unknown): number | null => n == null || n === "" || !Number.isFinite(Number(n)) ? null : Number(n);
const change = (end: number | null, base: number | null) => end == null || base == null || base <= 0 ? null : Number(((end - base) / base * 100).toFixed(2));
export function summarizeStockHistory(rows: Array<Record<string, any>>, now = new Date()) {
    const prices = [...rows].sort((a,b) => String(b.date).localeCompare(String(a.date)));
    const sunday = new Date(`${new Intl.DateTimeFormat("en-CA", {timeZone:"Africa/Cairo",year:"numeric",month:"2-digit",day:"2-digit"}).format(now)}T00:00:00Z`);
    sunday.setUTCDate(sunday.getUTCDate() - sunday.getUTCDay());
    const thisWeek = sunday.toISOString().slice(0,10);
    sunday.setUTCDate(sunday.getUTCDate() - 7);
    const lastWeek = sunday.toISOString().slice(0,10);
    const week = prices.filter(r => r.date >= lastWeek && r.date < thisWeek);
    const first = week[week.length - 1], last = week[0];
    const baseline = first ? prices.find(r => r.date < first.date) : null;
    return {
        recent_sessions: prices.slice(0,10).map((r,i) => ({date:r.date, close:finite(r.close), high:finite(r.high), low:finite(r.low), change_pct:change(finite(r.close),finite(prices[i+1]?.close))})),
        last_week_summary: first ? {
            sessions_count:week.length, start_date:first.date, end_date:last.date,
            start_close:finite(first.close), end_close:finite(last.close),
            baseline_date:baseline?.date ?? null, baseline_close:finite(baseline?.close),
            change_pct:change(finite(last.close),finite(baseline?.close)),
            within_week_change_pct:change(finite(last.close),finite(first.close)),
            change_basis:"previous_session_before_week_to_last_session; null if baseline missing",
            corporate_actions_adjusted:false
        } : null
    };
}
