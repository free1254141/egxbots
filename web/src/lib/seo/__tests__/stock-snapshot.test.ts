import { getPublicStockSnapshot } from '../stock-snapshot';
import { getPublicMarketClient } from '@/lib/supabase/route-data';
jest.mock('server-only', () => ({}));
jest.mock('next/cache', () => ({ unstable_cache: (fn: any) => fn }));
jest.mock('@/lib/supabase/route-data', () => ({ getPublicMarketClient: jest.fn() }));

test('public snapshot keeps independent data dates and every read is projected and bounded', async () => {
    const queries: any[] = [];
    const rows: any = { stock_fundamentals: [{ symbol: 'ABUK', exchange: 'EGX', data: { name: 'Abu Qir' } }],
        stock_prices: [{ date: '2026-10-14', close: 90 }, { date: '2026-10-13', close: 85 }],
        stock_technical_indicators: [{ date: '2026-10-13', close: 85, rsi_14: 25 }], scan_results: [] };
    (getPublicMarketClient as jest.Mock).mockReturnValue({ from(table: string) {
        const ops: any[] = []; queries.push({ table, ops }); let limit = 0;
        const q: any = new Proxy({}, { get: (_, key: string) => key === 'then'
            ? (yes: any, no: any) => Promise.resolve({ data: rows[table].slice(0, limit), error: null }).then(yes, no)
            : (...args: any[]) => { ops.push([key, ...args]); if (key === 'limit') limit = args[0]; return q; } });
        return q;
    } });
    const snapshot = await getPublicStockSnapshot('ABUK');
    expect(snapshot.latestPrice).toMatchObject({ date: '2026-10-14', close: 90 });
    expect(snapshot.latestTech).toMatchObject({ date: '2026-10-13', close: 85, rsi_14: 25 });
    expect(snapshot.historicalPrices.map((row: any) => row.date)).toEqual(['2026-10-13', '2026-10-14']);
    expect(queries).toHaveLength(5);
    for (const query of queries) {
        expect(query.ops).toContainEqual(['eq', 'symbol', 'ABUK']); expect(query.ops).toContainEqual(['eq', 'exchange', 'EGX']);
        expect(query.ops.some((op: any[]) => op[0] === 'limit' && op[1] <= 30)).toBe(true);
        expect(query.ops.find((op: any[]) => op[0] === 'select')[1]).not.toContain('*');
    }
});
