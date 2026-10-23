import { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/admin', '/api', '/profile'],
      },
      {
        userAgent: [
          'GPTBot',
          'ChatGPT-User',
          'PerplexityBot',
          'ClaudeBot',
          'Google-Extended',
          'Applebot-Extended',
          'cohere-ai',
          'OAI-SearchBot'
        ],
        allow: [
          '/',
          '/stocks',
          '/stocks/*',
          '/scanner/ai',
          '/scanner/technical',
          '/scanner/market',
          '/scanner/backtests',
          '/faq',
          '/news',
          '/blogs',
          '/llms.txt',
          '/llms-full.txt'
        ],
        disallow: ['/admin', '/api', '/profile'],
      },
      {
        // SEO-tool / bulk scrapers: no search or AI-answer visibility, but each
        // crawl of /stocks/* can trigger an on-demand render (Vercel CPU).
        userAgent: [
          'AhrefsBot',
          'SemrushBot',
          'MJ12bot',
          'DotBot',
          'PetalBot',
          'Bytespider',
          'DataForSeoBot',
          'BLEXBot'
        ],
        disallow: '/',
      },
    ],
    sitemap: 'https://egxbots.com/sitemap.xml',
  }
}
