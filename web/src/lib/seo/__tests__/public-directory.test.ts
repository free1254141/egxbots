import { getPublicStockDirectory } from '../stock-directory';
import { getPublicMarketClient } from '@/lib/supabase/route-data';
jest.mock('server-only', () => ({}));
jest.mock('next/cache', () => ({ unstable_cache: (fn: any) => fn }));
jest.mock('@/lib/supabase/route-data', () => ({ getPublicMarketClient: jest.fn() }));
const client = getPublicMarketClient as jest.Mock;
function response(data: any, error: any = null) {
    const ops: any[] = [];
    const query: any = new Proxy({}, { get: (_, key: string) => key === 'then'
        ? (yes: any, no: any) => Promise.resolve({ data, error }).then(yes, no)
        : (...args: any[]) => { ops.push([key, ...args]); return query; } });
    client.mockReturnValue({ from: (table: string) => { ops.push(['from', table]); return query; } });
    return ops;
}
test('one bounded anonymous public read supports the directory and sitemap without account data', async () => {
    const ops = response([{ symbol: 'ABUK', exchange: 'EGX', name: 'Abu Qir' }]);
    expect((await getPublicStockDirectory())[0].symbol).toBe('ABUK');
    expect(ops).toContainEqual(['eq', 'exchange', 'EGX']); expect(ops).toContainEqual(['limit', 501]);
    expect(ops.filter(op => op[0] === 'from')).toEqual([['from', 'stock_fundamentals']]);
    expect(ops.find(op => op[0] === 'select')[1]).not.toContain('*');
});
test.each([[null, { message: 'temporary database error' }], [[], null], [Array(501).fill({ symbol: 'ABUK', exchange: 'EGX' }), null]])('temporary or incomplete input fails regeneration instead of deleting stock URLs', async (data, error) => {
    response(data, error); await expect(getPublicStockDirectory()).rejects.toThrow('Unable to load a complete');
});
