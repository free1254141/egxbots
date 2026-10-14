import { MetadataRoute } from 'next'
import { getPublicMarketClient } from '@/lib/supabase/route-data'
import { getPublicStockDirectory } from '@/lib/seo/stock-directory'
import { canonicalSitemap, publishedBlogEntries, validLastModified } from '@/lib/seo/sitemap-entries'
import { getPublicReports, reportUrl } from '@/lib/social/public-reports'

export const revalidate = 86400;

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
      priority: 0.8,
    },
    {
      url: `${baseUrl}/news`,
      changeFrequency: 'hourly',
      priority: 0.8,
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
      url: `${baseUrl}/disclaimer`,
      changeFrequency: 'monthly',
      priority: 0.3,
    },
  ]

  const reportPages: MetadataRoute.Sitemap = (await getPublicReports()).map(r => ({
    url: baseUrl + reportUrl(r), lastModified: validLastModified(r.updated_at), changeFrequency: 'never', priority: 0.8
  }));
  staticPages.push({ url: baseUrl + '/reports', changeFrequency: 'daily', priority: 0.8 });

  const stocks = await getPublicStockDirectory();
  const stockPages: MetadataRoute.Sitemap = stocks.map(stock => ({
    url: `${baseUrl}/stocks/${stock.symbol.toLowerCase()}`,
    // This is the persisted fundamentals update, not fetch time or a claim
    // about today's close. Do not manufacture timestamps for unknown updates.
    lastModified: validLastModified(stock.updatedAt), changeFrequency: 'daily', priority: .7,
  }));
  const { data: posts, error, count } = await getPublicMarketClient().from('shared_chat_posts')
    .select('slug,is_published,updated_at,created_at', { count: 'exact' }).eq('is_published', true)
    .order('slug', { ascending: true }).limit(2001);
  if (error || !Array.isArray(posts) || posts.length > 2000 || typeof count === 'number' && count > posts.length)
    throw new Error('Unable to load complete published blog sitemap');
  return canonicalSitemap([...staticPages, ...stockPages, ...publishedBlogEntries(posts, baseUrl), ...reportPages]);
}
