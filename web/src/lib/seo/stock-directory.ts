import 'server-only';
import { unstable_cache } from 'next/cache';
import { getPublicMarketClient } from '@/lib/supabase/route-data';
import { DAILY_CACHE_TAGS } from '@/lib/cache/daily';
import { normalizeStockDirectory } from './sitemap-entries';

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
