import StockPage, { generateMetadata } from '@/app/stocks/[symbol]/page';
import { getPublicMarketClient } from '@/lib/supabase/route-data';
jest.mock('@/app/stocks/[symbol]/StockDetailClient', () => () => null);
jest.mock('@/lib/supabase/route-data', () => ({ getPublicMarketClient: jest.fn() }));
jest.mock('../stock-directory', () => ({ getPublicStockDirectory: async () => [] }));
jest.mock('next/navigation', () => ({ notFound: () => { throw new Error('NOT_FOUND'); } }));
function client(fund: any, price: any) {
    (getPublicMarketClient as jest.Mock).mockReturnValue({ from(table: string) {
        const q: any = new Proxy({}, { get: (_, key: string) => key === 'then'
            ? (yes: any, no: any) => Promise.resolve(table === 'stock_fundamentals' ? fund : price).then(yes, no) : () => q });
        return q;
    } });
}
const params = () => ({ params: Promise.resolve({ symbol: 'abuk' }) });
test('temporary fundamentals failure is not a missing stock or cached 404', async () => {
    client({ data: null, error: { message: 'temporary database failure' } }, { data: [], error: null });
    await expect(generateMetadata(params())).rejects.toThrow('Unable to load public stock fundamentals');
});
test('temporary fallback existence failure is not a cached 404', async () => {
    client({ data: [], error: null }, { data: null, error: { message: 'temporary database failure' } });
    await expect(StockPage(params())).rejects.toThrow('Unable to verify public stock existence');
});
test('a verified missing stock still returns notFound', async () => {
    client({ data: [], error: null }, { data: [], error: null });
    await expect(StockPage(params())).rejects.toThrow('NOT_FOUND');
});
