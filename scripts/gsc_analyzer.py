"""
Google Search Console (GSC) Analyzer for EGX Bots.
Provides automated SEO analysis, ranking changes, top queries, page opportunities, and indexing status.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    print("❌ Error: google-api-python-client or google-auth not installed.")
    print("Run: pip install google-api-python-client google-auth")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
DEFAULT_CREDENTIALS_FILES = [
    'scripts/gsc_service_account.json',
    'gsc_service_account.json',
    'gsc_credentials.json',
    'scripts/gsc_credentials.json',
    'credentials.json',
]


def find_credentials():
    env_path = os.getenv('GSC_CREDENTIALS_PATH')
    if env_path and os.path.exists(env_path):
        return env_path
    
    for f in DEFAULT_CREDENTIALS_FILES:
        if os.path.exists(f):
            return f
    return None


def get_service(creds_path):
    creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build('searchconsole', 'v1', credentials=creds)


def resolve_site_url(service, site_arg=None):
    if site_arg:
        return site_arg
    
    # Try listing properties accessible to this service account
    try:
        sites_list = service.sites().list().execute()
        entries = sites_list.get('siteEntry', [])
        if entries:
            # Prefer domain property or https://egxbots.com/
            for s in entries:
                url = s.get('siteUrl', '')
                if 'egxbots.com' in url:
                    return url
            return entries[0].get('siteUrl')
    except Exception as e:
        pass
    
    return 'sc-domain:egxbots.com'


def query_search_analytics(service, site_url, start_date, end_date, dimensions=None, row_limit=100, dimension_filter_groups=None):
    request_body = {
        'startDate': start_date,
        'endDate': end_date,
        'rowLimit': row_limit,
    }
    if dimensions:
        request_body['dimensions'] = dimensions
    if dimension_filter_groups:
        request_body['dimensionFilterGroups'] = dimension_filter_groups
        
    response = service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
    return response.get('rows', [])


def format_table(headers, rows):
    if not rows:
        return "_لا توجد بيانات مسجلة لهذه الفترة._"
    
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))
            
    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    separator_line = "| " + " | ".join("-" * col_widths[i] for i in range(len(headers))) + " |"
    data_lines = [
        "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator_line] + data_lines)


def run_summary(service, site_url, days=28):
    today = datetime.now(timezone.utc).date()
    # GSC data usually has a 2-3 day lag
    end_date = today - timedelta(days=2)
    start_date = end_date - timedelta(days=days)
    
    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=days)
    
    cur_rows = query_search_analytics(service, site_url, str(start_date), str(end_date))
    prev_rows = query_search_analytics(service, site_url, str(prev_start_date), str(prev_end_date))
    
    cur_clicks = sum(r.get('clicks', 0) for r in cur_rows)
    cur_impressions = sum(r.get('impressions', 0) for r in cur_rows)
    cur_ctr = (cur_clicks / cur_impressions * 100) if cur_impressions else 0
    cur_pos = (sum(r.get('position', 0) * r.get('impressions', 0) for r in cur_rows) / cur_impressions) if cur_impressions else 0
    
    prev_clicks = sum(r.get('clicks', 0) for r in prev_rows)
    prev_impressions = sum(r.get('impressions', 0) for r in prev_rows)
    prev_ctr = (prev_clicks / prev_impressions * 100) if prev_impressions else 0
    prev_pos = (sum(r.get('position', 0) * r.get('impressions', 0) for r in prev_rows) / prev_impressions) if prev_impressions else 0
    
    def change_str(cur, prev, is_position=False):
        diff = cur - prev
        if is_position:
            # Lower position is better
            icon = "🟢" if diff < 0 else ("🔴" if diff > 0 else "⚪")
            return f"{cur:.1f} ({icon} {diff:+.1f})"
        pct = ((diff / prev) * 100) if prev else 0
        icon = "🟢" if diff > 0 else ("🔴" if diff < 0 else "⚪")
        return f"{cur:,.0f} ({icon} {diff:+,.0f} / {pct:+.1f}%)"
    
    print(f"\n=======================================================")
    print(f"📊 ملخص أداء البحث في جوجل لـ {site_url}")
    print(f"الفترة: {start_date} إلى {end_date} (مقارنة بـ {prev_start_date} إلى {prev_end_date})")
    print(f"=======================================================")
    
    table_rows = [
        ["إجمالي النقرات (Clicks)", change_str(cur_clicks, prev_clicks)],
        ["مرات الظهور (Impressions)", change_str(cur_impressions, prev_impressions)],
        ["نسبة النقر (CTR)", f"{cur_ctr:.2f}% (السابق: {prev_ctr:.2f}%)"],
        ["متوسط الترتيب (Avg. Position)", change_str(cur_pos, prev_pos, is_position=True)],
    ]
    print(format_table(["المؤشر", "القيمة الحالية (ومعدل التغير)"], table_rows))


def run_top_queries(service, site_url, days=28, limit=20):
    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=2)
    start_date = end_date - timedelta(days=days)
    
    rows = query_search_analytics(service, site_url, str(start_date), str(end_date), dimensions=['query'], row_limit=limit)
    
    table_rows = []
    for idx, r in enumerate(rows, 1):
        q = r['keys'][0]
        clicks = int(r.get('clicks', 0))
        impressions = int(r.get('impressions', 0))
        ctr = f"{r.get('ctr', 0) * 100:.1f}%"
        pos = f"{r.get('position', 0):.1f}"
        table_rows.append([idx, q, clicks, impressions, ctr, pos])
        
    print(f"\n🔑 الكلمات الأكثر بحثاً ونقراً (Top {limit} Queries):")
    print(format_table(["#", "كلمة البحث (Query)", "نقرات (Clicks)", "ظهور (Impressions)", "CTR", "الترتيب (Rank)"], table_rows))


def run_top_pages(service, site_url, days=28, limit=20):
    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=2)
    start_date = end_date - timedelta(days=days)
    
    rows = query_search_analytics(service, site_url, str(start_date), str(end_date), dimensions=['page'], row_limit=limit)
    
    table_rows = []
    for idx, r in enumerate(rows, 1):
        page = r['keys'][0].replace('https://egxbots.com', '').replace('https://www.egxbots.com', '') or '/'
        clicks = int(r.get('clicks', 0))
        impressions = int(r.get('impressions', 0))
        ctr = f"{r.get('ctr', 0) * 100:.1f}%"
        pos = f"{r.get('position', 0):.1f}"
        table_rows.append([idx, page, clicks, impressions, ctr, pos])
        
    print(f"\n📄 الصفحات الأكثر زيارة من جوجل (Top {limit} Landing Pages):")
    print(format_table(["#", "الصفحة (Page Path)", "نقرات", "ظهور", "CTR", "الترتيب"], table_rows))


def run_opportunities(service, site_url, days=28, limit=20):
    """Find queries ranking in striking distance (positions 6-25) with high impressions."""
    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=2)
    start_date = end_date - timedelta(days=days)
    
    rows = query_search_analytics(service, site_url, str(start_date), str(end_date), dimensions=['query'], row_limit=500)
    
    opps = []
    for r in rows:
        pos = r.get('position', 0)
        impr = r.get('impressions', 0)
        clicks = r.get('clicks', 0)
        if 5.0 <= pos <= 25.0 and impr >= 20:
            opps.append({
                'query': r['keys'][0],
                'clicks': clicks,
                'impressions': impr,
                'ctr': r.get('ctr', 0) * 100,
                'position': pos
            })
            
    # Sort by highest impressions
    opps.sort(key=lambda x: x['impressions'], reverse=True)
    opps = opps[:limit]
    
    table_rows = [
        [idx, o['query'], int(o['clicks']), int(o['impressions']), f"{o['ctr']:.1f}%", f"{o['position']:.1f}"]
        for idx, o in enumerate(opps, 1)
    ]
    print(f"\n🎯 الفرص الذهبية (كلمات بصفحة 2 وقريبة من الصفحة الأولى):")
    print(format_table(["#", "الكلمة المستهدفة", "النقرات الحالية", "الظهور", "CTR", "الترتيب الحالي"], table_rows))


def run_countries(service, site_url, days=28, limit=10):
    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=2)
    start_date = end_date - timedelta(days=days)
    
    rows = query_search_analytics(service, site_url, str(start_date), str(end_date), dimensions=['country'], row_limit=limit)
    
    table_rows = []
    for idx, r in enumerate(rows, 1):
        country = r['keys'][0].upper()
        clicks = int(r.get('clicks', 0))
        impressions = int(r.get('impressions', 0))
        ctr = f"{r.get('ctr', 0) * 100:.1f}%"
        table_rows.append([idx, country, clicks, impressions, ctr])
        
    print(f"\n🌍 توزيع الترافيك والظهور حسب الدول (Top Countries):")
    print(format_table(["#", "الدولة (Country Code)", "نقرات", "ظهور", "CTR"], table_rows))


def main():
    parser = argparse.ArgumentParser(description="Google Search Console Analyzer for EGX Bots")
    parser.add_argument('--site', default=None, help='Site property URL (e.g. sc-domain:egxbots.com or https://egxbots.com/)')
    parser.add_argument('--days', type=int, default=28, help='Number of days to analyze (default: 28)')
    parser.add_argument('--action', choices=['all', 'summary', 'queries', 'pages', 'opportunities', 'countries'], default='all', help='Action to perform')
    parser.add_argument('--limit', type=int, default=15, help='Limit rows for tables')
    args = parser.parse_args()
    
    creds_path = find_credentials()
    if not creds_path:
        print("\n❌ لم يتم العثور على ملف مفتاح جوجل كونسول (Service Account JSON Key).")
        print("📌 خطوات التفعيل السريعة:")
        print("1. حمّل ملف المفتاح بصيغة JSON من Google Cloud Console.")
        print("2. ضعه في مجلد scripts باسم: scripts/gsc_service_account.json")
        print("3. أضف إيميل الـ Service Account كمستخدم (Viewer) داخل Google Search Console لـ egxbots.com.")
        sys.exit(1)
        
    try:
        service = get_service(creds_path)
        site_url = resolve_site_url(service, args.site)
        print(f"✅ متصل بنجاح مع Google Search Console | الموقع: {site_url}")
        
        if args.action in ['all', 'summary']:
            run_summary(service, site_url, args.days)
        if args.action in ['all', 'queries']:
            run_top_queries(service, site_url, args.days, args.limit)
        if args.action in ['all', 'pages']:
            run_top_pages(service, site_url, args.days, args.limit)
        if args.action in ['all', 'opportunities']:
            run_opportunities(service, site_url, args.days, args.limit)
        if args.action in ['all', 'countries']:
            run_countries(service, site_url, args.days, args.limit)
            
    except Exception as e:
        print(f"\n❌ خطأ أثناء الاتصال أو جلب البيانات من Google Search Console:")
        print(str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
