/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  async redirects() {
    return [
      {
        source: '/scanner/comparison',
        destination: '/scanner/technical',
        permanent: true,
      },
      {
        source: '/portfolio',
        destination: '/profile#portfolio',
        permanent: false,
      },
      {
        source: '/stocks/:symbol.:ext(sr|sa|tadawul|SR|SA|TADAWUL)',
        destination: '/stocks/:symbol',
        permanent: true,
      },
    ];
  },

  async rewrites() {
    console.log("Using Python Path:", process.env.PYTHON_PATH || "Default System Python");
    // Rewrites must target the Python backend only — never the Next.js origin.
    let backendUrl =
      process.env.TRADING_SIGNALS_API_URL ||
      process.env.PYTHON_BACKEND_URL ||
      (process.env.NODE_ENV === "production"
        ? "https://weeasdwee-ai-bot.hf.space"
        : "http://127.0.0.1:8000");
    if (/localhost:3000|:3000\b/.test(backendUrl)) {
      console.warn(
        "[next.config] Ignoring backend URL pointing at Next.js dev server; using http://127.0.0.1:8000"
      );
      backendUrl = "http://127.0.0.1:8000";
    }
    if (process.env.NODE_ENV === "production" && (/localhost|127\.0\.0\.1/.test(backendUrl))) {
      backendUrl = "https://weeasdwee-ai-bot.hf.space";
    }
    console.log("Using Trading Signals Backend URL:", backendUrl);
    const BACKEND_URL = backendUrl.replace(/\/$/, "");

    // Permanent Python Agentic Chatbot (HF Space in production, local in development)
    const defaultChatbotBackend = process.env.NODE_ENV === "production" ? "hf" : "local";
    const chatbotBackend = (process.env.CHATBOT_BACKEND || defaultChatbotBackend).toLowerCase().trim();
    const isPythonChatbot = chatbotBackend !== "vercel";
    const pythonChatbotDestination = chatbotBackend === "local"
      ? "http://127.0.0.1:8000/api/ai_chat/:path*"
      : `${BACKEND_URL}/api/ai_chat/:path*`;
    const pythonChatbotExact = chatbotBackend === "local"
      ? "http://127.0.0.1:8000/api/ai_chat"
      : `${BACKEND_URL}/api/ai_chat`;
    console.log(`[next.config] Chatbot backend configured: ${chatbotBackend} (isPython: ${isPythonChatbot}) -> ${pythonChatbotDestination}`);

    const offloadEnabled = process.env.OFFLOAD_TO_HF !== "false";
    const offloadBeforeFiles = offloadEnabled
      ? [
          { source: '/api/symbols/search', destination: `${BACKEND_URL}/api/symbols/search` },
          { source: '/api/symbols/countries', destination: `${BACKEND_URL}/api/symbols/countries` },
          { source: '/api/recommendations/chart-markers', destination: `${BACKEND_URL}/api/recommendations/chart-markers` },
          { source: '/api/ai_bot/recommendations', destination: `${BACKEND_URL}/api/ai_bot/recommendations` },
          { source: '/api/ai_bot/candles', destination: `${BACKEND_URL}/api/ai_bot/candles` },
          { source: '/api/user/quota', destination: `${BACKEND_URL}/api/user/quota` },
          { source: '/api/analytics/events', destination: `${BACKEND_URL}/api/analytics/events` },
          { source: '/api/short-swings/:path*', destination: `${BACKEND_URL}/api/short-swings/:path*` },
          { source: '/api/short-swings', destination: `${BACKEND_URL}/api/short-swings` },
          { source: '/api/scanner/intraday-session', destination: `${BACKEND_URL}/api/scanner/intraday-session` },
          { source: '/api/market/status', destination: `${BACKEND_URL}/api/market/status` },
          { source: '/api/market/proof', destination: `${BACKEND_URL}/api/market/proof` },
          { source: '/api/market/fundamentals', destination: `${BACKEND_URL}/api/market/fundamentals` },
          { source: '/api/market/recommendation-counts', destination: `${BACKEND_URL}/api/market/recommendation-counts` },
          { source: '/api/scan/signal-performance', destination: `${BACKEND_URL}/api/scan/signal-performance` },
          { source: '/api/scan/ai', destination: `${BACKEND_URL}/api/scan/ai` },
          { source: '/api/disclosures/pdf/:path*', destination: `${BACKEND_URL}/api/disclosures/pdf/:path*` },
          { source: '/api/disclosures/image/:itemId', destination: `${BACKEND_URL}/api/disclosures/image/:itemId` },
          { source: '/api/disclosures', destination: `${BACKEND_URL}/api/disclosures` },
          { source: '/api/marketing/:path*', destination: `${BACKEND_URL}/marketing/:path*` },
          // Public / SEO / Scanner / Market offload (0ms Vercel Fluid Active CPU)
          { source: '/api/public/:path*', destination: `${BACKEND_URL}/api/public/:path*` },
          { source: '/api/market/fair-value', destination: `${BACKEND_URL}/api/market/fair-value` },
          { source: '/api/market/breadth', destination: `${BACKEND_URL}/api/market/breadth` },
          { source: '/api/market/scan-settings', destination: `${BACKEND_URL}/api/market/scan-settings` },
          { source: '/api/market/macro-correlation/:path*', destination: `${BACKEND_URL}/api/market/macro-correlation/:path*` },
          { source: '/api/market/ai-signals', destination: `${BACKEND_URL}/api/market/ai-signals` },
          { source: '/api/scan/technical', destination: `${BACKEND_URL}/api/scan/technical` },
          { source: '/api/scan/news/stats', destination: `${BACKEND_URL}/api/scan/news/stats` },
          { source: '/api/scan/news', destination: `${BACKEND_URL}/api/scan/news` },
          { source: '/api/scan/similarity/published', destination: `${BACKEND_URL}/api/scan/similarity/published` },
          { source: '/api/scan/sectors/:path*', destination: `${BACKEND_URL}/api/scan/sectors/:path*` },
          { source: '/api/scan/traps', destination: `${BACKEND_URL}/api/scan/traps` },
          { source: '/api/scan/unusual-activity', destination: `${BACKEND_URL}/api/scan/unusual-activity` },
          { source: '/api/egx30/:path*', destination: `${BACKEND_URL}/api/egx30/:path*` },
          { source: '/api/recommendations/benchmark', destination: `${BACKEND_URL}/api/recommendations/benchmark` },
          { source: '/api/recommendations/events', destination: `${BACKEND_URL}/api/recommendations/events` },
          { source: '/api/chart-events', destination: `${BACKEND_URL}/api/chart-events` },
          { source: '/api/models/list', destination: `${BACKEND_URL}/api/models/list` },
          { source: '/api/models/local', destination: `${BACKEND_URL}/api/models/local` },
          { source: '/api/adaptive/recommendation', destination: `${BACKEND_URL}/api/adaptive/recommendation` },
          { source: '/api/saudi/backtests', destination: `${BACKEND_URL}/api/saudi/backtests` },
          { source: '/api/ai_bot/list', destination: `${BACKEND_URL}/api/ai_bot/list` },
          { source: '/api/ai_bot/model_cards', destination: `${BACKEND_URL}/api/ai_bot/model_cards` },
          { source: '/api/symbols/inventory', destination: `${BACKEND_URL}/symbols/inventory` },
          { source: '/api/symbols/synced', destination: `${BACKEND_URL}/symbols/synced` },
          { source: '/api/predict', destination: `${BACKEND_URL}/predict` },
          { source: '/api/health', destination: `${BACKEND_URL}/health` },
          // Authenticated User, Portfolio, Automations, Alerts & Payment offload (cookie + Bearer JWT)
          { source: '/api/portfolio/:path*', destination: `${BACKEND_URL}/api/portfolio/:path*` },
          { source: '/api/portfolio', destination: `${BACKEND_URL}/api/portfolio` },
          { source: '/api/user/portfolio/rebalance', destination: `${BACKEND_URL}/api/user/portfolio/rebalance` },
          { source: '/api/user/scanner-alerts', destination: `${BACKEND_URL}/api/user/scanner-alerts` },
          { source: '/api/profile/telegram-pro', destination: `${BACKEND_URL}/api/profile/telegram-pro` },
          { source: '/api/automations/:path*', destination: `${BACKEND_URL}/api/automations/:path*` },
          { source: '/api/automations', destination: `${BACKEND_URL}/api/automations` },
          { source: '/api/chart-workspace', destination: `${BACKEND_URL}/api/chart-workspace` },
          { source: '/api/affiliate/me', destination: `${BACKEND_URL}/api/affiliate/me` },
          { source: '/api/b2b/license', destination: `${BACKEND_URL}/api/b2b/license` },
          { source: '/api/b2b/trial', destination: `${BACKEND_URL}/api/b2b/trial` },
          { source: '/api/subscription/trial', destination: `${BACKEND_URL}/api/subscription/trial` },
          { source: '/api/support/message', destination: `${BACKEND_URL}/api/support/message` },
          { source: '/api/support/messages', destination: `${BACKEND_URL}/api/support/messages` },
          { source: '/api/payment/:path*', destination: `${BACKEND_URL}/api/payment/:path*` },
          { source: '/api/backtests/:backtestId/trades', destination: `${BACKEND_URL}/api/backtests/:backtestId/trades` },
          { source: '/api/backtests', destination: `${BACKEND_URL}/api/backtests` },
          { source: '/api/chat/share/:slug', destination: `${BACKEND_URL}/api/chat/share/:slug` },
          { source: '/api/chat/share', destination: `${BACKEND_URL}/api/chat/share` },
        ]
      : [];

    const beforeFiles = [
      ...(isPythonChatbot
        ? [
            {
              source: '/api/ai-chat/:path*',
              destination: pythonChatbotDestination,
            },
            {
              source: '/api/ai-chat',
              destination: pythonChatbotExact,
            },
          ]
        : []),
      ...offloadBeforeFiles,
    ];

    return {
      beforeFiles,
      afterFiles: [
      // Bypass rewrites to keep backtests, scan alerts, and admin proxy routes local
      {
        source: '/api/backtests/:path*',
        destination: '/api/backtests/:path*',
      },
      {
        source: '/api/scan/alerts/:path*',
        destination: '/api/scan/alerts/:path*',
      },
      {
        source: '/api/admin/:path*',
        destination: '/api/admin/:path*',
      },
      {
        source: '/api/support/:path*',
        destination: '/api/support/:path*',
      },
      {
        source: '/api/portfolio/:path*',
        destination: '/api/portfolio/:path*',
      },
      {
        source: '/api/automations/:path*',
        destination: '/api/automations/:path*',
      },
      {
        source: '/api/telegram/:path*',
        destination: `${BACKEND_URL}/api/telegram/:path*`,
      },
      {
        source: '/api/marketing/:path*',
        destination: `${BACKEND_URL}/marketing/:path*`,
      },
      {
        source: '/api/ai-chat/:path*',
        destination: pythonChatbotDestination,
      },
      {
        source: '/api/ai-chat',
        destination: pythonChatbotExact,
      },
      {
        source: '/api/disclosures/:path*',
        destination: '/api/disclosures/:path*',
      },
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/:path*`,
      },
      // Trading signals specific endpoints
      {
        source: '/signals/:path*',
        destination: `${BACKEND_URL}/signals/:path*`,
      },
      {
        source: '/markets/:path*',
        destination: `${BACKEND_URL}/markets/:path*`,
      },
      {
        source: '/alerts/:path*',
        destination: `${BACKEND_URL}/alerts/:path*`,
      },
      {
        source: '/strategies/:path*',
        destination: `${BACKEND_URL}/strategies/:path*`,
      },
      {
        source: '/backtest',
        destination: `${BACKEND_URL}/backtest`,
      },
      {
        source: '/backtests/:path*',
        destination: `${BACKEND_URL}/backtests/:path*`,
      },
      {
        source: '/docs',
        destination: `${BACKEND_URL}/docs`,
      },
      {
        source: '/openapi.json',
        destination: `${BACKEND_URL}/openapi.json`,
      },
      // Proxy specific top-level routes to backend
      {
        source: '/symbols/:path*',
        destination: `${BACKEND_URL}/symbols/:path*`,
      },
      {
        source: '/scan/:path*',
        destination: `${BACKEND_URL}/scan/:path*`,
      },
      {
        source: '/predict',
        destination: `${BACKEND_URL}/predict`,
      },
      {
        source: '/models/:path*',
        destination: `${BACKEND_URL}/models/:path*`,
      },
      {
        source: '/news',
        destination: `${BACKEND_URL}/news`,
      },
      {
        source: '/price',
        destination: `${BACKEND_URL}/price`,
      },
      {
        source: '/health',
        destination: `${BACKEND_URL}/health`,
      },
      {
        source: '/positions/:path*',
        destination: `${BACKEND_URL}/positions/:path*`,
      },
      {
        source: '/bot/:path*',
        destination: `${BACKEND_URL}/bot/:path*`,
      },
    ],
  };
},
compress: true,
  poweredByHeader: false,

  async headers() {
    return [
      {
        // Cache public stock pages across Vercel Edge CDN for 7 days (weekend-proof), invalidated via /api/revalidate
        source: '/stocks/:symbol*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=3600, s-maxage=604800, stale-while-revalidate=2592000',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=2592000, stale-if-error=2592000',
          },
          {
            key: 'CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=2592000',
          },
        ],
      },
      {
        // Static pricing page (revalidate in browser on deploy, keep 7d Vercel Edge CDN cache)
        source: '/pricing',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=0, must-revalidate',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=86400',
          },
          {
            key: 'CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=86400',
          },
        ],
      },
      {
        // Public market overview and directories
        source: '/(fair-value|sharia|disclosures|scanner/technical)',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=3600, s-maxage=604800, stale-while-revalidate=2592000',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=2592000, stale-if-error=2592000',
          },
          {
            key: 'CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=2592000',
          },
        ],
      },
      {
        // Public reports, news, and backtest track-record pages (weekend-proof 7-day CDN cache)
        source: '/(reports|reports/:path*|news|scanner/backtests|track-record)',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=3600, s-maxage=604800, stale-while-revalidate=2592000',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=2592000, stale-if-error=2592000',
          },
          {
            key: 'CDN-Cache-Control',
            value: 'public, s-maxage=604800, stale-while-revalidate=2592000',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;