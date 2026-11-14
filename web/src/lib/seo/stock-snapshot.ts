import 'server-only';
import { cache } from 'react';
import { unstable_cache } from 'next/cache';
import {
    getPublicMarketClient,
    getMarketSupabaseClient,
    type MarketMode,
} from '@/lib/supabase/route-data';
import { DAILY_CACHE_TAGS } from '@/lib/cache/daily';
import { SAUDI_STOCK_NAMES_AR } from '@/lib/saudi-stocks';

// Keep origin reads inside the shared Next cache boundary. The market-query
// cache's cold-fill fetch uses no-store; executing it directly while generating
// an ISR stock page can otherwise turn a static-render bailout into a 503.
const getPublicEgxStockSnapshot = cache(unstable_cache(async (symbol: string) => {
    const client = getPublicMarketClient();
    const read = (table: string, fields: string, order: string, limit: number) => client.from(table).select(fields)
        .eq('exchange', 'EGX').eq('symbol', symbol).order(order, { ascending: false }).limit(limit);
    const [fund, price, tech, history, scan] = await Promise.all([
        read('stock_fundamentals', 'symbol,exchange,data,updated_at', 'updated_at', 1),
        read('stock_prices', 'symbol,exchange,date,open,high,low,close,volume,updated_at', 'date', 1),
        read('stock_technical_indicators', 'symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200,calculated_at', 'date', 1),
        read('stock_prices', 'date,open,high,low,close,volume', 'date', 30),
        read('scan_results', 'symbol,exchange,created_at,precision,signal,top_reasons', 'created_at', 1),
    ]);
    if (fund.error) throw new Error('Unable to load public stock fundamentals');
    if (price.error) throw new Error('Unable to verify public stock existence');
    if (tech.error || history.error || scan.error) throw new Error('Unable to load a complete public stock snapshot');
    return { fundamentals: fund.data?.[0] || null, latestPrice: price.data?.[0] || null,
        latestTech: tech.data?.[0] || null, latestScan: scan.data?.[0] || null,
        historicalPrices: [...(history.data || [])].reverse() };
}, ['public-egx-stock-snapshot-v1'], { revalidate: 86400,
    tags: [DAILY_CACHE_TAGS.market, DAILY_CACHE_TAGS.recommendations] }));

const getPublicTasiStockSnapshot = cache(unstable_cache(async (symbol: string) => {
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

    const [fund, price, tech, history, scan, stockMeta] = await Promise.all([
        readOrdered('stock_fundamentals', 'symbol,exchange,data,updated_at', 'updated_at', 1),
        readOrdered('stock_prices', 'symbol,exchange,date,open,high,low,close,volume,updated_at', 'date', 1),
        readOrdered('stock_technical_indicators', 'symbol,exchange,date,close,change_pct,adx_14,rsi_14,macd,macd_signal,ema_50,ema_200,sma_50,sma_200', 'date', 1),
        readOrdered('stock_prices', 'date,open,high,low,close,volume', 'date', 30),
        readOrdered('scan_results', 'symbol,exchange,created_at,precision,signal,top_reasons', 'created_at', 1),
        stocksQuery(),
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
    };
}, ['public-tasi-stock-snapshot-v1'], { revalidate: 86400,
    tags: [DAILY_CACHE_TAGS.market, DAILY_CACHE_TAGS.recommendations] }));

export async function getPublicStockSnapshot(symbol: string, market: MarketMode = 'egx') {
    if (market === 'tasi') {
        return getPublicTasiStockSnapshot(symbol);
    }
    return getPublicEgxStockSnapshot(symbol);
}
