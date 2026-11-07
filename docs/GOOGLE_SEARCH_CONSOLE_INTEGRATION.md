# Google Search Console (GSC) & SEO/GEO Integration Guide

> **Target Site:** `https://egxbots.com/`  
> **Status:** Active & Connected via Official Google Search Console API  
> **Primary Audience:** Developers, Technical Marketers, and AI Coding Agents (Antigravity, Cursor, Claude Code, GitHub Copilot).

---

## 1. Overview & Architecture

This repository is integrated with **Google Search Console** to enable continuous programmatic monitoring of organic search traffic, keyword rankings, indexing coverage, and Generative Engine Optimization (GEO) for AI search engines (ChatGPT Search, Perplexity, Google Gemini / AI Overviews).

```
   Google Search Console (egxbots.com)
                 │
                 ▼ (REST API v1 / Webmasters)
     Service Account Auth (JSON Key)
                 │
                 ▼
   scripts/seo/gsc_audit.py ─────────► AI Agents & Developers
                 │
                 ▼
     Actionable SEO/GEO Insights:
     - Real-time Queries & Positions
     - High-Impression / Low-CTR Quick Wins
     - Sitemap Indexing Status
     - Rich Snippets / Schema Enhancements
```

---

## 2. Credentials & Security Configuration

### A. Service Account Identity
* **Service Account Email:** `egxbots-seo@neon-dryad-454519-r2.iam.gserviceaccount.com`
* **GSC Role:** `siteFullUser` (Owner permissions on `https://egxbots.com/`)
* **Project ID (Google Cloud):** `neon-dryad-454519-r2`

### B. Credentials File Location
The private credentials JSON key is stored in the repository root and scripts directory:
```
C:\Users\MR__CODER__\Desktop\stokscan_AI\neon-dryad-454519-r2-03a9cbb96d36.json
C:\Users\MR__CODER__\Desktop\stokscan_AI\scripts\gsc_service_account.json
```
*(Also configured system-wide via the `GSC_CREDENTIALS_PATH` environment variable).*

### C. Git Protection
To prevent credential leaks, the root `.gitignore` explicitly blocks all key variants:
```gitignore
# Google Service Account Keys
*neon-dryad*.json
service_account*.json
*credentials*.json
```
> **Warning for AI Agents:** NEVER commit or push `.json` key files to GitHub or remote repositories.

---

## 3. SEO & GEO Intelligence Tool (`gsc_audit.py`)

A centralized Python CLI tool is available at `scripts/seo/gsc_audit.py` and `scripts/gsc_analyzer.py`. Any agent or human developer can execute it from the terminal in any IDE.

### Available Commands:

#### 1. Executive Summary (Last 28 Days)
```bash
python scripts/seo/gsc_audit.py
```
*Outputs: Sitemaps status, total clicks, total impressions, top 5 keywords, and top 5 landing pages.*

#### 2. Quick-Win Opportunities (High Impressions, Low CTR)
```bash
python scripts/seo/gsc_audit.py --action wins
```
*Discovers pages and search queries already ranking on Google page 1-2 with high impression counts but suffering from low click-through rates (CTR). These represent the fastest way to 5x-10x traffic with simple copy/schema adjustments.*

#### 3. Top Keywords & Ranking Positions
```bash
python scripts/seo/gsc_audit.py --action queries --limit 50 --days 30
```
*Lists all search queries, impressions, clicks, CTR, and average SERP position.*

#### 4. Top Landing Pages
```bash
python scripts/seo/gsc_audit.py --action pages --limit 30
```

#### 5. Sitemaps Verification & Submission
```bash
python scripts/seo/gsc_audit.py --action sitemaps
python scripts/seo/gsc_audit.py --action submit-sitemap
```

#### 6. Programmatic JSON Output (For Agent Automation)
```bash
python scripts/seo/gsc_audit.py --action wins --json
```

---

## 4. Benchmark & Current Status Baseline (Snapshot: November 7, 2026)

This baseline establishes the exact metrics recorded before deploying the full-coverage Arabic stock names overhaul and 6 Pillar Guides. Use this section to compare progress during upcoming reviews.

### A. Performance Baseline (Last 28 Days: Oct 8 – Nov 5, 2026)
| Metric | Value | Previous Period | Growth |
| :--- | :--- | :--- | :--- |
| **Total Clicks** | **263** | 287 | -8.4% |
| **Total Impressions** | **7,953** | 2,157 | **+268.7% 🟢** |
| **Average CTR** | **3.31%** | 13.31% | *(Diluted due to massive surge in un-clicked stock impressions)* |
| **Average SERP Position** | **7.8** | 4.5 | -3.3 |

### B. Indexing & Coverage Audit (Why Only ~104 Pages Appeared in SERP)
* **Total URLs in `sitemap.xml`:** 372 active URLs (306 stocks, 11 guides/blogs, 55 daily reports & core tools).
* **Pages with Recorded Impressions in Google:** **103 pages** (87 stock pages + 16 core pages).
* **Root Causes Identified via GSC URL Inspection API:**
  1. **Discovered – currently not indexed:** Google crawler discovered stock URLs via sitemap but queued them slowly due to a lack of permanent internal links from high-authority pages.
  2. **URL is unknown to Google:** Ticker pages with zero links in navigation were not discovered until crawled via deep sitemap feeds.
  3. **English Ticker Disconnect (CTR Killer):** Egyptian investors searched in Arabic (e.g. `"سعر سهم العربية للالومنيوم"` - 595 imp, `"سعر سهم ام بي الهندسيه"` - 269 imp, `"سعر سهم كوبر"` - 226 imp), but our stock pages displayed only raw English tickers (`ALUM`, `MBEG`, `COPR`) without Arabic names in `<title>` or `<h1>`, resulting in **0.0% to 1.0% CTR**.

### C. Remediation Actions Deployed (Commit `c0837464`):
1. **100% Arabic & English Stock Name Coverage:** All 278 EGX symbols mapped to verified canonical Arabic company names in `web/src/lib/ai/stock-names.ts`.
2. **High-CTR Dynamic Titles & Metadata:** Pattern: `سعر سهم [اسم الشركة العربي] ([الرمز]) اليوم | تحليل فني ودعم ومقاومة | EGX BOTS`.
3. **Sitewide Internal Linking Hub:** Added a permanent footer block linking to top 10 traded EGX stocks and all 6 Pillar Guides on every page.
4. **6 High-Volume Educational Pillar Guides (`/blogs/*`):**
   - `/blogs/best-egx-stock-analysis-software`
   - `/blogs/ai-egyptian-stock-market-analysis`
   - `/blogs/egx-telegram-stock-recommendations`
   - `/blogs/how-to-invest-in-egyptian-stock-market-beginners`
   - `/blogs/egx33-sharia-compliant-stocks-egypt-guide`
   - `/blogs/undervalued-egx-stocks-fair-value-calculation`
5. **Instant Indexing Push:** Submitted sitemap to Google Search Console API and pushed key URLs to Bing/Yandex/ChatGPT Search via IndexNow protocol.

---

## 5. Review & Measurement Schedule

Google Search Console data has an inherent 2–3 day latency. Follow this inspection timeline:

1. **Tuesday, Nov 10, 2026 (72 Hours Post-Deploy):**
   - Check Googlebot sitemap ingestion and initial crawl timestamps:
     `python scripts/seo/gsc_audit.py --action sitemaps`
2. **Saturday, Nov 14, 2026 (1 Week Review):**
   - Check CTR rebound on high-impression stocks (`ALUM`, `MBEG`, `COPR`, `ABUK`):
     `python scripts/seo/gsc_audit.py --action queries --limit 30`
   - Verify indexing expansion beyond the 104-page mark.
3. **End of November (Nov 21–28, 2026):**
   - Full evaluation toward the goal of multiplying organic monthly traffic and scaling impression volume.

---

## 6. Guidelines for Future AI Agents

When tasked with SEO or GEO work on this repository:
1. **Always run `python scripts/seo/gsc_audit.py --action wins` first** to ground recommendations in real search data rather than guesswork.
2. **Prioritize high-impression pages (e.g. `ALUM`, `COPR`, `KORA`, `MBEG`)** where improving CTR yields immediate traffic gains.
3. **Preserve JSON-LD Schema integrity** whenever updating page components.
4. **Follow `<RULE[user_global]>`:** If any rebuild or dev server restart is needed, ensure both port 8000 (FastAPI) and port 3000 (Next.js) remain operational.
