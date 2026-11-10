"""
api/agentic_chat/pipeline.py
Core Agentic Chat Pipeline for DeepSeek V3 with Function Calling and SSE Streaming.
100% Async, Non-blocking, and Prefix-Cache Optimized.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional
import httpx
import pytz

from api.agentic_chat.prompts import AGENTIC_SYSTEM_PROMPT
from api.agentic_chat.tools_schema import AGENTIC_TOOLS_SCHEMA
from api.agentic_chat.tools_execution import dispatch_tool
from api.agentic_chat.auth_guard import filter_output

logger = logging.getLogger("agentic_chat")
CAIRO_TZ = pytz.timezone("Africa/Cairo")


def _get_deepseek_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or ""
    return key.strip()


def known_symbol_hints(message: str) -> List[Dict[str, Any]]:
    """
    Extract Egyptian stock symbol hints from Arabic company names, aliases, and tickers.
    Matches known Egyptian stock mappings (e.g. 'عتاقة' / 'عتاقه' -> 'ATQA').
    """
    if not message:
        return []
    try:
        from api.stock_aliases import ARABIC_STOCK_MAPPINGS, resolve_stock_symbol
    except Exception:
        return []

    norm_msg = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", message)
    norm_msg = re.sub(r"[أإآ]", "ا", norm_msg)
    norm_msg = re.sub(r"ة", "ه", norm_msg)
    norm_msg = re.sub(r"ى", "ي", norm_msg).lower()
    norm_msg = re.sub(r"(?:بورص[ةه]|سوق|مؤشر)\s+النيل", " ", norm_msg)

    hints: List[Dict[str, Any]] = []
    seen_symbols = set()

    # 1. Match Arabic full names and aliases, sorted longest first
    sorted_aliases = sorted(ARABIC_STOCK_MAPPINGS.items(), key=lambda x: len(x[0]), reverse=True)
    for ar_name, sym in sorted_aliases:
        norm_key = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", ar_name)
        norm_key = re.sub(r"[أإآ]", "ا", norm_key)
        norm_key = re.sub(r"ة", "ه", norm_key)
        norm_key = re.sub(r"ى", "ي", norm_key).lower()
        if len(norm_key) < 2:
            continue

        escaped = re.escape(norm_key)
        if norm_key.startswith("ال"):
            without_al = re.escape(norm_key[2:])
            pattern = rf"(?:^|[^\w\u0621-\u064a])(?:(?:و|ف|ب|ل|ك|ال)?{escaped}|لل{without_al})(?:$|[^\w\u0621-\u064a])"
        else:
            pattern = rf"(?:^|[^\w\u0621-\u064a])(?:و|ف|ب|ل|ك|ال)?{escaped}(?:$|[^\w\u0621-\u064a])"

        if re.search(pattern, norm_msg, re.IGNORECASE):
            s_upper = sym.upper()
            if s_upper not in seen_symbols:
                seen_symbols.add(s_upper)
                hints.append({"name": ar_name, "symbols": [s_upper]})

    # 2. Match Latin tickers (2-6 uppercase letters)
    latin_matches = re.findall(r"\b[A-Za-z]{2,6}\b", message)
    stopwords = {"EGX", "BUY", "SELL", "HOLD", "THE", "AND", "FOR", "RSI", "MACD", "EMA", "SMA", "VIP", "PRO", "API", "NOW", "TODAY", "NEWS", "USD", "EGP"}
    for tok in latin_matches:
        u = tok.upper()
        if u in stopwords:
            continue
        res = resolve_stock_symbol(u)
        if res and res not in seen_symbols:
            seen_symbols.add(res)
            hints.append({"name": tok, "symbols": [res]})

    return hints[:10]


async def run_agentic_chat_stream(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model: str = "deepseek-chat",
    autonomous_recommendations: bool = False,
    is_pro: bool = True,
    remaining_quota: int = 999,
    quota_limit: int = 999,
) -> AsyncGenerator[str, None]:
    """
    Main agentic streaming generator.
    Yields Server-Sent Events (SSE) formatted as: `data: <json_or_marker>\\n\\n`
    """
    api_key = _get_deepseek_key()
    if not api_key:
        err_event = {
            "type": "error",
            "detail": "مفتاح الذكاء الاصطناعي (DEEPSEEK_API_KEY) غير متاح في السيرفر."
        }
        yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Yield initial thinking status
    yield f"data: {json.dumps({'type': 'status', 'status': 'thinking', 'message': 'جاري تحليل استفسارك في البورصة المصرية...'}, ensure_ascii=False)}\n\n"

    # Static system prompt first (enables DeepSeek prefix caching)
    formatted_messages = [{"role": "system", "content": AGENTIC_SYSTEM_PROMPT}]

    # Inject dynamic Cairo timestamp and trading date in a separate message after static prompt
    now_cairo = datetime.now(CAIRO_TZ)
    date_context = (
        f"📅 الجلسة الحالية وتوقيت القاهرة الآن: {now_cairo.strftime('%Y-%m-%d %H:%M:%S')}. "
        f"جميع الأسعار والمؤشرات بالجنيه المصري (EGP). وضع التوصيات الحرة: {'مفعل' if autonomous_recommendations else 'غير مفعل'}."
    )
    formatted_messages.append({"role": "system", "content": date_context})

    # Add bounded conversation history (last 10 turns max)
    if history and isinstance(history, list):
        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                formatted_messages.append({"role": role, "content": str(content)[:2000]})

    # Inject symbol hints if detected in user message or context
    hints = known_symbol_hints(message)
    if hints:
        hints_payload = {"symbol_hints": hints}
        hints_text = (
            "سياق رموز البورصة المصرية المكتشفة في استفسار المستخدم (symbol_hints):\n"
            f"{json.dumps(hints_payload, ensure_ascii=False)}\n"
            "التزم بدقة بهذه الرموز عند استدعاء الأدوات get_stock و get_stock_levels و get_comparison ولا تخترع رمزاً بديلاً (مثل استخدام ATQA لعتاقة وعدم استبداله بـ ORAS)."
        )
        formatted_messages.append({"role": "system", "content": hints_text})

    # Append current user message
    formatted_messages.append({"role": "user", "content": message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start_time = time.time()
    accumulated_reply = ""
    tables_data: List[Any] = []
    tools_executed_count = 0

    max_rounds = 3
    round_count = 0

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            while round_count < max_rounds:
                round_count += 1

                req_payload = {
                    "model": "deepseek-chat",
                    "messages": formatted_messages,
                    "tools": AGENTIC_TOOLS_SCHEMA,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                    "max_tokens": 4000,
                }

                t_turn1_start = time.time()
                resp = None
                for attempt in range(2):
                    try:
                        resp = await client.post(
                            "https://api.deepseek.com/chat/completions",
                            headers=headers,
                            json=req_payload,
                        )
                        if resp.status_code == 200:
                            break
                        if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                            logger.warning(f"[agentic_chat] DeepSeek HTTP {resp.status_code}, retrying in 1.5s...")
                            await asyncio.sleep(1.5)
                            continue
                        break
                    except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                        if attempt == 0:
                            logger.warning(f"[agentic_chat] DeepSeek network glitch {net_err}, retrying in 1.5s...")
                            await asyncio.sleep(1.5)
                            continue
                        raise

                t_turn1 = time.time() - t_turn1_start

                if resp.status_code != 200:
                    logger.error(f"[agentic_chat] DeepSeek error: HTTP {resp.status_code} - {resp.text[:300]}")
                    yield f"data: {json.dumps({'type': 'error', 'detail': 'تعذر الاتصال بمحرك الذكاء الاصطناعي، يرجى المحاولة بعد قليل.'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                res_json = resp.json()
                choice = res_json.get("choices", [{}])[0]
                assistant_msg = choice.get("message", {})
                tool_calls = assistant_msg.get("tool_calls")

                # If DeepSeek has NO more tool calls to make:
                if not tool_calls:
                    content = assistant_msg.get("content", "")
                    if content:
                        accumulated_reply = filter_output(content)
                        # Stream the reply smoothly in natural word chunks
                        words = accumulated_reply.split(" ")
                        chunk_size = 4
                        for i in range(0, len(words), chunk_size):
                            chunk = " ".join(words[i:i+chunk_size]) + " "
                            yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.015)
                    break

                # Tool calls requested:
                tools_executed_count += len(tool_calls)
                yield f"data: {json.dumps({'type': 'status', 'status': 'executing_tools', 'message': f'جاري جلب أحدث بيانات البورصة المصرية ({len(tool_calls)} مصادر)...'}, ensure_ascii=False)}\n\n"

                # Append assistant tool-call intent to message history
                formatted_messages.append(assistant_msg)

                # Execute all tools concurrently with asyncio.gather
                t_tools_start = time.time()
                tool_tasks = []
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "")
                    try:
                        fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except Exception:
                        fn_args = {}
                    # Pass verified user_id and user_prompt for anti-injection validation
                    tool_tasks.append(dispatch_tool(fn_name, fn_args, user_id=user_id, user_prompt=message))

                tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)
                t_tools = time.time() - t_tools_start
                logger.info(f"[agentic_chat] Phase timing: Turn1={t_turn1:.2f}s, Tools({len(tool_calls)})={t_tools:.2f}s")

                for tc, result in zip(tool_calls, tool_results):
                    tc_id = tc.get("id", f"call_{int(time.time()*1000)}")
                    if isinstance(result, Exception):
                        content_str = json.dumps({"status": "error", "message": str(result)}, ensure_ascii=False)
                    else:
                        content_str = json.dumps(result, ensure_ascii=False)
                        # Extract table data if present
                        if isinstance(result, dict) and "stocks" in result and isinstance(result["stocks"], list):
                            tables_data.extend(result["stocks"])

                    formatted_messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": content_str,
                    })

                # If we've reached max_rounds or tools provided the final data, stream the final response
                if round_count >= max_rounds:
                    break

            # If tools were executed and we need to stream the final synthesis:
            if tools_executed_count > 0 and not accumulated_reply:
                stream_payload = {
                    "model": "deepseek-chat",
                    "messages": formatted_messages,
                    "stream": True,
                    "temperature": 0.3,
                    "max_tokens": 4000,
                }

                yield f"data: {json.dumps({'type': 'status', 'status': 'generating', 'message': 'جاري صياغة التقرير والتحليل الفني...'}, ensure_ascii=False)}\n\n"

                t_turn2_start = time.time()
                async with client.stream(
                    "POST",
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=stream_payload,
                ) as stream_resp:
                    if stream_resp.status_code != 200:
                        logger.error(f"[agentic_chat] Stream error: HTTP {stream_resp.status_code}")
                        yield f"data: {json.dumps({'type': 'error', 'detail': 'تعذر استكمال صياغة التحليل الفني، يرجى إعادة المحاولة.'}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    async for line in stream_resp.aiter_lines():
                        if not line:
                            continue
                        line_str = line.strip()
                        if line_str.startswith("data:"):
                            chunk_data = line_str[5:].strip()
                            if chunk_data == "[DONE]":
                                break
                            try:
                                parsed_chunk = json.loads(chunk_data)
                                delta = parsed_chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    accumulated_reply += delta
                                    yield f"data: {json.dumps({'type': 'token', 'token': delta}, ensure_ascii=False)}\n\n"
                            except Exception:
                                continue

                t_turn2 = time.time() - t_turn2_start
                logger.info(f"[agentic_chat] Synthesis stream finished: Turn2={t_turn2:.2f}s, Total={time.time()-start_time:.2f}s")

    except Exception as e:
        logger.exception(f"[agentic_chat] Unexpected exception in chat stream: {e}")
        yield f"data: {json.dumps({'type': 'error', 'detail': 'حدث خطأ أثناء معالجة المحادثة، يرجى المحاولة مرة أخرى.'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Apply compliance filter on final reply
    accumulated_reply = filter_output(accumulated_reply)

    # Suggest dynamic follow-up buttons based on context
    if "تحليل سهم" in accumulated_reply or "الدعم" in accumulated_reply or "المقاومة" in accumulated_reply:
        suggested_buttons = ["📊 تحديث المستويات الفنية", "🎯 أهداف السهم القادمة", "📈 ترشيح فرص بديلة"]
    elif "توصيات" in accumulated_reply or "شراء" in accumulated_reply:
        suggested_buttons = ["⚡ إشارات المضاربة اللحظية", "🎯 صفقات السوينغ", "🛡️ كاشف المصائد"]
    else:
        suggested_buttons = ["📈 أفضل أسهم السوق اليوم", "🔍 تحليل سهم محدد", "💼 فحص محفظتي"]

    total_latency_ms = int((time.time() - start_time) * 1000)

    # Format tables into standard ExcelTable schema expected by frontend
    excel_tables = []
    if tables_data:
        stocks_with_symbol = [s for s in tables_data if isinstance(s, dict) and s.get("symbol")]
        if len(stocks_with_symbol) >= 2:
            headers = ["المعيار"] + [f"{s.get('name_ar') or s.get('symbol')} ({s.get('symbol')})" for s in stocks_with_symbol]
            rows_list = [
                ["السعر الحالي"] + [f"{s.get('close', '—')} ج.م" if s.get('close') is not None else "—" for s in stocks_with_symbol],
                ["التغير اليومي"] + [f"{s.get('change_pct', '—')}%" if s.get('change_pct') is not None else "—" for s in stocks_with_symbol],
                ["مؤشر RSI"] + [str(s.get('rsi_14', '—')) for s in stocks_with_symbol],
                ["التقييم الفني"] + [str(s.get('verdict', '—')) for s in stocks_with_symbol],
                ["الدعم الأول"] + [f"{s.get('support_1', '—')} ج.م" if s.get('support_1') is not None else "—" for s in stocks_with_symbol],
                ["المقاومة الأولى"] + [f"{s.get('resistance_1', '—')} ج.م" if s.get('resistance_1') is not None else "—" for s in stocks_with_symbol],
                ["مؤشر King AI"] + [str(s.get('king_ai_score', '—')) for s in stocks_with_symbol],
                ["التوافق الشرعي"] + ["متوافق (EGX33)" if s.get('is_sharia_compliant') else "غير متوافق" for s in stocks_with_symbol],
            ]
            excel_tables.append({
                "id": f"comparison_{int(time.time())}",
                "title": "مقارنة الأسهم الفنية والمالية",
                "headers": headers,
                "rows": rows_list,
                "source": "EGX BOTS",
                "data_time": time.strftime("%Y-%m-%d"),
            })
        else:
            rows_list = []
            for s in tables_data:
                if isinstance(s, dict):
                    sym = s.get("symbol") or ""
                    name = s.get("name_ar") or sym
                    close_str = f"{s.get('close', '')} ج.م" if s.get('close') is not None else "—"
                    chg_str = f"{s.get('change_pct', '')}%" if s.get('change_pct') is not None else "—"
                    rsi_str = str(s.get('rsi_14', '—'))
                    verdict_str = s.get('verdict') or "—"
                    rows_list.append([sym, name, close_str, chg_str, rsi_str, verdict_str])
            if rows_list:
                excel_tables.append({
                    "id": f"table_{int(time.time())}",
                    "title": "جدول الأسهم والتحليل الفني",
                    "headers": ["الكود", "اسم الشركة", "السعر", "التغير %", "RSI", "التقييم الفني"],
                    "rows": rows_list,
                    "source": "EGX BOTS",
                    "data_time": time.strftime("%Y-%m-%d"),
                })

    # Final done event with accurate quota and pro status
    done_event = {
        "type": "done",
        "reply": accumulated_reply,
        "session_id": session_id,
        "suggested_buttons": suggested_buttons,
        "tables": excel_tables,
        "latency_ms": total_latency_ms,
        "is_pro": is_pro,
        "remaining_quota": remaining_quota,
        "quota_limit": quota_limit,
    }

    yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
