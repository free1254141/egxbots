"""
api/routers/voice.py — Free Real-Time Neural Text-to-Speech (TTS) for ARTORO
Powered by Microsoft Edge Neural Voices (zero-cost, low latency, Egyptian Arabic).
"""
from __future__ import annotations

import io
import re
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
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


def clean_text_for_speech(raw_text: str, max_chars: int = 500) -> str:
    """
    Format and streamline technical market analysis into clear, natural conversational Arabic.
    Strips raw markdown syntax, markdown tables, and decorative symbols.
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text

    # 1. Strip code blocks and markdown table structures
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\|[^\n]+\|", "", text)

    # 2. Extract leading executive summary if available
    summary_match = re.search(
        r"(?:ملخص تنفيذي|الرأي التوليفي|خلاصة القول|القرار الفني|الخلاصة)[:\s]+([^\n#]{30,250})",
        text,
    )
    lead = summary_match.group(1).strip() if summary_match else ""

    # 3. Strip markdown syntax
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 4. Remove emojis and decorative icons
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[•–—▶️◀️⚡📈📉🎯🚨✅❌🔍⚖️💼📊💎👑🤖🔥📌💡⚠️🛑~_\^]", "", text)

    # 5. Clean standalone currency abbreviations without mangling Arabic words (e.g. تجميع)
    text = re.sub(r"(?:\b|\d\s*)(?:ج\.م\.?|جم|EGP)(?:\b|\s*)", " جنيه ", text, flags=re.IGNORECASE)
    text = text.replace("%", " في المية ")
    text = re.sub(r"\bEGX30\b", " إيجي إكس 30 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEGX70\b", " إيجي إكس 70 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bP/E\b", " مضاعف الربحية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMACD\b", " مؤشر الماكد ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bRSI\b", " مؤشر القوة النسبية ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEMA\b", " المتوسط المتحرك ", text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if lead and lead not in text[:120]:
        text = f"{lead}. {text}"

    # Truncate smoothly at sentence boundary if exceeding max_chars
    if len(text) > max_chars:
        cut = text[:max_chars]
        last_punct = max(cut.rfind("."), cut.rfind("،"), cut.rfind("!"), cut.rfind("؟"))
        if last_punct > 120:
            text = cut[:last_punct + 1]
        else:
            text = cut

    return text.strip()


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = DEFAULT_VOICE
    rate: Optional[str] = "+0%"
    pitch: Optional[str] = "+0Hz"
    max_chars: Optional[int] = 500


@router.get("/voices")
async def list_available_voices():
    """List supported Arabic and Egyptian neural voices."""
    return {"ok": True, "default_voice": DEFAULT_VOICE, "voices": AVAILABLE_VOICES}


@router.post("/tts")
async def stream_tts(req: TTSRequest):
    """
    Synthesize text into natural spoken Egyptian Arabic audio (MP3).
    Streams audio directly to client with 0-cost and sub-second start latency.
    """
    if not edge_tts:
        raise HTTPException(status_code=500, detail="edge-tts library is not installed on this server")

    spoken_text = clean_text_for_speech(req.text, max_chars=req.max_chars or 500)
    if not spoken_text:
        raise HTTPException(status_code=400, detail="Text is empty or could not be processed for speech")

    voice = req.voice if req.voice in AVAILABLE_VOICES else DEFAULT_VOICE

    try:
        communicate = edge_tts.Communicate(
            text=spoken_text,
            voice=voice,
            rate=req.rate or "+0%",
            pitch=req.pitch or "+0Hz",
        )

        async def audio_stream():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        headers = {
            "Content-Disposition": "inline; filename=speech.mp3",
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
            "X-Spoken-Text": spoken_text[:100].encode("ascii", "ignore").decode(),
        }

        return StreamingResponse(
            audio_stream(),
            media_type="audio/mpeg",
            headers=headers,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {str(e)}")


@router.get("/tts")
async def stream_tts_get(
    text: str = Query(..., description="Text to synthesize"),
    voice: Optional[str] = Query(DEFAULT_VOICE, description="Voice ID"),
):
    """Convenience GET endpoint for direct HTML5 <audio src="..."> tags."""
    return await stream_tts(TTSRequest(text=text, voice=voice))
