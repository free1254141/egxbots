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
    STOCK_MAP, EXCLUDE_KEYWORDS, match_stock, parse_date, analyze_batch_with_ai
)

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

EXTRA_NON_EGX_KEYWORDS = [
    'السعودي', 'تداول', 'أرامكو', 'الراجحي', 'دبي', 'أبوظبي', 'أبو ظبي', 'الكويت', 'قطر', 'البحرين',
    'مسقط', 'عمان', 'وول ستريت', 'ناسداك', 'الفيدرالي', 'النفط', 'الذهب', 'بيتكوين', 'عملات',
    'الروبية', 'الريال', 'الدرهم', 'الدينار', 'أوروبا', 'آسيا', 'الصين', 'اليابان', 'الأمريكي',
    'الأمريكية', 'البريطاني', 'تركيا', 'الهند', 'عطاء التعليمية', 'الخليج للكيماويات',
    'بوبيان للبتروكيماويات', 'إنفيديا', 'انفيديا', 'آبل', 'مايكروسوفت', 'تسلا', 'أمازون',
    'ميتا', 'جوجل', 'ألفابت', 'سهم صادرات', 'أعيان للإجارة', 'كهرباء ومياه دبي', 'تبريد',
    'بيتك', 'إعمار', 'أدنوك', 'سالك', 'الدار العقارية', 'طيران الجزيرة', 'زين الكويت',
    'بورصة الكويت', 'سوق دبي', 'سوق أبوظبي'
]


def extract_shares_from_title(title: str):
    if not title:
        return None
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(مليون|ألف|الف)\s*سهم', title)
    if m:
        num = float(m.group(1).replace(',', '.'))
        mult = 1_000_000 if m.group(2) == 'مليون' else 1_000
        return int(round(num * mult))
    m2 = re.search(r'بعدد\s*(\d[\d,]*)\s*سهم', title)
    if m2:
        return int(m2.group(1).replace(',', ''))
    return None


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

    # Preload latest prices for execution_price enrichment
    price_map = {}
    try:
        p_res = sb.table('stock_technical_indicators').select('symbol, close').execute()
        for r in (p_res.data or []):
            if r.get('symbol') and r.get('close'):
                price_map[r['symbol']] = float(r['close'])
    except Exception as e:
        print(f"⚠️ Warning: Could not preload prices ({e})")

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
                        clean_t = re.sub(r'\s*-\s*معلومات مباشر.*$', '', title).strip()
                        if any(kw in clean_t for kw in EXCLUDE_KEYWORDS) or any(kw in clean_t for kw in EXTRA_NON_EGX_KEYWORDS):
                            continue
                        sym, official_name = match_stock(clean_t)
                        if not sym:
                            continue

                        seen_titles.add(title)
                        d_type = 'material_event'
                        if 'تعاملات الداخليين' in clean_t:
                            d_type = 'insider_trading'
                        elif 'هيكل المساهمين' in clean_t:
                            d_type = 'major_shareholders'
                        elif 'مجلس إدارة' in clean_t:
                            d_type = 'board_resolution'

                        shares_cnt = extract_shares_from_title(clean_t)
                        is_stake_trade = (
                            shares_cnt is not None
                            and shares_cnt > 0
                            and (
                                d_type in ('insider_trading', 'major_shareholders')
                                or any(k in clean_t for k in ('خفض حصته', 'رفع حصته', 'شراء داخلي', 'بيع داخلي'))
                            )
                        )
                        action_type = 'general'
                        if is_stake_trade:
                            if any(k in clean_t for k in ('خفض حصته', 'بيع', 'تقليص', 'تخارج')):
                                action_type = 'sell'
                            elif any(k in clean_t for k in ('رفع حصته', 'شراء', 'زيادة حصة', 'تجميع')):
                                action_type = 'buy'
                        meta = {'raw_title': clean_t, 'pub_date': pub, 'synced_by': 'daily_job'}
                        if action_type in ('buy', 'sell') and sym in price_map:
                            meta['execution_price'] = price_map[sym]
                            meta['transaction_currency'] = 'EGP'

                        new_items.append({
                            'symbol': sym,
                            'company_name': official_name or sym,
                            'disclosure_type': d_type,
                            'disclosure_date': dt_obj.strftime('%Y-%m-%d'),
                            'title': clean_t,
                            'raw_content': f"الإفصاح: {clean_t}\nالتاريخ: {dt_obj}\nالمصدر: البورصة المصرية",
                            'action_type': action_type,
                            'shares_count': shares_cnt,
                            'party_name': 'الشركة / كبار المساهمين',
                            'party_role': 'مساهم رئيسي / إدارة',
                            'source_url': link,
                            'metadata': meta
                        })
        except Exception as e:
            print(f"Error querying RSS: {e}")

    # 3. Check for duplicates against existing DB rows (source_url, normalized title, and same-day corporate events)
    if new_items:
        try:
            since_30d = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            existing_res = (
                sb.table('egx_disclosures')
                .select('symbol, disclosure_type, disclosure_date, title, source_url')
                .gte('disclosure_date', since_30d)
                .limit(1000)
                .execute()
            )
            existing_rows = existing_res.data or []
            existing_urls = {r.get('source_url') for r in existing_rows if r.get('source_url')}
            existing_norm_titles = {
                re.sub(r'[^\w\s\u0600-\u06FF]', '', (r.get('title') or '').lower()).strip()
                for r in existing_rows
                if r.get('title')
            }
            existing_event_keys = {
                (r.get('symbol'), r.get('disclosure_type'), r.get('disclosure_date'))
                for r in existing_rows
                if r.get('symbol') and r.get('disclosure_type') not in ('insider_trading', 'major_shareholders')
            }

            deduped_items = []
            for it in new_items:
                norm_t = re.sub(r'[^\w\s\u0600-\u06FF]', '', (it.get('title') or '').lower()).strip()
                ev_key = (it.get('symbol'), it.get('disclosure_type'), it.get('disclosure_date'))
                if it.get('source_url') and it.get('source_url') in existing_urls:
                    continue
                if norm_t and norm_t in existing_norm_titles:
                    continue
                if (
                    it.get('disclosure_type') not in ('insider_trading', 'major_shareholders')
                    and ev_key in existing_event_keys
                ):
                    continue
                if not it.get('shares_count'):
                    it['action_type'] = 'general'
                existing_urls.add(it.get('source_url'))
                existing_norm_titles.add(norm_t)
                existing_event_keys.add(ev_key)
                deduped_items.append(it)
            new_items = deduped_items
        except Exception as e:
            print(f"Warning: Could not filter existing disclosures: {e}")

    print(f"✨ Found {len(new_items)} genuinely new disclosures since {latest_date}.")

    if not new_items:
        print("✅ No new disclosures today. Zero token consumption.")
        return {"status": "ok", "new_count": 0, "added": 0}

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
    return {"status": "ok", "new_count": inserted, "added": inserted}


def run_incremental_sync():
    """Alias for daily bot run pipeline compatibility."""
    return run_daily_sync()


if __name__ == '__main__':
    run_daily_sync()
