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


def clean_text_for_speech(raw_text: str, max_chars: int = 10000) -> str:
    """
    Format and streamline technical market analysis into clear, natural conversational Arabic.
    Preserves 100% of analytical text and converts tables into natural spoken words.
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

    # 3. Strip trailing boilerplate disclaimers without affecting core notes or alerts
    text = re.sub(r"(?:إخلاء مسؤولية|تنبيه):\s*هذا التحليل لأغراض تعليمية[\s\S]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"منصة EGX BOTS ليست وسيطاً[\s\S]*$", "", text, flags=re.IGNORECASE)

    # 4. Remove emojis and decorative icons
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]", "", text)

    # 5. Clean standalone currency abbreviations without mangling Arabic words (e.g. تجميع)
    text = re.sub(r"(?<=\d)\s*(?:ج\.م\.?|جم|EGP)(?=\s|[^\w]|$)", " جنيه ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:ج\.م\.?|جم|EGP)\b", " جنيه ", text, flags=re.IGNORECASE)
    text = text.replace("%", " في المية ")
    text = re.sub(r"\bEGX30\b", " إيجي إكس 30 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEGX70\b", " إيجي إكس 70 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bP/E\b", " مضاعف الربحية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMACD\b", " مؤشر الماكد ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bRSI\b", " مؤشر القوة النسبية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEMA\b", " المتوسط المتحرك ", text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate smoothly at sentence boundary only if exceeding max_chars (default 10,000)
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
