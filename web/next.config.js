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

    const beforeFiles = isPythonChatbot
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
      : [];

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
        // Cache public stock pages across Vercel Edge CDN for 24h with stale-while-revalidate
        source: '/stocks/:symbol*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=14400, s-maxage=86400, stale-while-revalidate=86400',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
            value: 'public, s-maxage=86400, stale-while-revalidate=86400',
          },
          {
            key: 'CDN-Cache-Control',
            value: 'public, s-maxage=86400, stale-while-revalidate=86400',
          },
        ],
      },
      {
        // Static pricing page
        source: '/pricing',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=86400, s-maxage=604800, stale-while-revalidate=86400',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
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
            value: 'public, max-age=14400, s-maxage=86400, stale-while-revalidate=86400',
          },
          {
            key: 'Vercel-CDN-Cache-Control',
            value: 'public, s-maxage=86400, stale-while-revalidate=86400',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;