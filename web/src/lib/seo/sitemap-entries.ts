import type { MetadataRoute } from 'next';

export function validLastModified(value: unknown): Date | undefined {
    if (typeof value !== 'string' || !value.trim()) return undefined;
    const date = new Date(value);
    return Number.isFinite(date.getTime()) && date.getTime() <= Date.now() ? date : undefined;
}

export function normalizeStockDirectory(rows: any[]) {
    const directory = new Map<string, { symbol: string; name: string; sector: string; marketCap: number | null; updatedAt?: string }>();
    for (const row of rows) {
        if (row.exchange !== 'EGX' || typeof row.symbol !== 'string') continue;
        const symbol = row.symbol.trim().toUpperCase();
        if (!/^[A-Z][A-Z0-9]{1,11}$/.test(symbol)) continue;
        const data = row.data || {};
        const updatedAt = validLastModified(row.updated_at)?.toISOString();
        const previous = directory.get(symbol);
        if (previous && (!updatedAt || previous.updatedAt && previous.updatedAt >= updatedAt)) continue;
        const cap = row.market_cap ?? data.marketCap;
        directory.set(symbol, { symbol, name: String(row.name || row.name_legacy || data.name || data.Name || symbol),
            sector: String(row.sector || row.sector_legacy || data.sector || data.Sector || ''),
            marketCap: typeof cap === 'number' && Number.isFinite(cap) ? cap : null,
            ...(updatedAt ? { updatedAt } : {}) });
    }
    return [...directory.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
}

export function canonicalSitemap(entries: MetadataRoute.Sitemap): MetadataRoute.Sitemap {
    const pages = new Map<string, MetadataRoute.Sitemap[number]>();
    for (const entry of entries) {
        let url: URL;
        try { url = new URL(entry.url); } catch { continue; }
        if (url.origin !== 'https://egxbots.com' || url.search || url.hash) continue;
        const previous = pages.get(entry.url);
        if (!previous) pages.set(entry.url, entry);
        else if (entry.lastModified && (!previous.lastModified || new Date(entry.lastModified) > new Date(previous.lastModified)))
            pages.set(entry.url, entry);
    }
    return [...pages.values()];
}

export function selectStockLinks(directory: ReturnType<typeof normalizeStockDirectory>, symbol: string, sector: string) {
    const other = directory.filter(stock => stock.symbol !== symbol);
    const peers = sector.trim() ? other.filter(stock => stock.sector.trim().toLowerCase() === sector.trim().toLowerCase()) : [];
    return { basis: peers.length ? 'sector' as const : 'directory' as const,
        stocks: (peers.length ? peers : [...other.filter(stock => stock.symbol > symbol), ...other.filter(stock => stock.symbol < symbol)]).slice(0, 7)
            .map(({ symbol, name }) => ({ symbol, name })) };
}

export function publishedBlogEntries(posts: any[], baseUrl: string): MetadataRoute.Sitemap {
    return posts.filter(post => post.is_published === true && typeof post.slug === 'string'
        && /^[\p{L}\p{N}][\p{L}\p{N}_-]*$/u.test(post.slug)).map(post => ({
            url: `${baseUrl}/blogs/chat/${encodeURIComponent(post.slug)}`,
            lastModified: validLastModified(post.updated_at) || validLastModified(post.created_at),
            changeFrequency: 'weekly' as const, priority: .75,
        }));
}
