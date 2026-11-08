"""
Daily EGX Disclosures Automation Job
Runs as part of the daily pipeline to fetch and analyze newly published disclosures.
Incremental: picks up from the last recorded date and only analyzes new filings.
"""

import os
import sys
import io
import json
import re
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
from supabase import create_client

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Ensure root dir in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, '.env'))

from scripts.disclosures.sync_egx_disclosures import (
    STOCK_MAP, match_stock, parse_date, analyze_batch_with_ai
)

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

def run_daily_sync():
    print("=" * 65)
    print("🕒 Starting Daily EGX Disclosures Incremental Sync...")
    print("=" * 65)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Missing Supabase credentials in environment.")
        return {"status": "error", "message": "Missing Supabase credentials"}

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Get latest disclosure date in database
    try:
        res = sb.table('egx_disclosures').select('disclosure_date').order('disclosure_date', desc=True).limit(1).execute()
        latest_date_str = res.data[0]['disclosure_date'] if res.data else '2026-01-01'
        latest_date = datetime.date.fromisoformat(latest_date_str)
        print(f"📅 Latest disclosure date in DB: {latest_date}")
    except Exception as e:
        print(f"⚠️ Warning: Could not query latest date ({e}), defaulting to 3 days ago.")
        latest_date = datetime.date.today() - datetime.timedelta(days=3)

    # 2. Fetch fresh items from RSS targeting recent filings
    queries = [
        'site:mubasher.info/news "تعاملات الداخليين والمساهمين الرئيسيين"',
        'site:mubasher.info/news "إفصاح" "البورصة المصرية"',
        'site:mubasher.info/news "هيكل المساهمين" "البورصة المصرية"',
        'site:mubasher.info/news "مجلس إدارة" "البورصة المصرية"'
    ]

    new_items = []
    seen_titles = set()

    for q in queries:
        url = f'https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ar&gl=EG&ceid=EG:ar'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
                for it in root.findall('.//item'):
                    title = it.find('title').text or ''
                    link = it.find('link').text or ''
                    pub = it.find('pubDate').text or ''
                    
                    # Parse date
                    try:
                        dt_obj = parsedate_to_datetime(pub).date()
                    except Exception:
                        dt_obj = datetime.date.today()

                    # Only process items from latest_date onward
                    if dt_obj >= latest_date and title not in seen_titles:
                        seen_titles.add(title)
                        clean_t = re.sub(r'\s*-\s*معلومات مباشر.*$', '', title).strip()
                        sym, official_name = match_stock(clean_t)
                        
                        action_type = 'general'
                        if 'خفض حصته' in clean_t or 'تراجع' in clean_t or 'بيع' in clean_t:
                            action_type = 'sell'
                        elif 'رفع حصته' in clean_t or 'شراء' in clean_t or 'زيادة' in clean_t:
                            action_type = 'buy'

                        d_type = 'material_event'
                        if 'تعاملات الداخليين' in clean_t:
                            d_type = 'insider_trading'
                        elif 'هيكل المساهمين' in clean_t:
                            d_type = 'major_shareholders'
                        elif 'مجلس إدارة' in clean_t:
                            d_type = 'board_resolution'

                        new_items.append({
                            'symbol': sym,
                            'company_name': official_name or (sym if sym else 'البورصة المصرية'),
                            'disclosure_type': d_type,
                            'disclosure_date': dt_obj.strftime('%Y-%m-%d'),
                            'title': clean_t,
                            'raw_content': f"الإفصاح: {clean_t}\nالتاريخ: {dt_obj}\nالمصدر: البورصة المصرية",
                            'action_type': action_type,
                            'shares_count': None,
                            'party_name': 'الشركة / كبار المساهمين',
                            'party_role': 'مساهم رئيسي / إدارة',
                            'source_url': link,
                            'metadata': {'raw_title': clean_t, 'pub_date': pub, 'synced_by': 'daily_job'}
                        })
        except Exception as e:
            print(f"Error querying RSS: {e}")

    # 3. Check for duplicates against existing DB titles
    if new_items:
        try:
            titles = [it['title'] for it in new_items]
            existing_res = sb.table('egx_disclosures').select('title').in_('title', titles).execute()
            existing_set = set(r['title'] for r in existing_res.data)
            new_items = [it for it in new_items if it['title'] not in existing_set]
        except Exception as e:
            print(f"Warning: Could not filter existing titles: {e}")

    print(f"✨ Found {len(new_items)} genuinely new disclosures since {latest_date}.")

    if not new_items:
        print("✅ No new disclosures today. Zero token consumption.")
        return {"status": "ok", "new_count": 0}

    # 4. Analyze in batches of 5
    batch_size = 5
    inserted = 0
    for i in range(0, len(new_items), batch_size):
        batch = new_items[i:i + batch_size]
        analyzed, _, _ = analyze_batch_with_ai(batch)
        try:
            sb.table('egx_disclosures').insert(analyzed).execute()
            inserted += len(analyzed)
            print(f"  ✅ Inserted batch {i//batch_size + 1} ({len(analyzed)} items)")
        except Exception as e:
            print(f"  ❌ Insertion error: {e}")

    print(f"🎉 Successfully synced and analyzed {inserted} new disclosures.")
    return {"status": "ok", "new_count": inserted}

if __name__ == '__main__':
    run_daily_sync()
