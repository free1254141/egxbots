"""
EGX Disclosures Sync & AI Analyzer
Fetches, processes, analyzes, and stores EGX company disclosures and insider trading in Supabase.
"""

import os
import sys
import io
import json
import re
import datetime
import requests
from dotenv import load_dotenv
from supabase import create_client
from pypdf import PdfReader

# Force UTF-8 for console output safely
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment
load_dotenv('.env')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('DEEPSEEK_OFFICIAL_API_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Stock Keyword Mapping for Egyptian Exchange
STOCK_MAP = {
    'فوري': ('FWRY', 'فوري لتكنولوجيا البنوك والمدفوعات الالكترونية'),
    'الصعيد': ('SCCD', 'الصعيد العامة للمقاولات والاستثمار العقاري'),
    'العربية للأدوية': ('ADCI', 'العربية للأدوية والصناعات الكيماوية'),
    'العربية للادوية': ('ADCI', 'العربية للأدوية والصناعات الكيماوية'),
    'العربية للصناعات المعدنية': ('AMII', 'العربية للصناعات المعدنية والاستثمارات الصناعية'),
    'العربية للصناعات الهندسية': ('EEII', 'العربية للصناعات الهندسية'),
    'ابن سينا': ('ISPH', 'ابن سينا فارما'),
    'طاقة عربية': ('TAQA', 'طاقة عربية'),
    'ارابيا للاستثمار': ('AIND', 'ارابيا للاستثمار والتنمية'),
    'مجموعة النعيم': ('NAHO', 'مجموعة النعيم العقارية القابضة'),
    'مصر للفنادق': ('MHOT', 'شركة مصر للفنادق'),
    'بيراميزا': ('PHTV', 'بيراميزا للفنادق والقرى السياحية'),
    'الاسكندرية للخدمات الطبية': ('AMES', 'الاسكندرية للخدمات الطبية - المركز الطبي الجديد'),
    'المركز الطبى الجديد': ('AMES', 'الاسكندرية للخدمات الطبية - المركز الطبي الجديد'),
    'برايم': ('PRMH', 'برايم القابضة للاستثمارات المالية'),
    'المصرية لنظم التعليم': ('MOED', 'المصرية لنظم التعليم الحديثة'),
    'البدر': ('BIDI', 'البدر للاستثمار والتنمية'),
    'بي اي جي': ('BIGP', 'بي اي جي للتجارة والاستثمار'),
    'القاهرة للدواجن': ('POUL', 'القاهرة للدواجن'),
    'جو جرين': ('GOGN', 'جو جرين للتصنيع الزراعي'),
    'أراب للتنمية': ('ARAB', 'المطورون العرب القابضة'),
    'المطورون العرب': ('ARAB', 'المطورون العرب القابضة'),
    'النساجون': ('ORWE', 'النساجون الشرقيون للسجاد'),
    'مطاحن مصر العليا': ('UFMH', 'مطاحن مصر العليا'),
    'جولدن تكس': ('GTEX', 'جولدن تكس للاصواف'),
    'فيركيم': ('FERC', 'فيركيم مصر للاسمدة والكيماويات'),
    'الخليجية الكندية': ('AGIG', 'الخليجية الكندية للاستثمار العقاري العربي'),
    'الدولية للمحاصيل': ('IFAP', 'الدولية للمحاصيل الزراعية'),
    'الدولية للأسمدة': ('ICFC', 'الدولية للأسمدة والكيماويات'),
    'مدينة مصر': ('MASR', 'مدينة مصر للإسكان والتعمير'),
    'طلعت مصطفى': ('TMGH', 'مجموعة طلعت مصطفى القابضة'),
    'إعمار مصر': ('EMFD', 'إعمار مصر للتنمية'),
    'سيدي كرير': ('SKPC', 'سيدي كرير للبتروكيماويات - سيدبك'),
    'أبو قير': ('ABUK', 'أبو قير للأسمدة والصناعات الكيماوية'),
    'موبكو': ('MFPC', 'مصر لإنتاج الأسمدة - موبكو'),
    'كيما': ('EGCH', 'الصناعات الكيماوية المصرية - كيما'),
    'بلتون': ('BTFH', 'بلتون المالية القابضة'),
    'إي اف جي': ('HRHO', 'مجموعة إي إف جي القابضة'),
    'هيرميس': ('HRHO', 'مجموعة إي إف جي القابضة'),
    'حديد عز': ('ESRS', 'حديد عز'),
    'السويدي': ('SWDY', 'السويدي اليكتريك'),
    'التجاري الدولي': ('COMI', 'البنك التجاري الدولي - مصر'),
    'سي اي كابيتال': ('CICH', 'سي آي كابيتال القابضة للاستثمارات المالية'),
    'مصر للالومنيوم': ('EGAL', 'مصر للألومنيوم'),
    'الغربية الاسلامية': ('GIHD', 'الغربية الإسلامية للتنمية العمرانية'),
    'الشرق الأوسط للزجاج': ('MEGM', 'الشرق الأوسط لصناعة الزجاج'),
    'كوبر': ('COPR', 'كوبر للاستثمار التجاري والتطوير العقاري'),
    'قناة السويس لتوطين': ('SCTS', 'قناة السويس لتوطين التكنولوجيا'),
    'المصرية للاتصالات': ('ETEL', 'المصرية للاتصالات'),
    'غاز مصر': ('EGAS', 'غاز مصر'),
    'أموك': ('AMOC', 'الإسكندرية للزيوت المعدنية - أموك'),
    'القلعة': ('CCAP', 'شركة القلعة للاستشارات المالية'),
    'بالم هيلز': ('PHDC', 'بالم هيلز للتعمير'),
    'سامكريت': ('SMCR', 'سامكريت مصر مهندسون ومقاولون'),
    'جلاكسو': ('BIOC', 'جلاكسو سميثكلاين - مصر'),
    'أمون': ('AMUN', 'أمون للأدوية'),
    'بايونيرز بروبرتيز': ('PRDC', 'بايونيرز بروبرتيز للتنمية العمرانية'),
    'كرستمارك': ('CRST', 'كرستمارك للمقاولات والتطوير العقاري'),
    'بنيان للتنمية': ('BONY', 'بنيان للتنمية والتجارة'),
    'إي فاينانس': ('EFIH', 'إي فاينانس للاستثمارات المالية والرقمية'),
    'اي فاينانس': ('EFIH', 'إي فاينانس للاستثمارات المالية والرقمية'),
    'مصر الجديدة': ('HELI', 'مصر الجديدة للإسكان والتعمير'),
    'الشرقية للدخان': ('EAST', 'الشرقية - إيسترن كومباني'),
    'إيسترن كومباني': ('EAST', 'الشرقية - إيسترن كومباني'),
    'أوراسكوم للتنمية': ('ORHD', 'أوراسكوم للتنمية مصر'),
    'أوراسكوم كونستراكشون': ('ORAS', 'أوراسكوم كونستراكشون بي إل سي'),
    'أوراسكوم للاستثمار': ('OIH', 'أوراسكوم للاستثمار القابضة'),
    'أوراسكوم المالية': ('OFH', 'أوراسكوم المالية القابضة'),
    'راميدا': ('RMDA', 'العاشر من رمضان للصناعات الدوائية - راميدا'),
    'جهينة': ('JUFO', 'جهينة للصناعات الغذائية'),
    'عبور لاند': ('OLFI', 'عبور لاند للصناعات الغذائية'),
    'إيديتا': ('EFID', 'إيديتا للصناعات الغذائية'),
    'دومتي': ('DOMT', 'الصناعات الغذائية العربية - دومتي'),
    'الإسكندرية للحاويات': ('ALCN', 'الإسكندرية لتداول الحاويات والبضائع'),
    'القابضة المصرية الكويتية': ('EKHO', 'القابضة المصرية الكويتية'),
    'كريدي أجريكول': ('CIEB', 'بنك كريدي أجريكول مصر'),
    'أبوظبي الإسلامي': ('ADIB', 'مصرف أبوظبي الإسلامي - مصر'),
    'التعمير والإسكان': ('HDBK', 'بنك التعمير والإسكان'),
    'بنك قناة السويس': ('CANA', 'بنك قناة السويس'),
    'بنك البركة': ('SAUD', 'بنك البركة مصر'),
    'بنك فيصل': ('FAIT', 'بنك فيصل الإسلامي المصري'),
    'ليسيكو': ('LCSW', 'ليسيكو مصر'),
    'دايس': ('DSCW', 'دايس للملابس الجاهزة'),
    'كابو': ('KABO', 'النصر للملابس والمنسوجات - كابو'),
    'سبيد ميديكال': ('SPMD', 'سبيد ميديكال'),
    'كليوباترا': ('CLHO', 'مستشفيات كليوباترا'),
    'ماكرو جروب': ('MCRO', 'ماكرو جروب للمستحضرات الطبية'),
    'تعليم': ('TALM', 'تعليم لخدمات الإدارة'),
    'سيرا': ('CIRA', 'القاهرة للاستثمار والتنمية العقارية - سيرا'),
    'كونتكت': ('CNFN', 'كونتكت المالية القابضة'),
    'راية القابضة': ('RAYA', 'راية القابضة للاستثمارات المالية'),
    'راية لخدمات': ('RACC', 'راية لخدمات مراكز الاتصالات'),
    'ام ام جروب': ('MTIE', 'ام ام جروب للصناعة والتجارة العالمية'),
    'بي انفستمنتس': ('BINV', 'بي انفستمنتس القابضة'),
    'أكت فاينانشال': ('ACTF', 'أكت فاينانشال للاستشارات'),
    'مصر للأسمنت قنا': ('MCQE', 'مصر للأسمنت - قنا'),
    'أسمنت سيناء': ('SCEM', 'أسمنت سيناء'),
    'العربية للأسمنت': ('ARCC', 'العربية للأسمنت'),
    'جنوب الوادي': ('SVCE', 'جنوب الوادي للأسمنت'),
    'زهراء المعادي': ('ZMID', 'زهراء المعادي للاستثمار والتعمير'),
    'الشمس للإسكان': ('ELSH', 'الشمس للإسكان والتعمير'),
    'المتحدة للإسكان': ('UNIT', 'المتحدة للإسكان والتعمير'),
    'القاهرة للإسكان': ('ELKA', 'القاهرة للإسكان والتعمير'),
    'الجيزة العامة للمقاولات': ('GGCC', 'الجيزة العامة للمقاولات والاستثمار العقاري'),
    'المقاولات المصرية': ('MOIN', 'المقاولات المصرية - مختار ابراهيم'),
    'النصر للأعمال المدنية': ('NCCW', 'النصر للأعمال المدنية'),
    'المشروعات الصناعية': ('IEEC', 'المشروعات الصناعية والهندسية'),
    'عتاقة': ('ATQA', 'مصر الوطنية للصلب - عتاقة'),
    'أسكوم': ('ASCM', 'أسيك للتعدين - أسكوم'),
    'أجواء': ('AJWA', 'أجواء للصناعات الغذائية'),
    'المنصورة للدواجن': ('MPCO', 'المنصورة للدواجن'),
    'الإسماعيلية مصر للدواجن': ('ISMA', 'الإسماعيلية مصر للدواجن'),
    'شارم دريمز': ('SDTI', 'شارم دريمز للاستثمار السياحي'),
    'رمكو': ('RTVC', 'رمكو لإنشاء القرى السياحية'),
    'المصرية للمنتجعات': ('EGTS', 'المصرية للمنتجعات السياحية'),
}

GULF_EXCLUDE_KEYWORDS = [
    'ريال', 'دينار', 'درهم', 'تاسي', 'بورصة الكويت', 'بورصة مسقط',
    'سوق دبي', 'أبوظبي للأوراق', 'مسقط للغازات', 'صافولا', 'ريدان',
    'أمانة للتأمين', 'تداول السعودية', 'سوق الأسهم السعودية'
]

def _norm_ar(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r'[أإآ]', 'ا', s)
    s = s.replace('ة', 'ه').replace('ى', 'ي').replace('ـ', '')
    return s

# Dynamically load 280+ canonical EGX stocks from web/src/lib/ai/stock-names.ts if available
try:
    _names_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'web', 'src', 'lib', 'ai', 'stock-names.ts')
    if os.path.exists(_names_path):
        _content = open(_names_path, encoding='utf-8').read()
        for _sym, _nar in re.findall(r'([A-Z0-9]+):\s*\{\s*name_ar:\s*"([^"]+)"', _content):
            _short = _nar.split(' - ')[0].strip()
            if len(_short) >= 5 and _short not in STOCK_MAP:
                STOCK_MAP[_short] = (_sym, _nar)
except Exception:
    pass

def parse_date(date_str):
    """Normalize date string to YYYY-MM-DD."""
    if not date_str:
        return datetime.date.today().strftime('%Y-%m-%d')
    # Try dd/mm/yyyy or dd-mm-yyyy
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{int(mth):02d}-{int(d):02d}"
    # Try RFC 2822 (e.g. Thu, 05 Nov 2026 07:46:48 GMT)
    try:
        from email.utils import parsedate_to_datetime
        dt_obj = parsedate_to_datetime(date_str)
        return dt_obj.strftime('%Y-%m-%d')
    except Exception:
        pass
    return datetime.date.today().strftime('%Y-%m-%d')

def match_stock(title_or_text):
    """Match stock symbol and official name from text."""
    if not title_or_text:
        return None, None
    # Check explicit ticker in parentheses e.g. (FWRY.CA) or (COMI)
    m = re.search(r'\(([A-Z0-9]{3,6})(?:\.CA)?\)', title_or_text)
    if m:
        sym = m.group(1)
        for kw, (s, name) in STOCK_MAP.items():
            if s == sym:
                return sym, name
        return sym, sym

    norm_text = _norm_ar(title_or_text)
    # Check keyword (longest match first)
    for kw, (sym, name) in sorted(STOCK_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in title_or_text or _norm_ar(kw) in norm_text:
            return sym, name
    return None, None

def clean_and_enrich_existing_db():
    """Remove non-EGX Gulf items and backfill stock symbols in egx_disclosures."""
    res = sb.table('egx_disclosures').select('id, symbol, company_name, title, raw_content').limit(300).execute()
    deleted = 0
    updated = 0
    for r in (res.data or []):
        full_text = f"{r.get('title') or ''} {r.get('company_name') or ''} {r.get('raw_content') or ''}"
        if any(g in full_text for g in GULF_EXCLUDE_KEYWORDS) and '.CA' not in full_text:
            sb.table('egx_disclosures').delete().eq('id', r['id']).execute()
            deleted += 1
            continue
        sym, cname = match_stock(full_text)
        if sym and (not r.get('symbol') or r.get('company_name') == 'البورصة المصرية'):
            upd = {'symbol': sym}
            if cname and (not r.get('company_name') or r.get('company_name') == 'البورصة المصرية'):
                upd['company_name'] = cname
            sb.table('egx_disclosures').update(upd).eq('id', r['id']).execute()
            updated += 1
    print(f"Cleaned {deleted} non-EGX items, enriched {updated} symbols.")

def analyze_batch_with_ai(items_batch):
    """
    Calls DeepSeek to generate professional financial analysis for a batch of disclosures.
    Returns (analyzed_items, prompt_tokens, completion_tokens).
    """
    if not DEEPSEEK_KEY:
        print("Warning: No DEEPSEEK_KEY found, using rule-based fallback.")
        return fallback_rule_based_analysis(items_batch), 0, 0

    items_prompt = []
    for i, item in enumerate(items_batch):
        items_prompt.append({
            "id": i,
            "symbol": item.get('symbol') or 'عام',
            "company": item.get('company_name'),
            "type": item.get('disclosure_type'),
            "date": item.get('disclosure_date'),
            "title": item.get('title'),
            "action": item.get('action_type'),
            "shares": item.get('shares_count'),
            "party": item.get('party_name'),
            "role": item.get('party_role'),
            "raw": item.get('raw_content')
        })

    system_prompt = (
        "You are the Lead Financial Analyst at EGX BOTS (Advanced Egyptian Stock Exchange Intelligence). "
        "Analyze each disclosure concisely for Egyptian stock traders and investors. "
        "Explain what this insider transaction or filing means in plain, sharp Arabic. "
        "Is it bullish insider accumulation (تجميع مطلعين), bearish distribution (تسييل/تخارج), "
        "free-float tightening (تجفيف أسهم), or administrative neutral? "
        "Respond strictly with a JSON object containing an array 'disclosures' matching the order of input items."
    )

    user_prompt = f"""
قم بتحليل قائمة الإفصاحات التالية بالبورصة المصرية بدقة واحترافية:
{json.dumps(items_prompt, ensure_ascii=False, indent=2)}

المطلوب إرجاع JSON فقط بالهيكل التالي:
{{
  "disclosures": [
    {{
      "id": 0,
      "ai_summary": "شرح وتحليل مركز من 2 إلى 3 أسطر باللغة العربية يوضح دلالة الإفصاح للمستثمر وما يعكسه من ثقة الإدارة أو خروج كبار الملاك وتأثيره على المعروض بالسوق",
      "sentiment": "bullish" أو "bearish" أو "neutral",
      "key_takeaway": "خلاصة في جملة واحدة مكثفة"
    }}
  ]
}}
"""

    headers = {
        'Authorization': f'Bearer {DEEPSEEK_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': 0.2,
        'response_format': {'type': 'json_object'}
    }

    try:
        resp = requests.post('https://api.deepseek.com/chat/completions', headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            usage = data.get('usage', {})
            p_tok = usage.get('prompt_tokens', 0)
            c_tok = usage.get('completion_tokens', 0)
            content = json.loads(data['choices'][0]['message']['content'])
            res_list = content.get('disclosures', [])
            
            # Map back to items
            for r in res_list:
                idx = r.get('id')
                if idx is not None and 0 <= idx < len(items_batch):
                    items_batch[idx]['ai_summary'] = r.get('ai_summary', '')
                    items_batch[idx]['sentiment'] = r.get('sentiment', 'neutral')
                    items_batch[idx]['metadata']['key_takeaway'] = r.get('key_takeaway', '')
            return items_batch, p_tok, c_tok
        else:
            print(f"DeepSeek API error ({resp.status_code}): {resp.text[:200]}")
            return fallback_rule_based_analysis(items_batch), 0, 0
    except Exception as e:
        print(f"DeepSeek call exception: {e}")
        return fallback_rule_based_analysis(items_batch), 0, 0

def fallback_rule_based_analysis(items):
    """Deterministic financial rule-based analysis fallback."""
    for it in items:
        action = it.get('action_type', '')
        shares = it.get('shares_count')
        sym = it.get('symbol') or ''
        role = it.get('party_role') or ''
        
        if action == 'buy':
            it['sentiment'] = 'bullish'
            shares_txt = f"{shares:,} سهم" if shares else "كمية أسهم"
            it['ai_summary'] = (
                f"شراء مطلعين أو مجموعات مرتبطة بكمية {shares_txt} يعكس ثقة مباشرة من الإدارة أو كبار الملاك في القيمة العادلة للسهم ({sym}). "
                "يعد هذا مؤشراً إيجابياً داعماً للأسعار مع تقليص المعروض البيعي في السوق."
            )
            it['metadata']['key_takeaway'] = "شراء مطلعين داعم للاتجاه الصاعد"
        elif action == 'sell':
            it['sentiment'] = 'bearish'
            shares_txt = f"{shares:,} سهم" if shares else "كمية أسهم"
            it['ai_summary'] = (
                f"بيع أو تخارج جزئي من طرف داخلي أو مجموعة مرتبطة بكمية {shares_txt} في سهم ({sym}). "
                "يُنصح بالحذر ومراقبة مستويات الدعم الفنية لاحتمال وجود ضغط بيعي مؤقت من قبل المطلعين."
            )
            it['metadata']['key_takeaway'] = "تسييل داخلي يستوجب الحذر"
        elif it.get('disclosure_type') == 'major_shareholders':
            it['sentiment'] = 'neutral'
            it['ai_summary'] = (
                f"إفصاح رسمي دوري لهيكل المساهمين ومجلس الإدارة لشركة ({sym}) وفقاً للمادة 30. "
                "يوضح استقرار حصص السيطرة ونسبة الأسهم حرة التداول المتاحة للمضاربة والاستثمار."
            )
            it['metadata']['key_takeaway'] = "تحديث تنظيمي لهيكل الملكية"
        else:
            it['sentiment'] = 'neutral'
            it['ai_summary'] = f"إفصاح رسمي صادر عن الشركة ({sym}) بالبورصة المصرية يتضمن قرارات تنظيمية ومعلومات جوهرية تخص المستثمرين."
            it['metadata']['key_takeaway'] = "إفصاح جوهري للمتابعة"
    return items

def build_disclosures_dataset(max_count=150):
    """
    Harvests all recent disclosures from insider reports and company announcements.
    Returns up to max_count structured items.
    """
    disclosures = []
    seen = set()

    # 1. Parse session 04/11/2026 PDF if available
    pdf_path = 'scratch/insider_2.pdf'
    if os.path.exists(pdf_path):
        try:
            reader = PdfReader(pdf_path)
            txt = reader.pages[0].extract_text()
            for line in txt.split('\n'):
                line = line.strip()
                if not line or 'الورقة المالية' in line or 'تعاملات الداخليين' in line:
                    continue
                
                # Format: <Company> <Party/Role> <Action: شراء/بيع> <Shares>
                m = re.search(r'^(.*?)(مجموعة مرتبطة.*|داخلي)(شراء|بيع)(\d+)$', line)
                if m:
                    comp, role, action, shares = m.groups()
                    comp = comp.strip()
                    role = role.strip()
                    action_type = 'buy' if action == 'شراء' else 'sell'
                    shares_cnt = int(shares)
                    
                    sym, official_name = match_stock(comp)
                    title = f"{action} {role} {shares_cnt:,} سهم في {official_name or comp}"
                    key = (sym, '2026-11-04', title)
                    if key not in seen:
                        seen.add(key)
                        disclosures.append({
                            'symbol': sym,
                            'company_name': official_name or comp,
                            'disclosure_type': 'insider_trading',
                            'disclosure_date': '2026-11-04',
                            'title': title,
                            'raw_content': f"الشركة: {official_name or comp}\nالمتعامل: {role}\nالعملية: {action} {shares_cnt:,} سهم\nجلسة: 2026-11-04",
                            'action_type': action_type,
                            'shares_count': shares_cnt,
                            'party_name': role,
                            'party_role': 'داخلي' if 'داخلي' in role else 'مجموعة مرتبطة',
                            'source_url': 'https://static.mubasher.info/File.Mix_Announcement_File/06152F35-6E05-4299-AD5C-C82D2A9F45D3.pdf',
                            'metadata': {'session': '2026-11-04', 'source': 'EGX Daily Bulletin'}
                        })
        except Exception as e:
            print(f"Error parsing insider PDF: {e}")

    # 2. Add Prime Holding Article 30 (06/07/2026 - Q2)
    disclosures.append({
        'symbol': 'PRMH',
        'company_name': 'برايم القابضة للاستثمارات المالية',
        'disclosure_type': 'major_shareholders',
        'disclosure_date': '2026-07-06',
        'title': 'دخول عصر الذهب بحصة 14.99% وتخفيض الحرقان لحصته وتجفيف التداول الحر لـ 28.8%',
        'raw_content': 'نموذج إفصاح المادة 30: دخول شركة عصر الذهب بحصة 14.99% (52.4M سهم) لتصل حصتها مع جون وحيد إلى 24.99%. خفض فهد الحرقان حصته إلى 17.5% (-26.1M سهم). تخارج محمد البشري (9.19%). انخفاض الأسهم حرة التداول من 45.04% إلى 28.81%.',
        'action_type': 'holding_change',
        'shares_count': 52467000,
        'stake_before': 9.999,
        'stake_after': 24.990,
        'party_name': 'عصر الذهب لتجارة الذهب (مجموعة جون وحيد)',
        'party_role': 'مساهم رئيسي ومجموعة مرتبطة',
        'source_url': 'https://static.mubasher.info/File.Mix_Announcement_File/7803FAAE-86CA-42C0-9183-76FD6A55316A.pdf',
        'metadata': {'free_float_before': 45.04, 'free_float_after': 28.81}
    })

    # 3. Add Samcrete Article 30
    disclosures.append({
        'symbol': 'SMCR',
        'company_name': 'سامكريت مصر مهندسون ومقاولون',
        'disclosure_type': 'major_shareholders',
        'disclosure_date': '2026-04-10',
        'title': 'إفصاح هيكل المساهمين: سامكريت للاستثمار تستحوذ على 99.62% والأسهم الحرة 0.21%',
        'raw_content': 'نموذج إفصاح المادة 30: شركة سامكريت للإستثمار الهندسي تستحوذ على 2,988,463 سهم بنسبة 99.62%. الأسهم حرة التداول 6,234 سهم فقط بنسبة 0.21% من إجمالي 3 ملايين سهم.',
        'action_type': 'holding_change',
        'shares_count': 2988463,
        'stake_before': 99.62,
        'stake_after': 99.62,
        'party_name': 'شركة سامكريت للإستثمار الهندسي',
        'party_role': 'مساهم مسيطر',
        'source_url': 'https://static.mubasher.info/File.Story_File/%D8%B3%D8%A7%D9%85%D9%83%D8%B1%D9%8A%D8%AA%20%D9%85%D8%B5%D8%B1%20-%20%D9%85%D9%87%D9%86%D8%AF%D8%B3%D9%88%D9%86%20%D9%88%D9%85%D9%82%D8%A7%D9%88%D9%84%D9%88%D9%86%20-%20%D9%86%D9%85%D9%88%D8%B0%D8%AC%20%D8%AA%D9%82%D8%B1%D9%8A%D8%B1%20%D8%A5%D9%81%D8%B5%D8%A7%D8%AD.pdf',
        'metadata': {'free_float_after': 0.21}
    })

    # 4. Load from scratch/all_raw_disclosures.json
    raw_path = 'scratch/all_raw_disclosures.json'
    if os.path.exists(raw_path):
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        for title, it in raw_data.items():
            t = re.sub(r'\s*-\s*معلومات مباشر.*$', '', title).strip()
            link = it.get('link')
            pub = it.get('pub')
            parsed_d = parse_date(pub)
            
            # Skip if already added
            sym, official_name = match_stock(t)
            
            # Action type
            action_type = 'general'
            if 'خفض حصته' in t or 'تراجع' in t or 'بيع' in t:
                action_type = 'sell'
            elif 'رفع حصته' in t or 'شراء' in t or 'زيادة' in t:
                action_type = 'buy'
            elif 'مجلس إدارة' in t or 'قرارات' in t:
                action_type = 'resolution'
                
            # Disclosure type
            d_type = 'material_event'
            if 'تعاملات الداخليين' in t:
                d_type = 'insider_trading'
            elif 'هيكل المساهمين' in t or 'نموذج تقرير إفصاح' in t:
                d_type = 'major_shareholders'
            elif 'مجلس إدارة' in t:
                d_type = 'board_resolution'
            elif 'أرباح' in t or 'قوائم' in t:
                d_type = 'financial_results'
                
            key = (sym, parsed_d, t[:50])
            if key not in seen:
                seen.add(key)
                disclosures.append({
                    'symbol': sym,
                    'company_name': official_name or (sym if sym else 'البورصة المصرية'),
                    'disclosure_type': d_type,
                    'disclosure_date': parsed_d,
                    'title': t,
                    'raw_content': f"الإفصاح: {t}\nالتاريخ: {parsed_d}\nالمصدر: البورصة المصرية - مباشر",
                    'action_type': action_type,
                    'shares_count': None,
                    'party_name': 'الشركة / كبار المساهمين',
                    'party_role': 'مساهم رئيسي / إدارة',
                    'source_url': link,
                    'metadata': {'raw_title': t, 'pub_date': pub}
                })

    # Sort disclosures by date DESC
    disclosures.sort(key=lambda x: x['disclosure_date'], reverse=True)
    return disclosures[:max_count]

def main():
    print("=" * 70)
    print("🚀 بدء مزامنة إفصاحات البورصة المصرية وتحليلها بالذكاء الاصطناعي...")
    print("=" * 70)

    dataset = build_disclosures_dataset(max_count=150)
    print(f"📦 تم جمع وتجهيز {len(dataset)} إفصاحاً مستهدفاً للمزامنة.")

    # Check already synced in Supabase
    try:
        res = sb.table('egx_disclosures').select('title, disclosure_date').execute()
        existing = set((r.get('title'), r.get('disclosure_date')) for r in res.data)
        print(f"📊 عدد الإفصاحات الموجودة مسبقاً في قاعدة البيانات: {len(existing)}")
    except Exception as e:
        print(f"Notice: Could not fetch existing disclosures: {e}")
        existing = set()

    items_to_sync = [d for d in dataset if (d['title'], d['disclosure_date']) not in existing]
    print(f"⚡ إفصاحات جديدة مطلوب تحليلها وإدخالها: {len(items_to_sync)}")

    if not items_to_sync:
        print("✅ جميع الإفصاحات مدخلة ومحدثة مسبقاً! لا حاجة لاستهلاك توكنز جديدة.")
        return

    # Process in batches of 5 with DeepSeek
    batch_size = 5
    total_prompt_tokens = 0
    total_completion_tokens = 0
    synced_records = []

    for i in range(0, len(items_to_sync), batch_size):
        batch = items_to_sync[i:i + batch_size]
        print(f"🧠 جاري تحليل الدفعة {i//batch_size + 1} / {(len(items_to_sync) + batch_size - 1)//batch_size} ({len(batch)} إفصاحات)...")
        
        analyzed_batch, p_tok, c_tok = analyze_batch_with_ai(batch)
        total_prompt_tokens += p_tok
        total_completion_tokens += c_tok
        
        # Insert into Supabase
        try:
            insert_res = sb.table('egx_disclosures').insert(analyzed_batch).execute()
            synced_records.extend(analyzed_batch)
            print(f"  ✅ تم حفظ {len(analyzed_batch)} إفصاح بنجاح في Supabase.")
        except Exception as e:
            print(f"  ❌ خطأ أثناء إدخال الدفعة في Supabase: {e}")

    # Cost calculation (DeepSeek V3 prices: $0.14 / 1M prompt, $0.28 / 1M completion)
    prompt_cost = (total_prompt_tokens / 1_000_000) * 0.14
    comp_cost = (total_completion_tokens / 1_000_000) * 0.28
    total_cost_usd = prompt_cost + comp_cost
    total_cost_egp = total_cost_usd * 49.5  # Approximate USD/EGP

    print("\n" + "=" * 70)
    print("🎯 تقرير المزامنة واستهلاك التوكنز النهائي:")
    print("=" * 70)
    print(f"• إجمالي الإفصاحات المحفوظة: {len(synced_records)}")
    print(f"• توكنز الإدخال (Prompt Tokens): {total_prompt_tokens:,}")
    print(f"• توكنز الإخراج (Completion Tokens): {total_completion_tokens:,}")
    print(f"• إجمالي التوكنز المستخدمة: {total_prompt_tokens + total_completion_tokens:,}")
    print(f"• التكلفة بالدولار: ${total_cost_usd:.5f}")
    print(f"• التكلفة بالجنيه المصري: {total_cost_egp:.4f} ج.م فقط!")
    print("=" * 70)

if __name__ == '__main__':
    main()
