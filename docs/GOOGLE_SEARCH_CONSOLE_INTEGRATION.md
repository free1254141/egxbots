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
The private credentials JSON key is stored in the repository root:
```
C:\Users\MR__CODER__\Desktop\stokscan_AI\neon-dryad-454519-r2-03a9cbb96d36.json
```
*(Alternative: You can set the path via the `GSC_CREDENTIALS_PATH` environment variable).*

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

A centralized Python CLI tool is available at `scripts/seo/gsc_audit.py`. Any agent or human developer can execute it from the terminal in any IDE.

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

#### 5. Sitemaps Verification
```bash
python scripts/seo/gsc_audit.py --action sitemaps
```

#### 6. Programmatic JSON Output (For Agent Automation)
```bash
python scripts/seo/gsc_audit.py --action wins --json
```

---

## 4. Programmatic Python API for AI Agents

Any agent or background script can import the helper functions directly:

```python
from scripts.seo.gsc_audit import get_gsc_service, fetch_search_analytics, fetch_sitemaps

service, cred_path = get_gsc_service()

# Fetch top 20 queries for the last 14 days
rows, start_date, end_date = fetch_search_analytics(
    service, 
    site_url="https://egxbots.com/", 
    days=14, 
    dimensions=["query"], 
    row_limit=20
)

for r in rows:
    query = r["keys"][0]
    clicks = r["clicks"]
    impressions = r["impressions"]
    position = r["position"]
    print(f"{query}: {clicks} clicks, rank {position:.1f}")
```

---

## 5. SEO & GEO Implementation in Frontend (`web/`)

### A. GEO & AI Crawlers Policy (`web/src/app/robots.ts`)
The `robots.ts` file explicitly permits leading generative AI crawlers to index stock data, technical scanner pages, market analyses, and LLM feeds:
* Allowed AI Crawlers: `GPTBot`, `ChatGPT-User`, `PerplexityBot`, `ClaudeBot`, `Google-Extended`, `Applebot-Extended`, `OAI-SearchBot`, `cohere-ai`.
* Specialized Feeds Allowed: `/llms.txt`, `/llms-full.txt`, `/stocks/*`, `/scanner/*`.

### B. Dynamic High-CTR Metadata (`web/src/app/stocks/[symbol]/page.tsx`)
Titles and descriptions are dynamically generated using high-intent Arabic search queries matching real user search behavior in GSC:
* **Title Pattern:** `سعر وتحليل سهم [الاسم] ([الرمز]) وتوقعات الدعم والمقاومة | EGX BOTS`
* **Description Pattern:** Lead with exact closing price + EGP + date + RSI/MACD and support/resistance summary.

### C. Rich Structured Data Schema (JSON-LD)
Stock pages render an interconnected Schema.org graph:
1. **`BreadcrumbList`:** For structured Google navigation hierarchy.
2. **`WebPage`:** With author, publisher, and modification timestamps.
3. **`FinancialProduct`:** Exposes ticker symbol, exchange (`EGX`), currency (`EGP`), and latest closing price for Google Finance / Knowledge Graph.
4. **`FAQPage`:** Provides Google SERP Accordion / Rich Snippets answering:
   - *ما هو سعر سهم [الاسم] في البورصة المصرية اليوم؟*
   - *كيف يتم تحديد مستويات الدعم والمقاومة لسهم [الرمز]؟*

---

## 6. Guidelines for Future AI Agents

When tasked with SEO or GEO work on this repository:
1. **Always run `python scripts/seo/gsc_audit.py --action wins` first** to ground recommendations in real search data rather than guesswork.
2. **Prioritize high-impression pages (e.g. `ALUM`, `COPR`, `KORA`, `MBEG`)** where improving CTR yields immediate traffic gains.
3. **Preserve JSON-LD Schema integrity** whenever updating page components.
4. **Follow `<RULE[user_global]>`:** If any rebuild or dev server restart is needed, ensure both port 8000 (FastAPI) and port 3000 (Next.js) remain operational.
