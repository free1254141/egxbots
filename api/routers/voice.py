"""
api/routers/voice.py — Free Real-Time Neural Text-to-Speech (TTS) for ARTORO
Powered by Microsoft Edge Neural Voices (zero-cost, low latency, Egyptian Arabic).
"""
from __future__ import annotations

import io
import os
import re
import asyncio
import hashlib
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    import edge_tts
except ImportError:
    edge_tts = None

router = APIRouter(prefix="/voice", tags=["Voice & Audio"])

# Default voice: Natural Egyptian Male for ARTORO
DEFAULT_VOICE = "ar-EG-ShakirNeural"

AVAILABLE_VOICES = {
    "ar-EG-ShakirNeural": "شاكر (مصري طبيعي — صوت أرتورو الرسمي)",
    "ar-EG-SalmaNeural": "سلمى (مصري طبيعي نسائي)",
    "ar-SA-HamedNeural": "حامد (عربي فصيح)",
}

# Cache directory on disk for zero-delay instant replay
TTS_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "tts")
os.makedirs(TTS_CACHE_DIR, exist_ok=True)

# In-memory LRU cache: maps cache_key -> bytes
_TTS_MEMORY_CACHE: dict[str, bytes] = {}
_MAX_MEMORY_CACHE_ENTRIES = 500

# In-flight synthesis registry. The chat route pre-warms the exact same text/voice
# that the browser is about to request; without this, both requests would run a
# full neural synthesis in parallel and the browser would still wait for the
# second (cold) run. Concurrent callers now share one synthesis task.
_TTS_INFLIGHT: dict[str, "asyncio.Task"] = {}

# Optional premium provider (ElevenLabs). Enabled only when BOTH the API key and
# a voice id are configured, so the zero-cost Edge neural voice remains default.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()


def _tts_provider() -> str:
    return "elevenlabs" if (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID) else "edge"


def _get_cache_key(provider: str, voice: str, rate: str, pitch: str, clean_text: str) -> str:
    raw = f"{provider}:{voice}:{rate}:{pitch}:{clean_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Comprehensive Egyptian Stock Exchange (EGX) Symbol to Arabic Company Name Dictionary
# Guarantees that the TTS audio engine NEVER speaks English tickers/letters, and always speaks Arabic names.
EGX_STOCK_TICKERS: dict[str, str] = {
    "ABUK": "أبو قير للأسمدة",
    "ACAMD": "العربية لاستصلاح الأراضي",
    "ACGC": "العربية لحليج الأقطان",
    "ADCI": "العربية للأدوية",
    "ADIB": "أبوظبي الإسلامي",
    "AFMC": "مطاحن الإسكندرية",
    "AIFI": "الإسكندرية للاستثمارات المالية",
    "AIH": "العروبة للسمسرة",
    "AJWA": "أجواء للصناعات الغذائية",
    "ALCN": "الإسكندرية لتداول الحاويات",
    "ALEX": "الإسكندرية للغزل والنسيج",
    "ALUM": "العربية للألومنيوم",
    "AMER": "عامر جروب",
    "AMES": "المركز الطبي الجديد",
    "AMIA": "العربية للمحابس",
    "AMOC": "أموك",
    "ANFI": "الإسكندرية الوطنية للإلكترونيات",
    "ARAB": "المطورون العرب",
    "ARCC": "العربية للأسمنت",
    "ARVA": "الإسكندرية للخدمات الطبية",
    "ATCP": "العربية للتجارة والتوزيع",
    "ATLC": "التوفيق للتأجير",
    "ATQA": "مصر الوطنية للصلب",
    "AUTO": "جي بي أوتو",
    "AXPH": "الإسكندرية للأدوية",
    "BINV": "بي انفستمنتس",
    "BIOC": "بي بي أو كابيتال",
    "BOLA": "بدر الدين للمقاولات",
    "BRAQ": "البراق للاستثمارات",
    "BTFH": "بلتون",
    "CANA": "بنك قناة السويس",
    "CCAP": "القلعة للاستشارات",
    "CEFM": "مطاحن مصر الوسطى",
    "CERA": "ريماس",
    "CFGH": "كونكريت فاشون",
    "CHSH": "القناة للتوكيلات الملاحية",
    "CICH": "سي آي كابيتال",
    "CIEB": "كريدي أجريكول",
    "CLHO": "مستشفى كليوباترا",
    "CMRI": "العامة للصوامع والتخزين",
    "CNFN": "كونتكت المالية",
    "COMI": "التجاري الدولي",
    "COSG": "القاهرة للزيوت",
    "CPCI": "القاهرة للأدوية",
    "CPPC": "القاهرة للأدوية",
    "CRST": "كريست مارك",
    "CSAG": "القناة للتوكيلات الملاحية",
    "DAPH": "مصر للأسمنت قنا",
    "DEIN": "دايس للملابس",
    "DOMT": "دومتي",
    "DSCW": "دايس للملابس",
    "EAST": "الشرقية للدخان",
    "ECAP": "العز للسيراميك الجوهرة",
    "ECAZ": "العز للسيراميك الجوهرة",
    "EDFM": "مطاحن شرق الدلتا",
    "EEII": "العربية للصناعات الهندسية",
    "EFIC": "المالية والصناعية المصرية",
    "EFID": "إيديتا للصناعات الغذائية",
    "EFIH": "إي فاينانس",
    "EGAL": "مصر للألومنيوم",
    "EGAS": "غاز مصر",
    "EGBE": "البنك المصري الخليجي",
    "EGCH": "كيما للأسمدة",
    "EHDR": "المصريين للإسكان",
    "EKHO": "المصرية الكويتية القابضة",
    "EKHOA": "المصرية الكويتية",
    "ELEC": "الكابلات الكهربائية",
    "ELKA": "القاهرة للإسكان",
    "ELNA": "النصر للملابس كابو",
    "ELSH": "الشمس للإسكان",
    "ELWA": "الوادى للاستثمار السياحي",
    "EMFD": "إعمار مصر للتنمية",
    "EPPC": "الأهرام للطباعة",
    "EPPK": "الأهرام للطباعة",
    "ESRS": "حديد عز",
    "ETEL": "المصرية للاتصالات",
    "ETRS": "إيجيترانس",
    "EXPA": "بنك تنمية الصادرات",
    "FAIT": "بنك فيصل الإسلامي",
    "FENG": "فيركيم مصر للأسمدة",
    "FERC": "فيركيم مصر للأسمدة",
    "FWRY": "فوري للمدفوعات الإلكترونية",
    "GBCO": "جي بي كوربوريشن",
    "GDWA": "جدوى للتنمية الصناعية",
    "GEBE": "المصرية لتطوير صناعة البناء ليفت سلاب",
    "GMCI": "العامة لمنتجات الخزف والصيني شيني",
    "GOCO": "الخليجية الكندية للاستثمار",
    "GTWL": "جولدن تكس للأصواف",
    "HDBK": "بنك التعمير والإسكان",
    "HELI": "مصر الجديدة للإسكان",
    "HRHO": "إي إف جي القابضة هيرميس",
    "IBMD": "ابن سينا فارما",
    "IDHC": "التشخيص المتكاملة القابضة",
    "IDRE": "رواد السياحة",
    "IEEC": "المشروعات الصناعية والهندسية",
    "IFAP": "الدولية للأسمدة والكيماويات",
    "IIOC": "الدولية للتأجير التمويلي إينكوليس",
    "INCO": "المؤشر للبرمجيات",
    "IPMC": "المطاحن المصرية",
    "IRAX": "العز الدخيلة للصلب",
    "IRON": "الحديد والصلب المصرية",
    "ISMA": "الإسماعيلية للدواجن",
    "ISPH": "ابن سينا فارما",
    "JUFO": "جهينة للصناعات الغذائية",
    "KABO": "كابو للملابس",
    "KABR": "كفر الزيات للمبيدات",
    "KORA": "قرة للطاقة",
    "KZPC": "كفر الزيات للمبيدات",
    "LCSW": "ليسيكو مصر",
    "MAAL": "مرسيليا المصرية الخليجية",
    "MASR": "مدينة مصر للإسكان والتعمير",
    "MBEG": "إم بي للهندسة",
    "MBSC": "أسمنت بني سويف",
    "MCQE": "أسمنت قنا",
    "MEPA": "الشرق الأوسط لصناعة الزجاج",
    "MFPC": "موبكو للأسمدة",
    "MILS": "مطاحن شمال القاهرة",
    "MIPH": "مينا فارم للأدوية",
    "MNHD": "مدينة مصر للإسكان",
    "MOIL": "الخدمات الملاحية والبترولية ماريديف",
    "MPCI": "ممفيس للأدوية",
    "MPCO": "المنصورة للدواجن",
    "MRCO": "مرسى علم للتنمية السياحية",
    "NCCW": "النصر للأعمال المدنية",
    "NDRL": "ناشيونال دريلنج",
    "NIPH": "النيل للأدوية",
    "OBRI": "العبور للاستثمار العقاري",
    "OCDI": "سوديك السادس من أكتوبر للتنمية",
    "ODIN": "أودن للاستثمارات المالية",
    "OFH": "أوراسكوم المالية القابضة",
    "OIFI": "أوراسكوم للاستثمار القابضة",
    "OLFI": "عبور لاند للصناعات الغذائية",
    "ORAS": "أوراسكوم كونستراكشون",
    "ORHD": "أوراسكوم للتنمية مصر",
    "ORWE": "النساجون الشرقيون",
    "PHAR": "إيبيكو للأدوية",
    "PHDC": "بالم هيلز للتعمير",
    "POUL": "القاهرة للدواجن",
    "PRCL": "العامة لمنتجات الخزف والصيني",
    "PRDC": "الرواد للسياحة",
    "PRMH": "برايم القابضة للاستثمارات",
    "QNBA": "بنك قطر الوطني الأهلي",
    "QNBE": "بنك قطر الوطني",
    "RACC": "راية لمراكز الاتصالات",
    "RAKT": "العامة لصناعة الورق راكتا",
    "RAYA": "راية القابضة للاستثمارات المالية",
    "REAC": "العقارية للبنوك الوطنية للتنمية",
    "RMDA": "العاشر من رمضان للأدوية راميدا",
    "ROTO": "رواد مصر للاستثمار السياحي",
    "RREI": "العربية للاستثمار العقاري",
    "SAIB": "بنك الشركة المصرفية",
    "SAUD": "بنك البركة مصر",
    "SCEM": "أسمنت سيناء",
    "SCFM": "مطاحن جنوب القاهرة",
    "SEIG": "السعودية المصرية للاستثمار والتمويل",
    "SIPC": "سبأ الدولية للأدوية",
    "SKPC": "سيدي كرير للبتروكيماويات",
    "SNFC": "الشرقية الوطنية للأمن الغذائي",
    "SPIN": "سبينالكس للإسكندرية للغزل والنسيج",
    "SPMD": "سبيد ميديكال",
    "SUGR": "الدلتا للسكر",
    "SVCE": "أسمنت جنوب الوادي",
    "SWDY": "السويدي إليكتريك",
    "TALM": "تعليم لخدمات الإدارة",
    "TAQA": "طاقة عربية",
    "TMGH": "مجموعة طلعت مصطفى",
    "TRTO": "ترانس أوكاشنز",
    "UBEE": "البنك المتحد",
    "UEFM": "مطاحن مصر العليا",
    "UNIP": "يونيباك للورق والكرتون",
    "UNIT": "المتحدة للإسكان والتعمير",
    "VALU": "فاليو",
    "VERT": "فيرتيكا للبرمجيات",
    "WCDF": "مطاحن وسط وغرب الدلتا",
    "ZMID": "زهراء المعادي للاستثمار والتعمير",
}


ARABIC_MONTH_NAMES: dict[str, str] = {
    "01": "يناير", "1": "يناير",
    "02": "فبراير", "2": "فبراير",
    "03": "مارس", "3": "مارس",
    "04": "أبريل", "4": "أبريل",
    "05": "مايو", "5": "مايو",
    "06": "يونيو", "6": "يونيو",
    "07": "يوليو", "7": "يوليو",
    "08": "أغسطس", "8": "أغسطس",
    "09": "سبتمبر", "9": "سبتمبر",
    "10": "أكتوبر",
    "11": "نوفمبر",
    "12": "ديسمبر",
}


def clean_text_for_speech(raw_text: str, max_chars: int = 10000) -> str:
    """
    Format and streamline technical market analysis into clear, natural conversational Arabic.
    Omits raw tables and numbers, speaking natural human insights and stock names in Arabic only.
    Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
    Converts numbers >= 1,000 million into billions (مليار جنيه) to prevent '6 آلاف مليون' anomalies.
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text

    # 1. Strip code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 2. Extract prominent stock names ONLY from markdown stock screener/ranking tables
    table_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|") and line.strip().endswith("|")]
    extracted_stocks = []
    non_stock_terms = {
        "الإغلاق", "الإغلاق الحالي", "الدعم", "الدعم الأول", "الدعم الثاني",
        "المقاومة", "المقاومة الأولى", "المقاومة الثانية", "المؤشر", "المقياس",
        "المستوى / النقطة", "المستوى", "النقطة", "القيمة", "الوصف الفني",
        "سكور التقييم الشامل", "القيمة السوقية", "السعر العادل", "التوزيعات النقدية",
        "التوافق الشرعي", "ربحية السهم", "مضاعف الربحية", "الاتجاه", "القرار", "الحجم النسبي"
    }

    if len(table_lines) >= 3:
        header_row = table_lines[0]
        is_stock_list_table = any(k in header_row for k in ["السهم", "الشركة", "الرمز", "الكود"])
        if is_stock_list_table:
            for row in table_lines[2:]:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                if cells and cells[0]:
                    stock_cell = cells[0]
                    stock_clean = re.sub(r"\([A-Za-z0-9\.\-]+\)", "", stock_cell).strip()
                    for sym, ar in EGX_STOCK_TICKERS.items():
                        if re.search(rf"\b{sym}\b", stock_cell, re.IGNORECASE):
                            stock_clean = ar
                            break
                    stock_clean = re.sub(r"[A-Za-z0-9\.\-]+", "", stock_clean).strip()
                    if (
                        stock_clean
                        and stock_clean not in non_stock_terms
                        and stock_clean not in extracted_stocks
                        and len(stock_clean) > 2
                    ):
                        extracted_stocks.append(stock_clean)
                    if len(extracted_stocks) >= 4:
                        break

    # Replace markdown table blocks with a single smooth transitional sentence
    table_replacement = ""
    if extracted_stocks:
        table_replacement = f"\nومن أبرز الأسهم في القائمة: {'، و'.join(extracted_stocks)}، والجدول التفصيلي كامل بجميع الأسعار معروض على شاشتك.\n"
    elif table_lines:
        table_replacement = "\nوالجدول التفصيلي كامل بجميع الأسعار والنسب معروض على شاشتك.\n"

    # Completely remove all markdown table blocks
    text = re.sub(r"(?:^[ \t]*\|[^\n]+\|[ \t]*(?:\r?\n)?)+", lambda m: table_replacement, text, flags=re.MULTILINE)
    text = re.sub(r"\|[^\n]+\|", "", text)

    # 2b. Strip market breadth statistical preamble and dense stock count parentheticals
    # E.g. 'سياق السوق: 184 سهم صاعد مقابل 41 هابط... وإجمالي تداول 6,750 مليون جنيه'
    text = re.sub(r"(?:سياق السوق|سياق الجلسة|حالة السوق|أداء المؤشر)[:\s*]+[^\n]+(?:\r?\n)?", "", text)
    text = re.sub(r"\b\d+\s+سهم\s+صاعد\s+مقابل\s+\d+\s+هابط[^\n\.]*[\.\n]?", "", text)
    text = re.sub(r"\(من\s+\d+\s+سهماً:[^)]+\)", "", text)

    # 3. Strip visual table headers/titles (e.g. جدول أسهم التجميع)
    text = re.sub(r"جدول\s+(?:أسهم\s+التجميع|فحص\s+كامل|الأسهم|الفرز|المؤشرات|التحليل)(?:\s*\([^)]*\))?[:\s]*", "", text)

    # 4. Convert numeric dates like 03-11-2026 or 2026-11-03 into spoken Arabic months
    text = re.sub(r"\b(\d{1,2})[-/](\d{1,2})[-/](202\d)\b", lambda m: f"{int(m.group(1))} {ARABIC_MONTH_NAMES.get(m.group(2), m.group(2))} {m.group(3)}", text)
    text = re.sub(r"\b(202\d)[-/](\d{1,2})[-/](\d{1,2})\b", lambda m: f"{int(m.group(3))} {ARABIC_MONTH_NAMES.get(m.group(2), m.group(2))} {m.group(1)}", text)

    # 5. Naturalize large financial numbers: convert >= 1,000 million to billions (مليار جنيه)
    # E.g. "6,750.79 مليون جنيه" -> "6.75 مليار جنيه"
    def _millions_to_billions(m):
        raw_num = m.group(1).replace(",", "")
        has_currency = "جنيه" in m.group(0)
        try:
            val = float(raw_num)
            if val >= 1000:
                billions = round(val / 1000.0, 2)
                billions_str = f"{billions:.2f}".rstrip("0").rstrip(".")
                return f"{billions_str} مليار جنيه" if has_currency else f"{billions_str} مليار"
        except ValueError:
            pass
        return m.group(0)

    text = re.sub(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)\s*مليون(?:\s*جنيه)?", _millions_to_billions, text)

    # 6. Convert numerical ratios like 4.49:1 or 4.49 : 1 to "4.5 إلى 1"
    def _ratio_replace(m):
        try:
            r1 = round(float(m.group(1)), 1)
            r1_str = f"{r1}".rstrip("0").rstrip(".")
            return f"{r1_str} إلى {m.group(2)}"
        except ValueError:
            return f"{m.group(1)} إلى {m.group(2)}"
    text = re.sub(r"(\d+(?:\.\d+)?)\s*:\s*(\d+)", _ratio_replace, text)

    # 7. Strip trailing boilerplate disclaimers without affecting core notes or alerts
    text = re.sub(r"تحليل EGX Bots مبني على أحدث البيانات[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"تحليل مبني على أحدث البيانات المتاحة[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"منصة EGX Bots لتحليل الأسهم المصرية[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:إخلاء مسؤولية|تنبيه):\s*هذا التحليل لأغراض تعليمية[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"منصة EGX BOTS ليست وسيطاً[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"هذا التحليل لأغراض العمل الفني والتعليم فقط[\s\S]*$", "", text, flags=re.IGNORECASE)

    # 8. Strip markdown syntax
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 9. Strip parenthesized English tickers like (ABUK), ( TMGH ), (COMI.CA)
    text = re.sub(r"[\(\[\{]\s*[A-Za-z0-9\.\-]{2,10}\s*[\)\]\}]", "", text)

    # 10. Remove emojis and decorative icons
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]", "", text)

    # 11. Clean prefixes before English words (e.g. والـ P/E -> مضاعف الربحية)
    text = re.sub(r"(?:والـ|الـ)\s*(?=[A-Za-z])", " ", text)

    # 12. Financial terms, indices, and indicator acronyms into natural spoken Arabic
    text = re.sub(r"(?<=\d)\s*(?:ج\.م\.?|جم|EGP)(?=\s|[^\w]|$)", " جنيه ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:ج\.م\.?|جم|EGP)\b", " جنيه ", text, flags=re.IGNORECASE)
    text = text.replace("%", " في المية ")
    text = re.sub(r"\bEGX30\b", " إيجي إكس 30 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEGX70\b", " إيجي إكس 70 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEGX100\b", " إيجي إكس 100 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEGX\b", " البورصة المصرية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUSD\b", " دولار ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:مؤشر\s*)?\bRSI\b", " مؤشر القوة النسبية ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:مؤشر\s*)?\bMACD\b", " مؤشر الماكد ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:متوسط\s*)?\bEMA\b", " المتوسط المتحرك ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:متوسط\s*)?\bSMA\b", " المتوسط المتحرك ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bP/E\b", " مضاعف الربحية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bP/B\b", " القيمة الدفترية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEPS\b", " ربحية السهم ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:وقف الخسارة\s*)?\bSL\b", " وقف الخسارة ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:جني الأرباح\s*|الهدف\s*)?\bTP\b", " المستهدف ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBUY\b", " شراء ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSELL\b", " بيع ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bHOLD\b", " احتفاظ ", text, flags=re.IGNORECASE)

    # 13. Replace standalone stock tickers with full Arabic company names
    for sym, ar_name in EGX_STOCK_TICKERS.items():
        text = re.sub(rf"\b{sym}(?:\.CA)?\b", f" {ar_name} ", text, flags=re.IGNORECASE)

    # 14. Clean any remaining English characters/words so the voice engine NEVER pronounces English
    text = re.sub(r"[A-Za-z]+(?:\.[A-Za-z]+)?", "", text)

    # 15. Remove dense parenthesized number lists like (88.16 و 87.38)
    text = re.sub(r"\([0-9.,\sو\+\-%]+\)", "", text)

    # 16. Natural prosody: line breaks and list markers become soft pauses instead
    # of one long run-on sentence, and punctuation pile-ups are removed so the
    # neural voice does not stumble or produce robotic gaps.
    text = re.sub(r"[ \t]*\r?\n+[ \t]*", "، ", text)
    text = re.sub(r"(?:^|\s)[-*•]\s+", "، ", text)
    text = re.sub(r"\s*[:：]\s*(?=[\u0600-\u06FF])", "، ", text)
    text = re.sub(r"\s+(لكن|ولكن|إلا أن|بينما|في المقابل)\s+", r"، \1 ", text)
    text = re.sub(r"(?:،\s*){2,}", "، ", text)
    text = re.sub(r"\s+([،\.!؟])", r"\1", text)
    text = re.sub(r"([،\.!؟])\s*\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[،\s]+", "", text)
    # End with a full stop so the voice gets a clean, confident close.
    if text and text[-1] not in ".!؟":
        text += "."

    # 17. Truncate smoothly at sentence boundary only if exceeding max_chars
    if len(text) > max_chars:
        cut = text[:max_chars]
        last_punct = max(cut.rfind("."), cut.rfind("،"), cut.rfind("!"), cut.rfind("؟"), cut.rfind("\n"))
        if last_punct > 60:
            text = cut[:last_punct + 1]
        else:
            last_space = cut.rfind(" ")
            text = (cut[:last_space] if last_space > 0 else cut) + "..."

    return text.strip()


def _synthesize_elevenlabs_sync(text: str, rate: str) -> bytes:
    """Premium human-like voice via ElevenLabs (optional, only when configured)."""
    import requests

    speed = 1.0
    match = re.match(r"^\s*([+-])(\d+(?:\.\d+)?)%", rate or "")
    if match:
        delta = float(match.group(2)) / 100.0
        speed = 1.0 + (delta if match.group(1) == "+" else -delta)
    speed = max(0.7, min(1.2, speed))

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": ELEVENLABS_MODEL_ID,
            "output_format": "mp3_44100_128",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.8,
                "style": 0.12,
                "use_speaker_boost": True,
                "speed": speed,
            },
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.content


async def _synthesize_edge(text: str, voice: str, rate: str, pitch: str) -> bytes:
    """Zero-cost Microsoft Edge neural voice (default)."""
    if not edge_tts:
        raise RuntimeError("edge-tts library is not installed on this server")
    chunks: list[bytes] = []
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def _synthesize_audio(text: str, voice: str, rate: str, pitch: str) -> tuple[bytes, str]:
    """Synthesize with the configured provider, falling back to Edge on failure."""
    if _tts_provider() == "elevenlabs":
        try:
            audio = await asyncio.to_thread(_synthesize_elevenlabs_sync, text, rate)
            if audio and len(audio) > 500:
                return audio, "elevenlabs"
        except Exception as exc:
            print(f"[voice.py] ElevenLabs failed, falling back to Edge: {exc}")
    return await _synthesize_edge(text, voice, rate, pitch), "edge"


def _remember_in_ram(cache_key: str, audio: bytes) -> None:
    if len(audio) < 500:
        return
    if cache_key not in _TTS_MEMORY_CACHE and len(_TTS_MEMORY_CACHE) >= _MAX_MEMORY_CACHE_ENTRIES:
        _TTS_MEMORY_CACHE.pop(next(iter(_TTS_MEMORY_CACHE)))
    _TTS_MEMORY_CACHE[cache_key] = audio


def _store_audio(cache_key: str, cache_file: str, audio: bytes) -> None:
    _remember_in_ram(cache_key, audio)
    if len(audio) < 500:
        return
    try:
        with open(cache_file, "wb") as f:
            f.write(audio)
    except Exception as disk_err:
        print(f"[voice.py] Failed to write disk cache: {disk_err}")


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = DEFAULT_VOICE
    rate: Optional[str] = "+10%"
    pitch: Optional[str] = "+0Hz"
    max_chars: Optional[int] = 10000


@router.get("/voices")
async def list_available_voices():
    """List supported Arabic and Egyptian neural voices."""
    return {"ok": True, "default_voice": DEFAULT_VOICE, "voices": AVAILABLE_VOICES}


@router.post("/tts")
async def stream_tts(req: TTSRequest):
    """
    Synthesize text into natural spoken Egyptian Arabic audio (MP3).

    Caching tiers:
      1. Process RAM — instant replay.
      2. SSD — instant after the first synthesis (survives restarts).
      3. Single-flight — the chat pre-warm and the browser share one neural
         synthesis instead of racing each other and doing the work twice.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required for TTS")

    spoken_text = clean_text_for_speech(req.text, max_chars=req.max_chars or 3500)
    if not spoken_text:
        raise HTTPException(status_code=400, detail="Text is empty or could not be processed for speech")

    voice = req.voice if req.voice in AVAILABLE_VOICES else DEFAULT_VOICE
    rate = req.rate or "+10%"
    pitch = req.pitch or "+0Hz"
    provider = _tts_provider()
    cache_key = _get_cache_key(provider, voice, rate, pitch, spoken_text)
    cache_file = os.path.join(TTS_CACHE_DIR, f"{cache_key}.mp3")

    # 1. Tier-1: RAM Memory Cache (0ms instant response)
    if cache_key in _TTS_MEMORY_CACHE:
        audio_bytes = _TTS_MEMORY_CACHE[cache_key]
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3",
                "Content-Length": str(len(audio_bytes)),
                "Cache-Control": "public, max-age=31536000, immutable",
                "X-TTS-Cache": "HIT-RAM",
                "X-TTS-Provider": provider,
                "X-Spoken-Text": spoken_text[:100].encode("ascii", "ignore").decode(),
            },
        )

    # 2. Tier-2: SSD Disk Cache (<10ms instant response)
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 1024:
        try:
            with open(cache_file, "rb") as f:
                audio_bytes = f.read()
            _remember_in_ram(cache_key, audio_bytes)
            return Response(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": "inline; filename=speech.mp3",
                    "Content-Length": str(len(audio_bytes)),
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-TTS-Cache": "HIT-DISK",
                    "X-TTS-Provider": provider,
                    "X-Spoken-Text": spoken_text[:100].encode("ascii", "ignore").decode(),
                },
            )
        except Exception:
            pass

    # 3. Tier-3: single-flight synthesis shared with the chat pre-warm.
    async def _build() -> tuple[bytes, str]:
        audio, used_provider = await _synthesize_audio(spoken_text, voice, rate, pitch)
        _store_audio(cache_key, cache_file, audio)
        return audio, used_provider

    inflight = _TTS_INFLIGHT.get(cache_key)
    if inflight is None:
        inflight = asyncio.create_task(_build())
        _TTS_INFLIGHT[cache_key] = inflight
        inflight.add_done_callback(lambda _task, key=cache_key: _TTS_INFLIGHT.pop(key, None))

    try:
        # shield(): a browser disconnect must not cancel the shared synthesis and
        # waste the work the pre-warm (or another listener) is waiting for.
        audio_bytes, used_provider = await asyncio.shield(inflight)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {exc}") from exc

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=speech.mp3",
            "Content-Length": str(len(audio_bytes)),
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-TTS-Cache": "MISS-SYNTHESIZED",
            "X-TTS-Provider": used_provider,
            "X-Spoken-Text": spoken_text[:100].encode("ascii", "ignore").decode(),
        },
    )


@router.get("/tts")
async def stream_tts_get(
    text: str = Query(..., description="Text to synthesize"),
    voice: Optional[str] = Query(DEFAULT_VOICE, description="Voice ID"),
    rate: Optional[str] = Query("+10%", description="Speech rate adjustment"),
):
    """Convenience GET endpoint for direct HTML5 <audio src="..."> tags with instant caching."""
    return await stream_tts(TTSRequest(text=text, voice=voice, rate=rate))
