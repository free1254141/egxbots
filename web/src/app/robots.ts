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
          'OAI-SearchBot',
          'PerplexityBot',
          'Perplexity-User',
          'ClaudeBot',
          'Claude-Web',
          'MistralAI-User',
          'Google-Extended',
          'Applebot-Extended',
          'Bravebot',
          'DuckAssistBot',
          'YouBot'
        ],
        allow: [
          '/',
          '/chat',
          '/markets',
          '/markets/*',
          '/stocks',
          '/stocks/*',
          '/fair-value',
          '/sharia',
          '/disclosures',
          '/scanner/ai',
          '/scanner/technical',
          '/scanner/market',
          '/scanner/backtests',
          '/faq',
          '/news',
          '/blogs',
          '/blogs/*',
          '/reports',
          '/reports/*',
          '/llms.txt',
          '/llms-full.txt'
        ],
        disallow: ['/admin', '/api', '/profile'],
      },
      {
        // SEO-tool / bulk AI-training & scraper crawlers: no search or AI-answer visibility,
        // but heavy crawling across 600+ /stocks/* pages burns ISR Reads & Origin Transfer.
        userAgent: [
          'AhrefsBot',
          'SemrushBot',
          'MJ12bot',
          'DotBot',
          'PetalBot',
          'Bytespider',
          'DataForSeoBot',
          'BLEXBot',
          'Meta-ExternalAgent',
          'anthropic-ai',
          'cohere-ai',
          'CCBot',
          'Amazonbot',
          'FacebookBot',
          'Diffbot',
          'ImagesiftBot',
          'Omgilibot'
        ],
        disallow: '/',
      },
    ],
    sitemap: 'https://egxbots.com/sitemap.xml',
  }
}
