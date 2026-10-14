import 'server-only';
import { cache } from 'react';
import { unstable_cache } from 'next/cache';
import { getPublicMarketClient } from '@/lib/supabase/route-data';
import { DAILY_CACHE_TAGS } from '@/lib/cache/daily';

// Keep origin reads inside the shared Next cache boundary. The market-query
// cache's cold-fill fetch uses no-store; executing it directly while generating
// an ISR stock page can otherwise turn a static-render bailout into a 503.
export const getPublicStockSnapshot = cache(unstable_cache(async (symbol: string) => {
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
}, ['public-egx-stock-snapshot-v1'], { revalidate: 3600, tags: [DAILY_CACHE_TAGS.market, DAILY_CACHE_TAGS.recommendations] }));
