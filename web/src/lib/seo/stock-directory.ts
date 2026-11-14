import 'server-only';
import { unstable_cache } from 'next/cache';
import {
    getPublicMarketClient,
    getMarketSupabaseClient,
    type MarketMode,
} from '@/lib/supabase/route-data';
import { DAILY_CACHE_TAGS } from '@/lib/cache/daily';
import { normalizeStockDirectory } from './sitemap-entries';
import { POPULAR_TASI_STOCKS, SAUDI_STOCK_NAMES_AR, isSaudiSymbol } from '@/lib/saudi-stocks';

export interface TasiStockDirectoryEntry {
    symbol: string;
    name: string;
    sector: string;
    marketCap: number | null;
    updatedAt?: string;
    nameAr?: string;
    exchange?: string;
    currency?: string;
}

function normalizeTasiStockDirectory(rows: any[]): TasiStockDirectoryEntry[] {
    const bySymbol = new Map<string, TasiStockDirectoryEntry>();
    for (const row of rows || []) {
        const rawSym = String(row?.symbol ?? '').trim().toUpperCase();
        const baseSym = rawSym.replace(/\.(SR|SA|TADAWUL)$/i, '');
        if (!baseSym || !isSaudiSymbol(baseSym)) continue;
        const nameEn = String(row?.name || row?.name_legacy || '').trim();
        const nameAr = String(row?.name_ar || SAUDI_STOCK_NAMES_AR[baseSym] || '').trim();
        const sector = String(row?.sector || row?.sector_legacy || '').trim();
        const rawCap = row?.market_cap;
        const parsedCap = rawCap !== null && rawCap !== undefined && rawCap !== '' ? Number(rawCap) : null;
        const existing = bySymbol.get(baseSym);
        const updatedAt = row?.updated_at ? String(row.updated_at) : existing?.updatedAt;
        bySymbol.set(baseSym, {
            symbol: baseSym,
            name: nameEn || nameAr || existing?.name || baseSym,
            nameAr: nameAr || existing?.nameAr || undefined,
            sector: sector || existing?.sector || '',
            marketCap: parsedCap !== null && Number.isFinite(parsedCap) ? parsedCap : (existing?.marketCap ?? null),
            ...(updatedAt ? { updatedAt } : {}),
            exchange: 'TADAWUL',
            currency: String(row?.currency || existing?.currency || 'SAR'),
        });
    }
    return [...bySymbol.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
}

// The public directory and sitemap share one cookie-free, anonymous-RLS read.
// A failed read throws so ISR can retain the last healthy HTML/XML response.
export const getPublicStockDirectory = unstable_cache(async () => {
    const { data, error } = await getPublicMarketClient().from('stock_fundamentals')
        .select('symbol,exchange,updated_at,name:data->>name,name_legacy:data->>Name,sector:data->>sector,sector_legacy:data->>Sector,market_cap:data->marketCap').eq('exchange', 'EGX')
        .order('symbol', { ascending: true }).limit(501);
    if (error || !Array.isArray(data) || !data.length || data.length > 500)
        throw new Error('Unable to load a complete public EGX stock directory');
    const stocks = normalizeStockDirectory(data);
    if (!stocks.length) throw new Error('Public stock directory contains no valid EGX symbols');
    return stocks;
}, ['public-egx-stock-directory-v1'], { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market, DAILY_CACHE_TAGS.symbols] });

export const getPublicTasiStockDirectory = unstable_cache(async () => {
    const client = getMarketSupabaseClient('tasi');
    const fundPromise = client
        .from('stock_fundamentals')
        .select('symbol,exchange,updated_at,name:data->>name,name_legacy:data->>Name,sector:data->>sector,sector_legacy:data->>Sector,market_cap:data->marketCap')
        .eq('exchange', 'TADAWUL')
        .order('symbol', { ascending: true })
        .limit(1000);

    let stocksRes = await client
        .from('stocks')
        .select('symbol,exchange,name,name_ar,sector,currency')
        .eq('exchange', 'TADAWUL')
        .order('symbol', { ascending: true })
        .limit(1000);

    if (stocksRes.error) {
        stocksRes = await client
            .from('stocks')
            .select('symbol,exchange,name,sector')
            .eq('exchange', 'TADAWUL')
            .order('symbol', { ascending: true })
            .limit(1000);
    }

    const fundRes = await fundPromise;
    if (fundRes.error && stocksRes.error) {
        throw new Error('Unable to load a complete public TASI stock directory');
    }

    const combined = [
        ...(Array.isArray(stocksRes.data) ? stocksRes.data : []),
        ...(Array.isArray(fundRes.data) ? fundRes.data : []),
    ];
    const normalized = normalizeTasiStockDirectory(combined);
    if (normalized.length > 0) return normalized;

    return POPULAR_TASI_STOCKS.map((s) => ({
        symbol: s.symbol,
        name: s.name,
        nameAr: s.name_ar,
        sector: '',
        marketCap: null,
        exchange: 'TADAWUL',
        currency: 'SAR',
    }));
}, ['public-tasi-stock-directory-v1'], { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market, DAILY_CACHE_TAGS.symbols] });

export async function getPublicStockDirectoryByMarket(market: MarketMode = 'egx') {
    return market === 'tasi' ? getPublicTasiStockDirectory() : getPublicStockDirectory();
}
