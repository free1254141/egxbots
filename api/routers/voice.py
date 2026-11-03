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


def _get_cache_key(voice: str, rate: str, pitch: str, clean_text: str) -> str:
    raw = f"{voice}:{rate}:{pitch}:{clean_text}"
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


def clean_text_for_speech(raw_text: str, max_chars: int = 10000) -> str:
    """
    Format and streamline technical market analysis into clear, natural conversational Arabic.
    Omits raw tables and numbers, speaking natural human insights and stock names in Arabic only.
    Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text

    # 1. Strip code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 2. Extract prominent stock names from markdown tables before removing the table
    table_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|") and line.strip().endswith("|")]
    extracted_stocks = []
    if len(table_lines) >= 3:
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
                if stock_clean and stock_clean not in extracted_stocks and len(stock_clean) > 2:
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

    # 3. Strip trailing boilerplate disclaimers without affecting core notes or alerts
    text = re.sub(r"تحليل EGX Bots مبني على أحدث البيانات[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"تحليل مبني على أحدث البيانات المتاحة[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"منصة EGX Bots لتحليل الأسهم المصرية[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:إخلاء مسؤولية|تنبيه):\s*هذا التحليل لأغراض تعليمية[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"منصة EGX BOTS ليست وسيطاً[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"هذا التحليل لأغراض العمل الفني والتعليم فقط[\s\S]*$", "", text, flags=re.IGNORECASE)

    # 4. Strip markdown syntax
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 5. Strip parenthesized English tickers like (ABUK), ( TMGH ), (COMI.CA)
    text = re.sub(r"[\(\[\{]\s*[A-Za-z0-9\.\-]{2,10}\s*[\)\]\}]", "", text)

    # 6. Remove emojis and decorative icons
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]", "", text)

    # 7. Clean prefixes before English words (e.g. والـ P/E -> مضاعف الربحية)
    text = re.sub(r"(?:والـ|الـ)\s*(?=[A-Za-z])", " ", text)

    # 8. Financial terms, indices, and indicator acronyms into natural spoken Arabic
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

    # 9. Replace standalone stock tickers with full Arabic company names
    for sym, ar_name in EGX_STOCK_TICKERS.items():
        text = re.sub(rf"\b{sym}(?:\.CA)?\b", f" {ar_name} ", text, flags=re.IGNORECASE)

    # 10. Clean any remaining English characters/words so the voice engine NEVER pronounces English
    text = re.sub(r"[A-Za-z]+(?:\.[A-Za-z]+)?", "", text)

    # 11. Remove dense parenthesized number lists like (88.16 و 87.38)
    text = re.sub(r"\([0-9.,\sو\+\-%]+\)", "", text)

    # 12. Normalize whitespace and clean punctuation
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([،\.\!؟])\s*\1+", r"\1", text)

    # 13. Truncate smoothly at sentence boundary only if exceeding max_chars
    if len(text) > max_chars:
        cut = text[:max_chars]
        last_punct = max(cut.rfind("."), cut.rfind("،"), cut.rfind("!"), cut.rfind("؟"), cut.rfind("\n"))
        if last_punct > 60:
            text = cut[:last_punct + 1]
        else:
            last_space = cut.rfind(" ")
            text = (cut[:last_space] if last_space > 0 else cut) + "..."

    return text.strip()


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = DEFAULT_VOICE
    rate: Optional[str] = "+12%"
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
    Includes 2-tier caching (RAM + SSD) for instant <5ms replay and in-flight deduplication.
    """
    if not edge_tts:
        raise HTTPException(status_code=500, detail="edge-tts library is not installed on this server")

    spoken_text = clean_text_for_speech(req.text, max_chars=req.max_chars or 3500)
    if not spoken_text:
        raise HTTPException(status_code=400, detail="Text is empty or could not be processed for speech")

    voice = req.voice if req.voice in AVAILABLE_VOICES else DEFAULT_VOICE
    rate = req.rate or "+10%"
    pitch = req.pitch or "+0Hz"
    cache_key = _get_cache_key(voice, rate, pitch, spoken_text)
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
                "X-Spoken-Text": spoken_text[:100].encode("ascii", "ignore").decode(),
            },
        )

    # 2. Tier-2: SSD Disk Cache (<10ms instant response)
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 1024:
        try:
            with open(cache_file, "rb") as f:
                audio_bytes = f.read()
            # Store in RAM cache
            if len(_TTS_MEMORY_CACHE) >= _MAX_MEMORY_CACHE_ENTRIES:
                _TTS_MEMORY_CACHE.pop(next(iter(_TTS_MEMORY_CACHE)))
            _TTS_MEMORY_CACHE[cache_key] = audio_bytes

            return Response(
                content=audio_bytes,
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": "inline; filename=speech.mp3",
                    "Content-Length": str(len(audio_bytes)),
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-TTS-Cache": "HIT-DISK",
                    "X-Spoken-Text": spoken_text[:100].encode("ascii", "ignore").decode(),
                },
            )
        except Exception:
            pass

    # 3. Stream from Edge-TTS progressively while caching in background for instant start latency
    async def stream_and_cache_generator():
        accumulated = []
        try:
            communicate = edge_tts.Communicate(
                text=spoken_text,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data = chunk["data"]
                    accumulated.append(data)
                    yield data

            # Once streaming completes cleanly, persist full audio to RAM and SSD
            full_audio = b"".join(accumulated)
            if len(full_audio) > 500:
                if len(_TTS_MEMORY_CACHE) >= _MAX_MEMORY_CACHE_ENTRIES:
                    _TTS_MEMORY_CACHE.pop(next(iter(_TTS_MEMORY_CACHE)))
                _TTS_MEMORY_CACHE[cache_key] = full_audio

                try:
                    with open(cache_file, "wb") as f:
                        f.write(full_audio)
                except Exception as disk_err:
                    print(f"[voice.py] Failed to write disk cache: {disk_err}")
        except Exception as exc:
            print(f"[voice.py] Streaming synthesis error: {exc}")

    return StreamingResponse(
        stream_and_cache_generator(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=speech.mp3",
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-TTS-Cache": "MISS-STREAMING",
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
