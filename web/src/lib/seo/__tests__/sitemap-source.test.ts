import sitemap from '@/app/sitemap';
import { getPublicMarketClient } from '@/lib/supabase/route-data';
jest.mock('@/lib/seo/stock-directory', () => ({ getPublicStockDirectory: async () => [{ symbol: 'ABUK', updatedAt: '2026-10-01T00:00:00Z' }] }));
jest.mock('@/lib/social/public-reports', () => ({ getPublicReports: async () => [{ session_date: '2026-10-06', kind: 'market', updated_at: '2026-10-06T15:00:00Z' }],
    reportUrl: (r: any) => `/reports/${r.session_date}/${r.kind}` }));
jest.mock('@/lib/supabase/route-data', () => ({ getPublicMarketClient: jest.fn() }));
function mockPosts(data: any[], count: number) {
    const q: any = new Proxy({}, { get: (_, key: string) => key === 'then'
        ? (yes: any, no: any) => Promise.resolve({ data, count, error: null }).then(yes, no) : () => q });
    (getPublicMarketClient as jest.Mock).mockReturnValue({ from: () => q });
}
test('actual sitemap combines canonical stocks, published posts and approved reports only', async () => {
    mockPosts([{ slug: 'ready', is_published: true }, { slug: 'draft', is_published: false }], 2);
    const pages = await sitemap(); const urls = pages.map(p => p.url);
    expect(urls).toContain('https://egxbots.com/stocks/abuk'); expect(urls).toContain('https://egxbots.com/reports/2026-10-06/market');
    expect(urls).toContain('https://egxbots.com/blogs/chat/ready'); expect(urls).not.toContain('https://egxbots.com/blogs/chat/draft');
    expect(urls.some(url => /\/profile|\/admin|\/api\//.test(url))).toBe(false);
});
test('a lower server row cap cannot silently publish a truncated sitemap', async () => {
    mockPosts([{ slug: 'ready', is_published: true }], 1500);
    await expect(sitemap()).rejects.toThrow('Unable to load complete published blog sitemap');
});
