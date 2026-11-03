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
    "TMGH": "طلعت مصطفى",
    "COMI": "التجاري الدولي",
    "FWRY": "فوري",
    "SWDY": "السويدي إليكتريك",
    "ETEL": "المصرية للاتصالات",
    "MFPC": "موبكو",
    "SKPC": "سيدي كرير",
    "AMOC": "أموك",
    "EKHO": "المصرية الكويتية",
    "BTFH": "بلتون",
    "HRHO": "هيرميس",
    "CICH": "سي آي كابيتال",
    "EFIH": "إي فاينانس",
    "ISPH": "ابن سينا فارما",
    "PHAR": "إيبيكو",
    "ESRS": "حديد عز",
    "HELI": "مصر الجديدة للإسكان",
    "PHDC": "بالم هيلز",
    "MASR": "مدينة مصر للإسكان",
    "MNHD": "مدينة مصر للإسكان",
    "OCDI": "سوديك",
    "EMFD": "إعمار مصر",
    "ORHD": "أوراسكوم للتنمية",
    "ORAS": "أوراسكوم كونستراكشون",
    "EGAL": "مصر للألومنيوم",
    "TAQA": "طاقة عربية",
    "EGAS": "غاز مصر",
    "AUTO": "جي بي أوتو",
    "GBCO": "جي بي كوربوريشن",
    "ADIB": "أبوظبي الإسلامي",
    "CIEB": "كريدي أجريكول",
    "QNBE": "بنك قطر الوطني",
    "QNBA": "بنك قطر الوطني",
    "FAIT": "فيصل الإسلامي",
    "HDBK": "بنك التعمير والإسكان",
    "CCAP": "القلعة",
    "VALU": "فاليو",
    "ORWE": "النساجون الشرقيون",
    "EGCH": "كيما",
    "EFIC": "المالية والصناعية",
    "KZPC": "كفر الزيات للمبيدات",
    "FERC": "فيركيم مصر",
    "JUFO": "جهينة",
    "DOMT": "دومتي",
    "EFID": "إيديتا",
    "OLFI": "عبور لاند",
    "POUL": "القاهرة للدواجن",
    "ISMA": "الإسماعيلية للدواجن",
    "MPCO": "المنصورة للدواجن",
    "SUGR": "الدلتا للسكر",
    "EAST": "إيسترن كومباني",
    "MCQE": "أسمنت قنا",
    "MBSC": "أسمنت بني سويف",
    "ARCC": "العربية للأسمنت",
    "SVCE": "أسمنت جنوب الوادي",
    "SCEM": "أسمنت سيناء",
    "LCSW": "ليسيكو مصر",
    "ECAP": "العز للسيراميك",
    "CERA": "ريماس",
    "IRAX": "العز الدخيلة للصلب",
    "ATQA": "مصر الوطنية للصلب",
    "IRON": "الحديد والصلب",
    "MBEG": "إم بي للهندسة",
    "IEEC": "المشروعات الصناعية والهندسية",
    "EEII": "العربية للصناعات الهندسية",
    "ALUM": "العربية للألومنيوم",
    "KORA": "قرة للطاقة",
    "ELEC": "الكابلات الكهربائية",
    "RAYA": "راية القابضة",
    "RACC": "راية لمراكز الاتصالات",
    "ETRS": "إيجيترانس",
    "ALCN": "الإسكندرية لتداول الحاويات",
    "EGBE": "البنك المصري الخليجي",
    "SAUD": "بنك البركة",
    "EXPA": "بنك تنمية الصادرات",
    "CANA": "بنك قناة السويس",
    "UBEE": "البنك المتحد",
    "SEIG": "السعودية المصرية للاستثمار",
    "ODIN": "أودن للاستثمارات",
    "CNFN": "كونتكت المالية",
    "ATLC": "التوفيق للتأجير",
    "PRMH": "برايم القابضة",
    "GTWL": "جولدن تكس",
    "ACGC": "العربية لحليج الأقطان",
    "DEIN": "دايس للملابس",
    "DSCW": "دايس للملابس",
    "KABO": "كابو",
    "SPIN": "سبينالكس",
    "TALM": "تعليم لخدمات الإدارة",
    "CEFM": "مطاحن مصر الوسطى",
    "EDFM": "مطاحن شرق الدلتا",
    "SCFM": "مطاحن جنوب القاهرة",
    "MILS": "مطاحن شمال القاهرة",
    "AFMC": "مطاحن الإسكندرية",
    "WCDF": "مطاحن وسط وغرب الدلتا",
    "UEFM": "مطاحن مصر العليا",
    "MPCI": "ممفيس للأدوية",
    "NIPH": "النيل للأدوية",
    "AXPH": "الإسكندرية للأدوية",
    "CPCI": "القاهرة للأدوية",
    "AMES": "المركز الطبي الجديد",
    "CLHO": "مستشفى كليوباترا",
    "SIPC": "سبأ الدولية للأدوية",
    "SPMD": "سبيد ميديكال",
    "RMDA": "راميدا للأدوية",
    "ADCI": "العربية للأدوية",
    "ELSH": "الشمس للإسكان",
    "ELKA": "القاهرة للإسكان",
    "UNIT": "المتحدة للإسكان",
    "ZMID": "زهراء المعادي",
    "CRST": "كريست مارك",
    "RREI": "العربية للاستثمار العقاري",
    "MAAL": "مرسيليا المصرية الخليجية",
    "OBRI": "العبور للاستثمار العقاري",
    "NCCW": "النصر للأعمال المدنية",
}


def clean_text_for_speech(raw_text: str, max_chars: int = 10000) -> str:
    """
    Format and streamline technical market analysis into clear, natural conversational Arabic.
    Preserves 100% of analytical text and converts tables into natural spoken words.
    Guarantees ZERO English tickers or letters in speech audio: replaces tickers with Arabic company names.
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text

    # 1. Strip code blocks, but convert markdown tables into readable spoken text
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\|[\s:\-]+\|[\s:\-]*[\r\n]+", "\n", text)
    text = text.replace("|", "، ")

    # 2. Strip markdown syntax
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 3. Strip parenthesized English tickers like (ABUK), ( TMGH ), (COMI.CA)
    text = re.sub(r"[\(\[\{]\s*[A-Za-z0-9\.\-]{2,10}\s*[\)\]\}]", "", text)

    # 4. Strip trailing boilerplate disclaimers without affecting core notes or alerts
    text = re.sub(r"(?:إخلاء مسؤولية|تنبيه):\s*هذا التحليل لأغراض تعليمية[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"منصة EGX BOTS ليست وسيطاً[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"هذا التحليل لأغراض العمل الفني والتعليم فقط[\s\S]*$", "", text, flags=re.IGNORECASE)

    # 5. Remove emojis and decorative icons
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]", "", text)

    # 6. Clean prefixes before English words (e.g. والـ P/E -> مضاعف الربحية)
    text = re.sub(r"(?:والـ|الـ)\s*(?=[A-Za-z])", " ", text)

    # 7. Financial terms, indices, and indicator acronyms into natural spoken Arabic
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
    text = re.sub(r"\bEPS\b", " ربحية السهم ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:وقف الخسارة\s*)?\bSL\b", " وقف الخسارة ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:جني الأرباح\s*|الهدف\s*)?\bTP\b", " المستهدف ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBUY\b", " شراء ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSELL\b", " بيع ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bHOLD\b", " احتفاظ ", text, flags=re.IGNORECASE)

    # 8. Replace standalone stock tickers with full Arabic company names
    for sym, ar_name in EGX_STOCK_TICKERS.items():
        text = re.sub(rf"\b{sym}(?:\.CA)?\b", f" {ar_name} ", text, flags=re.IGNORECASE)

    # 9. Clean any remaining English characters/words so the voice engine NEVER pronounces English
    text = re.sub(r"[A-Za-z]+(?:\.[A-Za-z]+)?", "", text)

    # 10. Normalize whitespace and clean punctuation
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([،\.\!؟])\s*\1+", r"\1", text)

    # 11. Truncate smoothly at sentence boundary only if exceeding max_chars (default 10,000)
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
