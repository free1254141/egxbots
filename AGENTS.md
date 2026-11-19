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

## ⚡ Vercel CPU Conservation & Hugging Face Offloading Playbook

> **MANDATORY READ:** `docs/VERCEL_ZERO_CPU_ARCHITECTURE.md` is the canonical reference for the zero-CPU Vercel architecture (edge rewrites, 1-week ISR, tag-based Run-1/Run-2 invalidation, client-side freshness guards, HF cache maps, postgrest 0.16.11 rules) and its design-pattern glossary. Every agent must follow its checklist before adding or changing any page, API route, cache, or query.

To stay comfortably inside Vercel Hobby limits (Fluid Active CPU, Fast Origin Transfer, and ISR Writes) while keeping latency low, ALL new features and updates MUST follow these architecture, algorithmic, and security standards:

### 1. HF-First Compute & Rewrite Routing (`0` Vercel Active CPU)
- Keep Vercel focused strictly on SSR/ISR UI pages, auth session cookies, and lightweight Edge/BFF glue that cannot run elsewhere.
- Route high-traffic API endpoints, webhooks, email campaigns, AI inference, market scanners, candles, symbol search, quota checks, and analytics directly to the FastAPI backend on Hugging Face (`weeasdwee-ai-bot.hf.space`) via `beforeFiles` rewrites in `web/next.config.js` (gated by `OFFLOAD_TO_HF !== "false"`).
- Using `beforeFiles` rewrites bypasses Next.js App Router serverless functions (`0` Fluid Active CPU) while preserving local `route.ts` fallback files for Jest contract tests and `OFFLOAD_TO_HF=false` debugging.
- Never call heavy database aggregations or LLM loops inside Vercel Server Functions when Hugging Face + Supabase can execute them once and cache the result.

### 2. Algorithmic Performance & Smart Caching
- **Bounded LRU + TTL + SingleFlight (`api/perf_utils.py`):** Protect every hot backend read path with `BoundedTTLCache` (O(1) `OrderedDict` LRU eviction, bounded memory, automatic TTL expiry) paired with `SingleFlight` request coalescing so concurrent burst traffic collapses into one upstream query.
- **Parallel Independent I/O:** Use `ThreadPoolExecutor` / `asyncio.gather` whenever an endpoint needs multiple independent reads (e.g. `user/quota`: profile + subscriptions + usage counters + founding-member count in parallel).
- **Debounced Revalidation (`api/cache_invalidation.py`):** Deduplicate cache tags and respect `REVALIDATE_COOLDOWN_SECONDS` (default `120s`) before calling Vercel `/api/revalidate` so clustered pipeline steps never trigger redundant ISR rebuilds.
- **Edge HTTP Caching Headers:** Public unauthenticated daily payloads MUST return `Cache-Control: public, s-maxage=900, stale-while-revalidate=3600` (with appropriate `Vary` when entitlement affects output); authenticated or user-specific payloads MUST return `Cache-Control: private, no-store, max-age=0`.

### 3. Compact Database Queries & Smart Projections
- **Targeted Column Projections:** Never run `SELECT *` on large or medium tables (`stock_prices`, `recommendations`, `scan_results`, `user_usage`, `telemetry_events`, `market_cache`). Always select only the exact columns serialized in the response.
- **Strict Bounded Limits & Indexed Filters:** Every list/search query MUST apply indexed equality/range filters and explicit `.limit(n)` caps (clamp user-supplied `limit` parameters server-side).
- **Zero-Allocation Hot Paths:** Normalize symbols, validate inputs with precompiled regexes, and strip sensitive or unneeded fields before caching or JSON serialization.

### 4. Zero-Trust Request & Entitlement Security
- **Verified Identity Only (`resolve_verified_viewer`):** Never trust client-supplied `is_pro`, `user_id`, or `tier` query/body flags on HF endpoints. Extract bearer tokens or `@supabase/ssr` cookies via `api/agentic_chat/auth_guard.py`, verify via Supabase Auth (`get_user` cached briefly by SHA-256 token hash), and verify active entitlement (`subscriptions` table + `paymentsEnabled` gate).
- **Timing-Safe Secrets & Input Sanitization:** Compare internal keys (`x-admin-key`) with `hmac.compare_digest` (failing closed when unset), verify webhook signatures (`svix` HMAC on Resend webhooks), and validate ticker/exchange/metadata keys with strict regex allowlists.
- **Per-User Isolation:** Never mix user-specific quota, portfolio, or unlocked PRO fields into shared public cache keys.

## 💳 Subscription Tiers, Capability Isolation & Payment/FRA Architecture

- **Canonical Reference:** Always follow `docs/PRICING_AND_ENTITLEMENTS_ARCHITECTURE.md` before changing plans, pricing UI, quotas, checkout triggers, or Telegram VIP access.
- **3-Tier Retail Split:** `chat_only` (100 EGP / 10 SAR), `vip_only` (100 EGP / 10 SAR), and `pro` Full Bundle Hero (150 EGP/mo, 750 EGP/6m, 1,350 EGP/1y; 15 / 75 / 135 SAR; EasyKash `tasi` billing mapped via `_SAUDI_SAR_EXCHANGE_MAP`), plus `lifetime` (2,250 EGP / 225 SAR).
- **Founders 50 & 100 EGP Protection:** Applies strictly to the Full Bundle (`pro`, `pro_6m`, `pro_1y`); never grant Founders status or discounted Full Bundle rates from `chat_only` or `vip_only`. Preserve the `COALESCE(new.customer_note, '') NOT ILIKE 'Market: tasi%'` bypass in `public.check_founders_checkout_amount()`.
- **Strict Capability Isolation:** Gate AI Chat (`350`/mo), Vision AI uploads (`403 PRO_REQUIRED`), `15`-stock portfolio (`record_portfolio_transaction`), portfolio rebalance, and scheduled automations strictly on `has_chat_pro` / `egx_chat_pro_active`. Gate VIP Telegram channel invites strictly on `has_vip_access`. Reserve `is_pro` / `egx_pro_active` solely for shared zero-delay site signals and paid backtests.
- **EasyKash-Only & FRA Compliance:** EasyKash (`DirectPayV1/pay`) is the sole approved payment gateway — never promote InstaPay or manual external wallets. Keep all copy strictly SaaS analytical tooling for personal research/education per `docs/fra-submission-dossier/` (no advisory/recommendation claims or profit guarantees).


