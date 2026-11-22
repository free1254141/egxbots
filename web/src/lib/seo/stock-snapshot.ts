import 'server-only';
import { cache } from 'react';
import { unstable_cache } from 'next/cache';
import {
    getPublicMarketClient,
    getMarketSupabaseClient,
    type MarketMode,
} from '@/lib/supabase/route-data';
import { SAUDI_STOCK_NAMES_AR } from '@/lib/saudi-stocks';
import { fetchHfPublicJson } from '@/lib/hf-public-read';

export type StockDisclosureItem = {
    id?: string;
    symbol?: string;
    disclosure_type?: string;
    disclosure_date?: string;
    title?: string;
    ai_summary?: string;
    sentiment?: string;
};

export type PublicStockSnapshotData = {
    fundamentals: any;
    latestPrice: any;
    latestTech: any;
    latestScan: any;
    historicalPrices: any[];
    recentDisclosures?: StockDisclosureItem[];
};

async function readSafeDisclosures(client: any, symOrCandidates: string | string[]): Promise<StockDisclosureItem[]> {
    try {
        let q = client
            .from('egx_disclosures')
            .select('id,symbol,disclosure_type,disclosure_date,title,ai_summary,sentiment');
        if (Array.isArray(symOrCandidates)) {
            q = q.in('symbol', symOrCandidates);
        } else {
            q = q.eq('symbol', symOrCandidates);
        }
        const res = await q.order('disclosure_date', { ascending: false }).limit(3);
        return Array.isArray(res?.data) ? res.data : [];
    } catch {
        return [];
    }
}

export type PublicStockPageBundle = {
    snapshot: PublicStockSnapshotData;
    related: {
        basis: 'sector' | 'directory';
        stocks: Array<{ symbol: string; name: string }>;
    } | null;
};

async function fetchSnapshotBundleFromHf(
    symbol: string,
    market: MarketMode,
    preferredExchange?: string,
): Promise<PublicStockPageBundle | null> {
    const exParam = preferredExchange ? `&exchange=${encodeURIComponent(preferredExchange)}` : '';
    const payload = await fetchHfPublicJson<{
        snapshot?: PublicStockSnapshotData;
        related?: { basis?: 'sector' | 'directory'; stocks?: Array<{ symbol: string; name: string }> };
    }>(`/api/public/stock-page-data?symbol=${encodeURIComponent(symbol)}&market=${market}${exParam}`, 604800);
    if (!payload?.snapshot || (!payload.snapshot.fundamentals && !payload.snapshot.latestPrice)) return null;
    return {
        snapshot: payload.snapshot,
        related: payload.related?.stocks
            ? {
                  basis: payload.related.basis === 'sector' ? 'sector' : 'directory',
                  stocks: payload.related.stocks,
              }
            : null,
    };
}

// Keep SSR stock pages decoupled from DAILY_CACHE_TAGS so daily pipeline runs
// do not mass-invalidate 250+ static HTML stock pages and trigger Vercel CPU spikes.
// StockDetailClient hydrates fresh market data directly from HF on mount (0ms Vercel CPU).
const getPublicEgxStockSnapshot = cache(unstable_cache(async (symbol: string): Promise<PublicStockSnapshotData> => {
    const hf = await fetchSnapshotBundleFromHf(symbol, 'egx');
    if (hf?.snapshot) return hf.snapshot;
    const client = getPublicMarketClient();
    const read = (table: string, fields: string, order: string, limit: number) => client.from(table).select(fields)
        .eq('exchange', 'EGX').eq('symbol', symbol).order(order, { ascending: false }).limit(limit);
    const [fund, price, tech, history, scan, recentDisclosures] = await Promise.all([
        read('stock_fundamentals', 'symbol,exchange,data,updated_at', 'updated_at', 1),
        read('stock_prices', 'symbol,exchange,date,open,high,low,close,volume,updated_at', 'date', 1),
        read('stock_technical_indicators', 'symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200,calculated_at', 'date', 1),
        read('stock_prices', 'date,open,high,low,close,volume', 'date', 30),
        read('scan_results', 'symbol,exchange,created_at,precision,signal,top_reasons', 'created_at', 1),
        readSafeDisclosures(client, symbol),
    ]);
    if (fund.error) throw new Error('Unable to load public stock fundamentals');
    if (price.error) throw new Error('Unable to verify public stock existence');
    if (tech.error || history.error || scan.error) throw new Error('Unable to load a complete public stock snapshot');
    const egxLatestPrice = price.data?.[0] || null;
    const egxFund = fund.data?.[0] || null;
    if (!egxFund && !egxLatestPrice) {
        const gccSnap = await getPublicGccMetalsStockSnapshot(symbol).catch(() => null);
        if (gccSnap) return gccSnap;
    }

    return { fundamentals: egxFund, latestPrice: egxLatestPrice,
        latestTech: tech.data?.[0] || null, latestScan: scan.data?.[0] || null,
        historicalPrices: [...(history.data || [])].reverse(),
        recentDisclosures };
}, ['public-egx-stock-snapshot-v3'], { revalidate: 604800 }));

const GCC_METALS_EXCHANGES = ['DFM', 'ADX', 'QSE', 'COMMODITIES'] as const;

async function getPublicGccMetalsStockSnapshot(symbol: string, preferredExchange?: string): Promise<PublicStockSnapshotData | null> {
    const cleanSymbol = symbol.toUpperCase().trim();
    const targetExchanges = preferredExchange
        ? [preferredExchange.toUpperCase()]
        : [...GCC_METALS_EXCHANGES];
    const client = getMarketSupabaseClient('tasi');
    const [stockRes, priceRes, techRes, histRes, recentDisclosures] = await Promise.all([
        client
            .from('stocks')
            .select('symbol,exchange,country,currency,name,name_ar,sector,updated_at')
            .in('exchange', targetExchanges)
            .eq('symbol', cleanSymbol)
            .limit(1),
        client
            .from('stock_prices')
            .select('symbol,exchange,date,open,high,low,close,volume,updated_at')
            .in('exchange', targetExchanges)
            .eq('symbol', cleanSymbol)
            .order('date', { ascending: false })
            .limit(1),
        client
            .from('stock_technical_indicators')
            .select('symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200,calculated_at')
            .in('exchange', targetExchanges)
            .eq('symbol', cleanSymbol)
            .order('date', { ascending: false })
            .limit(1),
        client
            .from('stock_prices')
            .select('date,open,high,low,close,volume')
            .in('exchange', targetExchanges)
            .eq('symbol', cleanSymbol)
            .order('date', { ascending: false })
            .limit(30),
        readSafeDisclosures(client, cleanSymbol),
    ]);

    const stockRow = stockRes.data?.[0] as any;
    const latestPrice = priceRes.data?.[0] || null;
    if (!stockRow && !latestPrice) return null;

    const exchange = String(stockRow?.exchange || latestPrice?.exchange || 'DFM');
    return {
        fundamentals: {
            symbol: cleanSymbol,
            exchange,
            updated_at: stockRow?.updated_at || latestPrice?.updated_at || null,
            data: {
                country: stockRow?.country || (exchange === 'QSE' ? 'Qatar' : exchange === 'COMMODITIES' ? 'Global' : 'UAE'),
                currency: stockRow?.currency || (exchange === 'QSE' ? 'QAR' : exchange === 'COMMODITIES' ? 'USD' : 'AED'),
                exchange,
                name: stockRow?.name || cleanSymbol,
                Name: stockRow?.name || cleanSymbol,
                name_ar: stockRow?.name_ar || cleanSymbol,
                sector: stockRow?.sector || '',
            },
        },
        latestPrice,
        latestTech: techRes.error ? null : (techRes.data?.[0] || null),
        latestScan: null,
        historicalPrices: histRes.error ? [] : [...(histRes.data || [])].reverse(),
        recentDisclosures,
    };
}

const getPublicTasiStockSnapshot = cache(unstable_cache(async (symbol: string): Promise<PublicStockSnapshotData> => {
    const hf = await fetchSnapshotBundleFromHf(symbol, 'tasi');
    if (hf?.snapshot) return hf.snapshot;
    const cleanSymbol = symbol.toUpperCase().replace(/\.(SR|SA|TADAWUL)$/i, '');
    const candidates = Array.from(new Set([cleanSymbol, `${cleanSymbol}.SR`]));
    const client = getMarketSupabaseClient('tasi');
    const readOrdered = (table: string, fields: string, order: string, limit: number) =>
        client
            .from(table)
            .select(fields)
            .eq('exchange', 'TADAWUL')
            .in('symbol', candidates)
            .order(order, { ascending: false })
            .limit(limit);

    const stocksQuery = async () => {
        const res = await client
            .from('stocks')
            .select('symbol,exchange,name,name_ar,sector,currency')
            .eq('exchange', 'TADAWUL')
            .in('symbol', candidates)
            .limit(1);
        if (!res.error) return res;
        return client
            .from('stocks')
            .select('symbol,exchange,name,sector')
            .eq('exchange', 'TADAWUL')
            .in('symbol', candidates)
            .limit(1);
    };

    const [fund, price, tech, history, scan, stockMeta, recentDisclosures] = await Promise.all([
        readOrdered('stock_fundamentals', 'symbol,exchange,data,updated_at', 'updated_at', 1),
        readOrdered('stock_prices', 'symbol,exchange,date,open,high,low,close,volume,updated_at', 'date', 1),
        readOrdered('stock_technical_indicators', 'symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200', 'date', 1),
        readOrdered('stock_prices', 'date,open,high,low,close,volume', 'date', 30),
        readOrdered('scan_results', 'symbol,exchange,created_at,precision,signal,top_reasons', 'created_at', 1),
        stocksQuery(),
        readSafeDisclosures(client, candidates),
    ]);

    if (fund.error && stockMeta.error) throw new Error('Unable to load public TASI stock fundamentals');
    if (price.error) throw new Error('Unable to verify public TASI stock existence');

    const rawFund = fund.data?.[0] || null;
    const stockRow = (stockMeta.data?.[0] || null) as {
        symbol?: string;
        name?: string;
        name_ar?: string;
        sector?: string;
        currency?: string;
    } | null;
    const latestPrice = price.data?.[0] || null;
    const knownAr = stockRow?.name_ar || SAUDI_STOCK_NAMES_AR[cleanSymbol] || '';
    const knownEn = stockRow?.name || rawFund?.data?.name || rawFund?.data?.Name || '';

    const mergedFundamentals = rawFund || stockRow || latestPrice
        ? {
            ...(rawFund || { symbol: cleanSymbol, exchange: 'TADAWUL', updated_at: null }),
            exchange: 'TADAWUL',
            data: {
                country: 'Saudi Arabia',
                currency: stockRow?.currency || 'SAR',
                ...(rawFund?.data || {}),
                ...(knownEn ? { name: knownEn, Name: knownEn } : {}),
                ...(knownAr ? { name_ar: knownAr } : {}),
                ...(!rawFund?.data?.sector && !rawFund?.data?.Sector && stockRow?.sector ? { sector: stockRow.sector } : {}),
            },
        }
        : null;

    return {
        fundamentals: mergedFundamentals,
        latestPrice,
        latestTech: tech.error ? null : (tech.data?.[0] || null),
        latestScan: scan.error ? null : (scan.data?.[0] || null),
        historicalPrices: history.error ? [] : [...(history.data || [])].reverse(),
        recentDisclosures,
    };
}, ['public-tasi-stock-snapshot-v2'], { revalidate: 604800 }));

const EMPTY_SNAPSHOT: PublicStockSnapshotData = {
    fundamentals: null,
    latestPrice: null,
    latestTech: null,
    latestScan: null,
    historicalPrices: [],
    recentDisclosures: [],
};

const getCachedStockPageBundle = cache(unstable_cache(async (symbol: string, market: MarketMode, preferredExchange = ''): Promise<PublicStockPageBundle> => {
    const cleanEx = preferredExchange.trim().toUpperCase() || undefined;
    const hf = await fetchSnapshotBundleFromHf(symbol, market, cleanEx);
    if (hf?.snapshot) return hf;
    if (market === 'uae' || market === 'qatar' || (cleanEx && (GCC_METALS_EXCHANGES as readonly string[]).includes(cleanEx))) {
        const gccSnap = await getPublicGccMetalsStockSnapshot(symbol, cleanEx).catch(() => null);
        return { snapshot: gccSnap ?? EMPTY_SNAPSHOT, related: null };
    }
    const snapshot = market === 'tasi'
        ? await getPublicTasiStockSnapshot(symbol)
        : await getPublicEgxStockSnapshot(symbol);
    return { snapshot, related: null };
}, ['public-stock-page-bundle-v4'], { revalidate: 604800 }));

export async function getPublicStockSnapshot(symbol: string, market: MarketMode = 'egx', preferredExchange?: string) {
    if (preferredExchange || market === 'uae' || market === 'qatar') {
        const gccSnap = await getPublicGccMetalsStockSnapshot(symbol, preferredExchange).catch(() => null);
        if (gccSnap) return gccSnap;
    }
    if (market === 'tasi') {
        return getPublicTasiStockSnapshot(symbol);
    }
    return getPublicEgxStockSnapshot(symbol);
}

export async function getPublicStockPageBundle(symbol: string, market: MarketMode = 'egx', preferredExchange?: string): Promise<PublicStockPageBundle> {
    return getCachedStockPageBundle(symbol, market, preferredExchange || '');
}
