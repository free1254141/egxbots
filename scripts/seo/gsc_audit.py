#!/usr/bin/env python3
"""
Google Search Console (GSC) Audit & SEO/GEO Intelligence Tool
==============================================================
Designed for AI Agents (Antigravity, Cursor, Copilot, Claude Code) and developers.
Allows querying live search performance, discovering SEO quick wins (high impressions, low CTR),
and verifying/submitting sitemaps for https://egxbots.com/.

Usage:
    python scripts/seo/gsc_audit.py                           # Full executive summary
    python scripts/seo/gsc_audit.py --action queries          # Top search queries
    python scripts/seo/gsc_audit.py --action pages            # Top landing pages
    python scripts/seo/gsc_audit.py --action wins             # Top quick-win opportunities (high imp, low CTR)
    python scripts/seo/gsc_audit.py --action sitemaps         # Sitemaps status
    python scripts/seo/gsc_audit.py --action submit-sitemap   # Ping/Submit sitemap.xml to Google Search Console
    python scripts/seo/gsc_audit.py --days 14                 # Custom date range (default: 28 days)
    python scripts/seo/gsc_audit.py --json                    # Output raw JSON for programmatic agent consumption
"""

import os
import sys
import glob
import json
import argparse
from datetime import datetime, timedelta

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    print("Error: Missing Google API libraries. Run: pip install google-api-python-client google-auth")
    sys.exit(1)

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SITE_URL = "https://egxbots.com/"
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/webmasters"
]

def find_credentials():
    # 1. Environment variable
    if os.environ.get("GSC_CREDENTIALS_PATH"):
        p = os.environ["GSC_CREDENTIALS_PATH"]
        if os.path.exists(p):
            return p

    # 2. Project root search
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    patterns = [
        os.path.join(repo_root, "*neon-dryad*.json"),
        os.path.join(repo_root, "*gsc*.json"),
        os.path.join(repo_root, "service_account*.json")
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]

    return None

def get_gsc_service():
    cred_file = find_credentials()
    if not cred_file:
        raise FileNotFoundError(
            "GSC Service Account credentials JSON not found! "
            "Ensure a file matching '*neon-dryad*.json' exists in repo root or set GSC_CREDENTIALS_PATH."
        )
    creds = service_account.Credentials.from_service_account_file(cred_file, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds), cred_file

def fetch_search_analytics(service, site_url, days=28, dimensions=None, row_limit=50):
    if dimensions is None:
        dimensions = ["query"]
    
    end_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days + 2)).strftime("%Y-%m-%d")

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit
    }
    resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return resp.get("rows", []), start_date, end_date

def fetch_sitemaps(service, site_url):
    sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
    return sitemaps.get("sitemap", [])

def main():
    parser = argparse.ArgumentParser(description="Google Search Console SEO & GEO Intelligence Tool")
    parser.add_argument("--action", choices=["summary", "queries", "pages", "wins", "sitemaps", "submit-sitemap"], default="summary")
    parser.add_argument("--days", type=int, default=28, help="Number of historical days to inspect (default: 28)")
    parser.add_argument("--limit", type=int, default=30, help="Row limit for queries or pages (default: 30)")
    parser.add_argument("--site", default=DEFAULT_SITE_URL, help=f"Target GSC site (default: {DEFAULT_SITE_URL})")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON for agent workflows")
    args = parser.parse_args()

    try:
        service, cred_path = get_gsc_service()
    except Exception as e:
        print(f"Failed to initialize GSC client: {e}")
        sys.exit(1)

    if args.action == "submit-sitemap":
        feedpath = f"{args.site.rstrip('/')}/sitemap.xml"
        service.sitemaps().submit(siteUrl=args.site, feedpath=feedpath).execute()
        sitemaps = fetch_sitemaps(service, args.site)
        if args.json:
            print(json.dumps({"submitted": feedpath, "sitemaps": sitemaps}, indent=2))
            return
        print(f"Successfully submitted sitemap to Google Search Console: {feedpath}")
        for sm in sitemaps:
            print(f"- Path: {sm.get('path')} | Last Submitted: {sm.get('lastSubmitted')} | Errors: {sm.get('errors', 0)}")
        return

    if args.action == "sitemaps":
        sitemaps = fetch_sitemaps(service, args.site)
        if args.json:
            print(json.dumps(sitemaps, indent=2))
            return
        print(f"=== SITEMAPS FOR {args.site} ===")
        for sm in sitemaps:
            print(f"- Path: {sm.get('path')} | Downloaded: {sm.get('lastDownloaded')} | Errors: {sm.get('errors', 0)}")
        return

    if args.action == "queries":
        rows, s_dt, e_dt = fetch_search_analytics(service, args.site, days=args.days, dimensions=["query"], row_limit=args.limit)
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        print(f"=== TOP SEARCH QUERIES ({s_dt} to {e_dt}) ===")
        print(f"{'Query':<35} | {'Clicks':<8} | {'Impressions':<12} | {'CTR (%)':<8} | {'Avg Pos':<8}")
        print("-" * 80)
        for r in rows:
            q = r.get("keys", [""])[0]
            c = r.get("clicks", 0)
            imp = r.get("impressions", 0)
            ctr = r.get("ctr", 0) * 100
            pos = r.get("position", 0)
            print(f"{q:<35} | {c:<8} | {imp:<12} | {ctr:<8.1f} | {pos:<8.1f}")
        return

    if args.action == "pages":
        rows, s_dt, e_dt = fetch_search_analytics(service, args.site, days=args.days, dimensions=["page"], row_limit=args.limit)
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        print(f"=== TOP LANDING PAGES ({s_dt} to {e_dt}) ===")
        for r in rows:
            p = r.get("keys", [""])[0]
            print(f"- {p} -> Clicks: {r.get('clicks', 0)} | Imp: {r.get('impressions', 0)} | CTR: {r.get('ctr', 0)*100:.1f}%")
        return

    if args.action == "wins":
        # Discover queries/pages with High Impressions (>=30) but Low CTR (<= 3%)
        q_rows, _, _ = fetch_search_analytics(service, args.site, days=args.days, dimensions=["query"], row_limit=100)
        p_rows, _, _ = fetch_search_analytics(service, args.site, days=args.days, dimensions=["page"], row_limit=100)
        
        q_wins = [r for r in q_rows if r.get("impressions", 0) >= 30 and (r.get("ctr", 0) * 100) <= 5.0]
        p_wins = [r for r in p_rows if r.get("impressions", 0) >= 50 and (r.get("ctr", 0) * 100) <= 2.0]

        result = {
            "query_opportunities": q_wins,
            "page_opportunities": p_wins
        }
        if args.json:
            print(json.dumps(result, indent=2))
            return
        
        print("=== 🚀 QUICK-WIN SEO OPPORTUNITIES (High Impressions, Low CTR) ===")
        print("\n[Pages losing clicks despite high visibility in Google]:")
        for p in p_wins:
            url = p.get("keys", [""])[0]
            print(f"  * {url}")
            print(f"    Impressions: {p.get('impressions', 0)} | Clicks: {p.get('clicks', 0)} | CTR: {p.get('ctr', 0)*100:.2f}% | Avg Pos: {p.get('position', 0):.1f}")
            print(f"    Action: Optimize Title Tag and add Structured Data (Schema JSON-LD) to boost CTR.\n")
            
        print("\n[Keywords with high impressions where better copy will 10x traffic]:")
        for q in q_wins:
            word = q.get("keys", [""])[0]
            print(f"  * '{word}' | Imp: {q.get('impressions', 0)} | Clicks: {q.get('clicks', 0)} | CTR: {q.get('ctr', 0)*100:.2f}% | Pos: {q.get('position', 0):.1f}")
        return

    # Default: Executive Summary
    sitemaps = fetch_sitemaps(service, args.site)
    q_rows, s_dt, e_dt = fetch_search_analytics(service, args.site, days=args.days, dimensions=["query"], row_limit=10)
    p_rows, _, _ = fetch_search_analytics(service, args.site, days=args.days, dimensions=["page"], row_limit=10)
    
    total_clicks = sum(r.get("clicks", 0) for r in p_rows)
    total_imp = sum(r.get("impressions", 0) for r in p_rows)

    print(f"================================================================")
    print(f"  GOOGLE SEARCH CONSOLE AUDIT REPORT - {args.site}")
    print(f"  Period: {s_dt} to {e_dt} ({args.days} days)")
    print(f"  Credentials: {os.path.basename(cred_path)}")
    print(f"================================================================")
    print(f"Sitemaps: {len(sitemaps)} active (Primary: {sitemaps[0].get('path') if sitemaps else 'None'})")
    print(f"Top 10 Pages Total Clicks: {total_clicks} | Total Impressions: {total_imp}")
    print("\nTop 5 Ranking Keywords:")
    for r in q_rows[:5]:
        q = r.get("keys", [""])[0]
        print(f"  - '{q}': {r.get('clicks', 0)} clicks, {r.get('impressions', 0)} imp, Avg Pos: {r.get('position', 0):.1f}")

    print("\nTop 5 Pages by Traffic:")
    for r in p_rows[:5]:
        p = r.get("keys", [""])[0]
        print(f"  - {p}: {r.get('clicks', 0)} clicks, {r.get('impressions', 0)} imp")
    print(f"================================================================")
    print("Run with '--action wins' to inspect immediate traffic-multiplication opportunities.")

if __name__ == "__main__":
    main()
