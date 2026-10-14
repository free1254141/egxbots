import { executeAgenticTool } from '../agentic-tools';
import { fetchLiveStockIndicators, isEgxSessionOpen } from '../live-stock-updater';
import { isDailySyncComplete } from '../sync-gate';
import { toAgenticEvidence, checkAgenticDraft } from '../agentic-publication';
import { renderStockRecovery } from '../stock-recovery';

jest.mock('../live-stock-updater', () => ({ fetchLiveStockIndicators: jest.fn(), isEgxSessionOpen: jest.fn() }));
const provider = fetchLiveStockIndicators as jest.Mock;
const open = isEgxSessionOpen as jest.Mock;
const stamp = '2026-10-14T10:00:00Z';
const live = { success: true, data: { close: 110, change_pct: 10, volume: 2000, rsi_14: 45, macd: 2, macd_signal: 1,
    ema_50: 105, ema_200: 95, bb_upper: 120, bb_lower: 90, updated_at: stamp } };
const snapshot = { symbol: 'COMI', date: '2026-10-13', close: 100, rsi_14: 20, macd: -3, macd_signal: -2, king_ai_score: .4, egx_ai_score: .6 };
const closeJob = { status: 'completed', started_at: '2026-10-14T14:00:00Z', completed_at: '2026-10-14T15:00:00Z',
    steps: [{ step: 'sync_prices', status: 'started' }, { step: 'sync_prices', status: 'success' }] };
function db(job: any = null, prices = [{ date: '2026-10-13', close: 100 }]) {
    const queries: any[] = [];
    return { queries, from(table: string) {
        const ops: any[] = []; queries.push({ table, ops });
        const rows: Record<string, any[]> = { stock_technical_indicators: [snapshot], stock_prices: prices, daily_job_runs: job ? [job] : [], stocks: [{ symbol: 'COMI', name: 'البنك التجاري الدولي' }] };
        const q: any = new Proxy({}, { get: (_, key: string) => key === 'then'
            ? (yes: any, no: any) => Promise.resolve({ data: rows[table] || [], error: null }).then(yes, no)
            : (...args: any[]) => { ops.push([key, ...args]); return q; } });
        return q;
    } };
}
beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date('2026-10-14T12:00:00Z'));
    provider.mockReset().mockResolvedValue(live); open.mockReset().mockReturnValue(false);
});
afterEach(() => jest.useRealTimers());

test.each(['get_stock', 'get_comparison'])('%s gets the provider snapshot automatically while the market is open', async tool => {
    open.mockReturnValue(true);
    const client = db(closeJob, [{ date: '2026-10-14', close: 100 }]);
    const result = await executeAgenticTool(tool, { symbols: ['COMI'] }, client, 'offline');
    const row = (result.stocks || result.comparison)[0];
    expect(row).toMatchObject({ close: 110, date: null, quote_source: 'tradingview', price_type: 'provider_quote',
        final_close_confirmed: false, live_quote_available: true, fetched_at: stamp, rsi_14: 45, indicators_source: 'tradingview', king_ai_score: null });
    expect(row.fetched_at_cairo).toContain('13:00:00');
    expect(provider).toHaveBeenCalledTimes(1);
    expect(client.queries.every(q => q.ops.some((op: any[]) => op[0] === 'limit'))).toBe(true);
    const evidence = toAgenticEvidence(tool, { symbols: ['COMI'] }, result);
    expect(evidence.data_type).toBe('provider-snapshot');
    expect(checkAgenticDraft('COMI سعره 110 جنيه، وقت الجلب 12:00 بتوقيت القاهرة.', [evidence], '', [evidence])).toContain('quote_fetch_time_cairo_mismatch');
});
test.each(['running', 'failed'])('after 18:00 an unfinished %s close job still uses the provider', async status => {
    jest.setSystemTime(new Date('2026-10-14T16:30:00Z'));
    const result = await executeAgenticTool('get_comparison', { symbols: ['COMI'] }, db({ ...closeJob, status }), 'offline');
    expect(result.comparison[0]).toMatchObject({ close: 110, final_close_confirmed: false, live_quote_available: true });
});
test('a completed close run with a successful sync and this symbol date confirms the stored close', async () => {
    const client = db(closeJob, [{ date: '2026-10-14', close: 108 }]);
    const result = await executeAgenticTool('get_stock', { symbols: ['COMI'] }, client, 'offline');
    expect(result.stocks[0]).toMatchObject({ close: 108, date: '2026-10-14', price_type: 'daily_close', final_close_confirmed: true, indicators_stale: true });
    expect(provider).not.toHaveBeenCalled();
    expect(client.queries.find(q => q.table === 'daily_job_runs').ops).toContainEqual(['order', 'started_at', { ascending: false }]);
    expect(client.queries.filter(q => q.table === 'stock_prices').every(q => q.ops.some((op: any[]) => op[0] === 'eq' && op[1] === 'symbol' && op[2] === 'COMI'))).toBe(true);
});
test.each(['failed_prices', 'stale_symbol', 'midday_only'])('%s cannot certify a final close', async mode => {
    const job = mode === 'midday_only' ? null : { ...closeJob, steps: mode === 'failed_prices' ? [{ step: 'sync_prices', status: 'started' }, { step: 'sync_prices', status: 'failed' }] : closeJob.steps };
    const result = await executeAgenticTool('get_stock', { symbols: ['COMI'] }, db(job), 'offline');
    expect(result.stocks[0]).toMatchObject({ close: 110, live_quote_available: true, final_close_confirmed: false });
});
test('a double-encoded ledger is accepted only after completed successful synchronization', async () => {
    expect(await isDailySyncComplete(db({ ...closeJob, steps: JSON.stringify(JSON.stringify(closeJob.steps)) }, [{ date: '2026-10-14', close: 108 }]), '2026-10-14', 'COMI')).toBe(true);
});
test('provider failure preserves the saved date and marks a same-day value as a session snapshot', async () => {
    provider.mockResolvedValue({ success: false, error: 'provider unavailable' });
    const result = await executeAgenticTool('get_stock', { symbols: ['COMI'] }, db(null, [{ date: '2026-10-14', close: 108 }]), 'offline');
    expect(result.stocks[0]).toMatchObject({ close: 108, date: '2026-10-14', live_quote_available: false,
        price_type: 'current_session_snapshot', final_close_confirmed: false, indicators_stale: true });
    expect(renderStockRecovery(result.stocks)).toContain('تعذر التحقق من سعر جديد');
});
test('explicit provider failure does not trigger another provider attempt during stored recovery', async () => {
    provider.mockResolvedValue({ success: false });
    const result = await executeAgenticTool('get_live_quote', { symbols: ['COMI'] }, db(), 'offline');
    expect(result.stocks[0].live_quote_available).toBe(false); expect(provider).toHaveBeenCalledTimes(1);
});
test('temporary positions can use the provider value without inventing a last-trade date', async () => {
    const result = await executeAgenticTool('calculate_position', { symbol: 'COMI', quantity: 10, entry_price: 100 }, db(), 'offline');
    expect(result.positions[0]).toMatchObject({ close: 110, date: null, market_value: 1100, profit_loss_val: 100, price_type: 'provider_quote' });
});
test.each([false, true])('older levels cannot overwrite a provider price in either evidence order: %s', reverse => {
    const current = { symbol: 'COMI', close: 110, date: null, live_quote_available: true, fetched_at: stamp, fetched_at_cairo: '13:00:00', price_label: 'أحدث سعر متاح من المزود', macd: 2, macd_signal: 1, indicators_source: 'tradingview', indicators_observed_at: stamp };
    const level = { symbol: 'COMI', close: 100, date: '2026-10-14', support: 90, resistance: 103, macd: -3, macd_signal: -2 };
    const reply = renderStockRecovery(reverse ? [level, current] : [current, level]);
    expect(reply).toContain('110 جنيه'); expect(reply).toContain('فوق خط إشارته');
    expect(reply).not.toContain('103'); expect(reply).not.toContain('100 جنيه'); expect(reply).not.toContain('تحت خط إشارته');
});
