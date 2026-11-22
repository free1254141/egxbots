import { MetadataRoute } from 'next'
import { getPublicMarketClient } from '@/lib/supabase/route-data'
import { getPublicStockDirectory, getPublicTasiStockDirectory, getPublicGccMetalsDirectory } from '@/lib/seo/stock-directory'
import { canonicalSitemap, publishedBlogEntries, validLastModified } from '@/lib/seo/sitemap-entries'
import { getPublicReports, reportUrl } from '@/lib/social/public-reports'
import { fetchHfPublicJson } from '@/lib/hf-public-read'

export const revalidate = 604800;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = 'https://egxbots.com'
  
  const staticPages: MetadataRoute.Sitemap = [
    {
      url: baseUrl,
      changeFrequency: 'daily',
      priority: 1.0,
    },
    {
      url: `${baseUrl}/scanner/ai`,
      changeFrequency: 'daily',
      priority: 0.95,
    },
    {
      url: `${baseUrl}/chat`,
      changeFrequency: 'daily',
      priority: 0.95,
    },
    {
      url: `${baseUrl}/stocks`,
      changeFrequency: 'daily',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/fair-value`,
      changeFrequency: 'daily',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/sharia`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/disclosures`,
      changeFrequency: 'hourly',
      priority: 0.95,
    },
    {
      url: `${baseUrl}/scanner/technical`,
      changeFrequency: 'daily',
      priority: 0.85,
    },
    {
      url: `${baseUrl}/scanner/backtests`,
      changeFrequency: 'daily',
      priority: 0.85,
    },
    {
      url: `${baseUrl}/scanner/market`,
      changeFrequency: 'daily',
      priority: 0.85,
    },
    {
      url: `${baseUrl}/blogs`,
      changeFrequency: 'daily',
      priority: 0.85,
    },
    {
      url: `${baseUrl}/blogs/best-egx-stock-analysis-software`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/ai-egyptian-stock-market-analysis`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/egx-telegram-stock-recommendations`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/how-to-invest-in-egyptian-stock-market-beginners`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/egx33-sharia-compliant-stocks-egypt-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/undervalued-egx-stocks-fair-value-calculation`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/real-estate-vs-stocks-egypt-ewanbot-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/best-tasi-ai-stock-analysis-software`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/aramco-2222-rajhi-1120-ai-stock-analysis-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/saudi-tasi-sharia-compliant-stocks-purification-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/gold-silver-xauusd-ai-technical-analysis-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/saudi-tasi-telegram-stock-alerts-ai-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/undervalued-saudi-tasi-stocks-fair-value-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/blogs/uae-dfm-adx-qatar-qse-ai-sharia-stocks-guide`,
      changeFrequency: 'weekly',
      priority: 0.90,
    },
    {
      url: `${baseUrl}/news`,
      changeFrequency: 'hourly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/pricing`,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/b2b`,
      changeFrequency: 'weekly',
      priority: 0.85,
    },
    {
      url: `${baseUrl}/chart`,
      changeFrequency: 'weekly',
      priority: 0.75,
    },
    {
      url: `${baseUrl}/faq`,
      changeFrequency: 'weekly',
      priority: 0.75,
    },
    {
      url: `${baseUrl}/legal-status`,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${baseUrl}/disclaimer`,
      changeFrequency: 'monthly',
      priority: 0.3,
    },
  ]

  const reportPages: MetadataRoute.Sitemap = (await getPublicReports()).map(r => ({
    url: baseUrl + reportUrl(r), lastModified: validLastModified(r.updated_at), changeFrequency: 'never', priority: 0.8
  }));
  staticPages.push({ url: baseUrl + '/reports', changeFrequency: 'daily', priority: 0.8 });

  const saudiLandingPages: MetadataRoute.Sitemap = [
    { url: `${baseUrl}/markets`, changeFrequency: 'daily', priority: 0.90 },
    { url: `${baseUrl}/stocks?market=tasi`, changeFrequency: 'daily', priority: 0.90 },
    { url: `${baseUrl}/scanner/ai?market=tasi`, changeFrequency: 'daily', priority: 0.90 },
    { url: `${baseUrl}/scanner/technical?market=tasi`, changeFrequency: 'daily', priority: 0.85 },
    { url: `${baseUrl}/scanner/market?market=tasi`, changeFrequency: 'daily', priority: 0.85 },
    { url: `${baseUrl}/scanner/backtests?market=tasi`, changeFrequency: 'daily', priority: 0.85 },
    { url: `${baseUrl}/markets/uae`, changeFrequency: 'daily', priority: 0.90 },
    { url: `${baseUrl}/markets/qatar`, changeFrequency: 'daily', priority: 0.90 },
    { url: `${baseUrl}/markets/gold-silver`, changeFrequency: 'daily', priority: 0.90 },
  ];

  const [stocks, tasiStocks, gccMetals] = await Promise.all([
    getPublicStockDirectory(),
    getPublicTasiStockDirectory().catch(() => []),
    typeof getPublicGccMetalsDirectory === 'function'
      ? getPublicGccMetalsDirectory().catch(() => [])
      : Promise.resolve([]),
  ]);
  const stockPages: MetadataRoute.Sitemap = [...stocks, ...tasiStocks, ...gccMetals].map(stock => ({
    url: `${baseUrl}/stocks/${stock.symbol.toLowerCase()}`,
    // This is the persisted fundamentals update, not fetch time or a claim
    // about today's close. Do not manufacture timestamps for unknown updates.
    lastModified: validLastModified('updatedAt' in stock ? stock.updatedAt : undefined), changeFrequency: 'daily', priority: .7,
  }));
  const hfPosts = await fetchHfPublicJson<{ posts?: any[] }>(
    '/api/public/sitemap-posts',
    604800,
    5000,
    ['daily-public-reports']
  );
  let posts: any[] | null = Array.isArray(hfPosts?.posts) ? hfPosts.posts : null;
  if (!posts) {
    const { data, error, count } = await getPublicMarketClient().from('shared_chat_posts')
      .select('slug,is_published,updated_at,created_at', { count: 'exact' }).eq('is_published', true)
      .order('slug', { ascending: true }).limit(2001);
    if (error || !Array.isArray(data) || data.length > 2000 || (typeof count === 'number' && count > data.length))
      throw new Error('Unable to load complete published blog sitemap');
    posts = data;
  }
  return canonicalSitemap([...staticPages, ...saudiLandingPages, ...stockPages, ...publishedBlogEntries(posts, baseUrl), ...reportPages]);
}
