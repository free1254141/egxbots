import { renderToStaticMarkup } from 'react-dom/server';
import { canonicalSitemap, normalizeStockDirectory, publishedBlogEntries, selectStockLinks, validLastModified } from '../sitemap-entries';
import TechnicalScannerGuide from '@/app/scanner/technical/TechnicalScannerGuide';

let mockLanguage = 'ar';
jest.mock('@/contexts/LanguageContext', () => ({ useLanguage: () => ({ language: mockLanguage }) }));
const directory = [
    { symbol: 'ABUK', exchange: 'EGX', name: 'أبو قير للأسمدة', sector: 'Materials', updated_at: '2026-10-10T09:00:00Z' },
    { symbol: 'abuk', exchange: 'EGX', name: 'الأحدث', sector: 'Materials', updated_at: '2026-10-12T09:00:00Z' },
    { symbol: 'ACAMD', exchange: 'EGX', name: 'Arab development', sector: 'Real estate' },
    { symbol: 'MFPC', exchange: 'EGX', name: 'MOPCO', sector: 'Materials' },
    { symbol: 'ABUK', exchange: 'US', name: 'Different exchange' },
    { symbol: '../profile', exchange: 'EGX' }, { symbol: null, exchange: 'EGX' },
];

test('published EGX stock links are canonical and deduplicated, never ticker substitutions', () => {
    const stocks = normalizeStockDirectory(directory);
    expect(stocks.map(s => s.symbol)).toEqual(['ABUK', 'ACAMD', 'MFPC']);
    expect(stocks[0]).toMatchObject({ name: 'الأحدث', updatedAt: '2026-10-12T09:00:00.000Z' });
    expect(stocks[1].updatedAt).toBeUndefined();
});
test('related links use the actual published sector and never invented peers or the same stock', () => {
    const stocks = normalizeStockDirectory(directory);
    expect(selectStockLinks(stocks, 'ABUK', 'Materials')).toEqual({ basis: 'sector', stocks: [{ symbol: 'MFPC', name: 'MOPCO' }] });
    const fallback = selectStockLinks(stocks, 'MFPC', '');
    expect(fallback.basis).toBe('directory');
    expect(fallback.stocks.map(s => s.symbol)).toEqual(['ABUK', 'ACAMD']);
});
test('lastmod is sourced from real timestamps, not refresh time, invalid dates or future values', () => {
    expect(validLastModified(null)).toBeUndefined(); expect(validLastModified('bad-date')).toBeUndefined();
    expect(validLastModified('2999-01-01T00:00:00Z')).toBeUndefined();
    expect(validLastModified('2026-01-01T00:00:00Z')?.toISOString()).toBe('2026-01-01T00:00:00.000Z');
});
test('blog sitemap includes published safe slugs only and retains their known change time', () => {
    const pages = publishedBlogEntries([
        { slug: 'public-note', is_published: true, updated_at: '2026-01-01T00:00:00Z' },
        { slug: 'draft-note', is_published: false }, { slug: '../profile', is_published: true },
        { slug: 'public?private=1', is_published: true },
    ], 'https://egxbots.com');
    expect(pages).toHaveLength(1); expect(pages[0].url).toBe('https://egxbots.com/blogs/chat/public-note');
    expect(pages[0].lastModified).toEqual(new Date('2026-01-01T00:00:00Z'));
    expect(canonicalSitemap([...pages, ...pages, { url: 'https://other.test/stocks/abuk' }, { url: 'https://egxbots.com/stocks/abuk?filter=1' }, { url: 'malformed' }])).toEqual(pages);
});
test.each(['ar', 'en'])('scanner introduction has useful raw HTML and links before JavaScript in %s', language => {
    mockLanguage = language;
    const html = renderToStaticMarkup(<TechnicalScannerGuide />);
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    for (const path of ['/stocks', '/reports', '/scanner/backtests']) expect(html).toContain(`href="${path}"`);
    expect(html).toContain('RSI'); expect(html).toContain('MACD');
    expect(html).toContain(language === 'ar' ? 'طريقة الاستخدام' : 'How to use');
    expect(html).toContain(language === 'ar' ? 'وليست أسعاراً لحظية' : 'not live quotes');
    expect(html).toContain(`dir="${language === 'ar' ? 'rtl' : 'ltr'}"`);
});
