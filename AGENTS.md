# Repository Agent Instructions

These instructions apply to the entire repository, including AI assistants, reviewers and delegated agents. Nested AGENTS.md files add module-specific rules. Follow the user's requested scope; do not change production behavior merely because an optimization is suggested.

## Resource-conscious investigation

- Start with local code, `rg`, git diffs, existing test results and available status records. Reuse results within the task instead of repeating remote reads.
- Supabase Log Query measures logs scanned while reading; it is not database query count or visitor bandwidth. Log Ingestion measures generated logs. Do not attribute a usage spike to a particular actor without evidence.
- Do not open or query remote logs during routine reviews, successful builds or healthy monitoring. Query logs only for a specific failure that simpler status checks cannot explain.
- For an incident, start with one project, one relevant service and an explicit 15-minute interval around the failure; widen to at most 60 minutes initially if needed. Convert Cairo incident times to the requested timezone explicitly. Longer windows require a concrete diagnostic reason, not another user approval if investigation is already authorized.
- Filter by request/job ID, severity or endpoint where supported. A row LIMIT does not necessarily limit bytes scanned. Never repeatedly scan the same interval or all projects/services just to check progress.
- Prefer a narrowly filtered `daily_job_runs` read for job status over reading runtime logs. Select only required fields and rows. Stop polling at a terminal state; use bounded retries, backoff and in-flight deduplication.
- Do not dump entire price/history tables to answer a count or status question. Use bounded date/symbol filters, aggregates and targeted projections. Never print secrets or full environment files.

## Daily data and caching

- Reuse the existing HF daily pipeline and Vercel daily cache/tag invalidation for shared public market data. Do not add per-visitor daily calculations, LLM generation or database refresh jobs.
- Invalidate only affected tags after the relevant successful pipeline stage; do not flush or warm every cache on each diagnostic check or deployment.
- Private account, quota, payment and entitlement data must remain authenticated and isolated per user. Never apply shared public caching to them or weaken RLS/auth to reduce requests.
- Prefer explicit refresh events for public daily data. Network polling must have a real freshness requirement, be bounded, pause in hidden tabs where appropriate and stop when work completes.
- Distinguish local UI timers and active-stream keepalives from database/network polling before proposing their removal.
- Preserve error, security and operational audit logging. Do not disable logging, change database log settings or remove useful evidence merely to reduce usage.

## AI tools, verification and deployments

- Use deterministic checks and fixtures before paid/live LLM, image, video, search or inference calls. Reuse an existing approved asset/report; do not regenerate it just to verify publishing.
- Do not run daily production jobs, training, large backtests, cache rebuilds or live provider suites as ordinary smoke tests. If genuinely necessary and in scope, use one bounded case with explicit limits and no uncontrolled retries.
- Run the smallest relevant offline tests first. Perform a full production build only when runtime/build changes justify it, normally once after the final changes. Instructions/docs-only changes need a diff/consistency check, not a build or paid tool call.
- Batch related deployments. Do not manually redeploy/restart HF for documentation-only changes. Do not repeatedly check unchanged deployment state; reuse revision/status results and back off.
- Coordinate delegated work so agents do not independently repeat the same remote query, live test or generation. Share compact findings rather than large logs.
- Before an external call, determine the question it answers, the smallest scope and whether an existing result already answers it. Report measured savings separately from estimates; never promise a percentage without measurements.

## 🛡️ DNS & Infrastructure Configuration (Vercel Origin Direct)

- **Domain & Nameservers:**
  * Authoritative Nameservers are managed directly on Vercel: `ns1.vercel-dns.com` and `ns2.vercel-dns.com`.
  * **CRITICAL Egyptian ISP Guard:** Never proxy `egxbots.com` through Cloudflare's shared free IP pools (`104.21.x.x` / `172.67.x.x`). Egyptian telecommunications providers (WE / Telecom Egypt, Vodafone) filter and drop traffic to these Cloudflare free ranges at the DPI level, causing fatal `ERR_CONNECTION_TIMED_OUT` for Egyptian visitors.
  * DNS resolves directly to Vercel Anycast edge IPs (`76.76.21.21`, `216.198.79.1`).
  * Cache and quota protection rely on Next.js 15 Incremental Static Regeneration (ISR) and Vercel Data Cache (`Cache-Control: public, max-age=14400`), which serve public stock pages directly from Vercel's global edge without invoking backend functions on cache hits.
- **Backend & ML Services (Hugging Face):** Python FastAPI backend (`weeasdwee/AI_BOT`) executes heavy market jobs and Telegram bots.
- **Database & Auth (Supabase):** PostgreSQL with Row-Level Security, persistent storage, and authentication.
- **Email Services (Resend & ImprovMX):** Outbound emails via Resend (DKIM `resend._domainkey`), inbound via ImprovMX MX.
- Full architectural reference is documented in `docs/SYSTEM_ARCHITECTURE_AND_CDN_EDGE.md`.

## Email Campaign Reporting Rule

- Whenever an email batch or campaign is dispatched, ALWAYS automatically report the complete live analytics breakdown immediately after dispatch without waiting for the user to request it:
  1. Total cumulative emails sent across all campaigns and database records.
  2. Total opened emails and open rate percentage (`open_rate = opened / total * 100`).
  3. Total clicks and conversions (`click_rate`).
  4. Bounced/failed count.
  5. Detailed list of users who opened and clicked (with timestamps).

## 🚫 Strict Git Push Rule (No Automatic Git Push)

- **NEVER** push changes to Git (`git push`) automatically under any circumstances.
- You must ALWAYS wait for the user to explicitly request or approve pushing to Git (e.g., "ارفع", "ادفع لجيت", "git push").
- All local edits, commits, and builds remain strictly local until explicit user authorization to push.

## 🚀 Hugging Face Deployment Rule (Python Backend Only)

- When deploying or syncing updates to the Hugging Face Space (`weeasdwee/AI_BOT`), **ONLY push updated Python files (`.py`)** and backend configuration files (e.g. `api/`, `jobs/`, `scripts/`, `requirements*.txt`, `daily_job_config.json`, `Dockerfile`).
- **NEVER** push frontend Next.js files (`web/`), UI assets/images, Android APKs, docs, or non-Python packages to Hugging Face. The HF Space runs the Python backend & bots only.

## AI Chat Architecture (Agentic Function Calling)

- All user chat queries are routed permanently through the pure LLM-driven Agentic architecture in the Python FastAPI backend (`api/agentic_chat/`), running on Hugging Face Space (`weeasdwee-ai-bot.hf.space`) in production and `http://127.0.0.1:8000` locally, completely eliminating Vercel Active CPU. Next.js proxies/rewrites `/api/ai-chat` directly to the Python backend.
- DeepSeek-V3 determines user intent and selects from the 9 available tools in parallel (`get_stock`, `get_stock_levels`, `manage_portfolio`, `get_market`, `get_recommendations`, `get_technical_scan`, `get_accumulation_stocks`, `get_news`, `get_comparison`).
- Do NOT re-introduce brittle regex intent routers, rigid keyword blocklists, or mechanical symbol substitutions (e.g., swapping `ADRI` for `ADCI`) that break Egyptian dialect, Nile market stocks, or multi-turn queries.
- Tool executions must always query Supabase directly with explicit column projections and strict `limit()` clauses.
- Public read-only tool results (`get_stock`, `get_market`, `get_recommendations`, `get_technical_scan`, `get_news`, `get_fair_value`, `get_sharia_cleanser`, ...) are cached per Cairo trading day in `web/src/lib/ai/tool-result-cache.ts`. Never add portfolio, alert, automation or live-quote tools to that allowlist: they read `userId` or must stay intraday. Disable the cache with `TOOL_RESULT_CACHE=off` if it ever misbehaves.
- Detailed architecture, Python backend engine (`api/agentic_chat/`), and historical reviews are in `docs/chatbot-python-agentic-architecture-2026-11-10.md`, `docs/chatbot-current-architecture.md`, and `docs/chatbot-agentic-architecture-2026-10-08.md`.

## Google Search Console & SEO / GEO Intelligence

- Official API integration via Service Account (`egxbots-seo@neon-dryad-454519-r2.iam.gserviceaccount.com`).
- Full documentation and usage guide: `docs/GOOGLE_SEARCH_CONSOLE_INTEGRATION.md`.
- Tool for immediate query, ranking, and opportunity auditing:
  ```bash
  python scripts/seo/gsc_audit.py --action wins
  ```
- Before creating or modifying public SEO/GEO routes, consult `gsc_audit.py` to identify high-impression / low-CTR pages (e.g., stock symbols with thousands of impressions on Google page 1).

The current resource review and prioritized implementation candidates are in `docs/resource-usage-review-2026-10-05.md`.
