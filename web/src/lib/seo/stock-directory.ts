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
import { fetchHfPublicJson } from '@/lib/hf-public-read';

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
async function fetchEgxDirectoryUncached(tags?: string[]) {
    const hf = await fetchHfPublicJson<{ stocks?: ReturnType<typeof normalizeStockDirectory> }>(
        '/api/public/stock-directory?market=egx',
        604800,
        5000,
        tags
    );
    if (Array.isArray(hf?.stocks) && hf.stocks.length > 0) {
        return hf.stocks;
    }
    const { data, error } = await getPublicMarketClient().from('stock_fundamentals')
        .select('symbol,exchange,updated_at,name:data->>name,name_legacy:data->>Name,sector:data->>sector,sector_legacy:data->>Sector,market_cap:data->marketCap').eq('exchange', 'EGX')
        .order('symbol', { ascending: true }).limit(501);
    if (error || !Array.isArray(data) || !data.length || data.length > 500)
        throw new Error('Unable to load a complete public EGX stock directory');
    const stocks = normalizeStockDirectory(data);
    if (!stocks.length) throw new Error('Public stock directory contains no valid EGX symbols');
    return stocks;
}

export const getPublicStockDirectory = unstable_cache(
    () => fetchEgxDirectoryUncached([DAILY_CACHE_TAGS.symbols]),
    ['public-egx-stock-directory-v1'],
    { revalidate: 604800, tags: [DAILY_CACHE_TAGS.symbols] }
);

async function fetchTasiDirectoryUncached(tags?: string[]): Promise<TasiStockDirectoryEntry[]> {
    const hf = await fetchHfPublicJson<{ stocks?: TasiStockDirectoryEntry[] }>(
        '/api/public/stock-directory?market=tasi',
        604800,
        5000,
        tags
    );
    if (Array.isArray(hf?.stocks) && hf.stocks.length > 0) {
        return hf.stocks;
    }
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
}

export const getPublicTasiStockDirectory = unstable_cache(
    () => fetchTasiDirectoryUncached([DAILY_CACHE_TAGS.symbols]),
    ['public-tasi-stock-directory-v1'],
    { revalidate: 604800, tags: [DAILY_CACHE_TAGS.symbols] }
);

// Weekly untagged caches for /stocks/[symbol] related links so daily pipeline runs
// do not cascade-invalidate all 250+ individual stock ISR pages.
export const getPublicStockDirectoryWeekly = unstable_cache(
    () => fetchEgxDirectoryUncached(),
    ['public-egx-stock-directory-weekly-v1'],
    { revalidate: 604800 }
);

export const getPublicTasiStockDirectoryWeekly = unstable_cache(
    () => fetchTasiDirectoryUncached(),
    ['public-tasi-stock-directory-weekly-v1'],
    { revalidate: 604800 }
);

const GCC_METALS_EXCHANGES = ['DFM', 'ADX', 'QSE', 'COMMODITIES'] as const;

async function fetchGccMetalsDirectoryUncached(tags?: string[]): Promise<TasiStockDirectoryEntry[]> {
    const hf = await fetchHfPublicJson<{ stocks?: GccMarketStockRow[] }>(
        '/api/public/gcc-metals-directory',
        604800,
        5000,
        tags
    );
    if (Array.isArray(hf?.stocks) && hf.stocks.length > 0) {
        return hf.stocks;
    }
    try {
        const client = getMarketSupabaseClient('tasi');
        const { data, error } = await client
            .from('stocks')
            .select('symbol,exchange,name,name_ar,sector,currency,updated_at')
            .in('exchange', [...GCC_METALS_EXCHANGES])
            .eq('is_active', true)
            .order('symbol', { ascending: true })
            .limit(500);
        if (error || !Array.isArray(data)) return [];
        const bySym = new Map<string, TasiStockDirectoryEntry>();
        for (const row of data) {
            const sym = String(row?.symbol ?? '').trim().toUpperCase();
            if (!sym) continue;
            bySym.set(sym, {
                symbol: sym,
                name: String(row?.name || sym).trim(),
                nameAr: row?.name_ar ? String(row.name_ar).trim() : undefined,
                sector: String(row?.sector || '').trim(),
                marketCap: null,
                ...(row?.updated_at ? { updatedAt: String(row.updated_at) } : {}),
                exchange: String(row?.exchange || '').trim(),
                currency: String(row?.currency || 'USD').trim(),
            });
        }
        return [...bySym.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
    } catch {
        return [];
    }
}

export const getPublicGccMetalsDirectory = unstable_cache(
    () => fetchGccMetalsDirectoryUncached([DAILY_CACHE_TAGS.symbols]),
    ['public-gcc-metals-directory-v1'],
    { revalidate: 604800, tags: [DAILY_CACHE_TAGS.symbols] }
);

export const getPublicGccMetalsDirectoryWeekly = unstable_cache(
    () => fetchGccMetalsDirectoryUncached(),
    ['public-gcc-metals-directory-weekly-v1'],
    { revalidate: 604800 }
);

export interface GccMarketStockRow extends TasiStockDirectoryEntry {
    close?: number | null;
    changePct?: number | null;
    rsi14?: number | null;
    priceDate?: string | null;
}

export const getPublicGccMetalsDirectoryWithPrices = unstable_cache(
    async (): Promise<GccMarketStockRow[]> => {
        const hf = await fetchHfPublicJson<{ stocks?: GccMarketStockRow[] }>(
            '/api/public/gcc-metals-directory',
            604800,
            5000,
            [DAILY_CACHE_TAGS.symbols]
        );
        if (Array.isArray(hf?.stocks) && hf.stocks.length > 0) {
            return hf.stocks;
        }
        try {
            const client = getMarketSupabaseClient('tasi');
            const [stocks, indRes] = await Promise.all([
                fetchGccMetalsDirectoryUncached(),
                client
                    .from('stock_technical_indicators')
                    .select('symbol,exchange,close,change_pct,rsi_14,date')
                    .in('exchange', [...GCC_METALS_EXCHANGES])
                    .limit(500),
            ]);
            const indMap = new Map<string, any>();
            for (const row of indRes.data || []) {
                const k = `${String(row?.exchange || '').toUpperCase()}:${String(row?.symbol || '').toUpperCase()}`;
                indMap.set(k, row);
            }
            return stocks.map((st) => {
                const ind = indMap.get(`${String(st.exchange || '').toUpperCase()}:${st.symbol.toUpperCase()}`);
                return {
                    ...st,
                    close: ind?.close != null ? Number(ind.close) : null,
                    changePct: ind?.change_pct != null ? Number(ind.change_pct) : null,
                    rsi14: ind?.rsi_14 != null ? Number(ind.rsi_14) : null,
                    priceDate: ind?.date ? String(ind.date).slice(0, 10) : null,
                };
            });
        } catch {
            return [];
        }
    },
    ['public-gcc-metals-with-prices-v1'],
    { revalidate: 604800, tags: [DAILY_CACHE_TAGS.symbols] }
);

export async function getPublicStockDirectoryByMarket(market: MarketMode = 'egx') {
    return market === 'tasi' ? getPublicTasiStockDirectory() : getPublicStockDirectory();
}
