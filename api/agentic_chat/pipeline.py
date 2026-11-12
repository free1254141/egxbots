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
from api.agentic_chat.auth_guard import filter_output, strip_dsml
from api.agentic_chat.vision import (
    analyze_image,
    reconcile_vision_with_market,
    safe_image_evidence_reply,
    safe_portfolio_image_reply,
    format_vision_context_for_prompt,
)
from api.stock_ai import _init_supabase, supabase
from api.agentic_chat.analysis_cache import get_cached_analysis, set_cached_analysis

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


def parse_dsml_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Parse DeepSeek internal DSML tool invocations if leaked in message content:
    <｜｜DSML｜｜ invoke name="get_stock">
    <｜｜DSML｜｜ parameter name="symbol" string="true">AMES</｜｜DSML｜｜ parameter>
    </｜｜DSML｜｜ invoke>
    """
    if not text or ("DSML" not in text and "dsml" not in text):
        return []
    tool_calls = []
    invoke_pattern = re.compile(
        r"<[｜|]{1,2}DSML[｜|]{1,2}\s+invoke\s+name=[\"']?([a-zA-Z0-9_-]+)[\"']?[^>]*>([\s\S]*?)<\/[｜|]{1,2}DSML[｜|]{1,2}\s+invoke>",
        re.IGNORECASE,
    )
    param_pattern = re.compile(
        r"<[｜|]{1,2}DSML[｜|]{1,2}\s+parameter\s+name=[\"']?([a-zA-Z0-9_-]+)[\"']?(?:\s+string=[\"']?(true|false)[\"']?)?[^>]*>(.*?)<\/[｜|]{1,2}DSML[｜|]{1,2}\s+parameter>",
        re.IGNORECASE | re.DOTALL,
    )

    for i, match in enumerate(invoke_pattern.finditer(text)):
        fn_name = match.group(1).strip()
        body = match.group(2)
        args = {}
        for pmatch in param_pattern.finditer(body):
            pname = pmatch.group(1).strip()
            is_str = (pmatch.group(2) or "").lower()
            pval = pmatch.group(3).strip()
            if is_str == "false":
                if pval.lower() == "true":
                    args[pname] = True
                elif pval.lower() == "false":
                    args[pname] = False
                elif pval.isdigit():
                    args[pname] = int(pval)
                else:
                    try:
                        args[pname] = float(pval)
                    except ValueError:
                        args[pname] = pval
            else:
                args[pname] = pval
        tool_calls.append({
            "id": f"call_dsml_{int(time.time()*1000)}_{i}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })
    return tool_calls


async def run_agentic_chat_stream(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    images: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model: str = "deepseek-chat",
    autonomous_recommendations: bool = False,
    is_pro: bool = True,
    remaining_quota: int = 999,
    quota_limit: int = 999,
):
    """
    Main agentic streaming generator.
    Yields Server-Sent Events (SSE) formatted as: `data: <json_or_marker>\\n\\n`
    """
    start_time = time.time()
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
            img_url = msg.get("image_url") or msg.get("imageUrl")
            if role in ("user", "assistant") and (content or img_url):
                if role == "user" and img_url:
                    formatted_messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": str(content)[:2000] if content else "صورة مرفقة"},
                            {"type": "image_url", "image_url": {"url": img_url}}
                        ]
                    })
                else:
                    formatted_messages.append({"role": role, "content": str(content)[:2000]})

    # 1. Vision Analysis Pipeline (Ported 1:1 from legacy Vercel system)
    valid_images = [img for img in (images or []) if img and isinstance(img, str) and img.strip()]
    vision_data = None
    if valid_images:
        yield f"data: {json.dumps({'type': 'status', 'status': 'vision', 'message': 'قراءة الصورة مع حفظ درجة الثقة وحدودها...'}, ensure_ascii=False)}\n\n"
        try:
            vision_data, vision_err = await analyze_image(
                image_url=valid_images,
                user_message=message,
                api_key=api_key,
                message_id=session_id or "",
            )
        except Exception as v_ex:
            logger.error(f"[agentic_chat] Vision exception: {v_ex}")
            vision_data, vision_err = None, str(v_ex)

        if vision_data:
            try:
                _init_supabase()
                vision_data = reconcile_vision_with_market(vision_data, supabase)
            except Exception as rec_ex:
                logger.warning(f"[agentic_chat] Reconcile error: {rec_ex}")

            # Send vision result events to client immediately
            yield f"data: {json.dumps({'type': 'vision_result', 'data': vision_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'vision', 'data': vision_data}, ensure_ascii=False)}\n\n"
        else:
            # Fallback when vision cannot extract anything from the image
            fallback_text = "وصلت الصورة إلى الشات، لكن تعذّر تحليلها بخدمة قراءة الصور حالياً. لذلك لم أستخرج منها رموزاً أو أرقاماً، ولم أعتمد على صورة أو بيانات سابقة. جرّب إعادة إرفاقها لاحقاً."
            words = fallback_text.split(" ")
            for i in range(0, len(words), 4):
                chunk = " ".join(words[i : i + 4]) + " "
                yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.015)

            total_lat = int((time.time() - start_time) * 1000)
            done_ev = {
                "type": "done",
                "reply": fallback_text,
                "session_id": session_id,
                "suggested_buttons": ["تحليل سهم معين", "أقوى الأسهم اليوم"],
                "tables": [],
                "latency_ms": total_lat,
                "is_pro": is_pro,
                "remaining_quota": remaining_quota,
                "quota_limit": quota_limit,
                "vision": None,
                "vision_error": vision_err or "vision_analysis_failed",
            }
            yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

    # Inject symbol hints if detected in user message, context, or vision
    hints = known_symbol_hints(message)
    if vision_data:
        vision_symbols = [
            s["symbol"].upper()
            for s in vision_data.get("symbols", [])
            if s.get("symbol")
        ]
        for vsym in vision_symbols:
            if not any(vsym in h.get("symbols", []) for h in hints):
                hints.insert(0, {"name": vsym, "symbols": [vsym]})

    if hints:
        hints_payload = {"symbol_hints": hints}
        hints_text = (
            "سياق رموز البورصة المصرية المكتشفة في استفسار المستخدم والصور المرفقة (symbol_hints):\n"
            f"{json.dumps(hints_payload, ensure_ascii=False)}\n"
            "التزم بدقة بهذه الرموز عند استدعاء الأدوات get_stock و get_stock_levels و get_comparison ولا تخترع رمزاً بديلاً."
        )
        formatted_messages.append({"role": "system", "content": hints_text})

    # Append vision context and user message
    if vision_data:
        vision_context_str = format_vision_context_for_prompt(vision_data)
        formatted_messages.append({"role": "system", "content": vision_context_str})

        clean_user_text = message.strip() if message and message.strip() else "قم بتحليل محفظتي / الصورة المرفقة وقارنها بأسعار السوق اليوم ومستويات الدعم والمقاومة."
        formatted_messages.append({"role": "user", "content": clean_user_text})

        if vision_symbols:
            prompt_instruction = (
                f"استدعِ فوراً الأدوات get_stock و get_stock_levels للرموز المستخرجة من الصورة: {', '.join(vision_symbols)} "
                f"لجلب أسعار الإغلاق اللحظية ومستويات الدعم والمقاومة، لمقارنتها بأسعار الشراء وكميات المراكز المستخرجة من الصورة وتقديم تحليل مالي وفني متكامل."
            )
            formatted_messages.append({"role": "system", "content": prompt_instruction})
    else:
        formatted_messages.append({"role": "user", "content": message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    accumulated_reply = ""
    tables_data: List[Any] = []
    recommendations_data: List[Any] = []
    tools_executed_count = 0

    # 0. Check In-Memory Analysis Cache for Repeatable Canonical Queries (Zero-Token, Zero-Latency)
    if not vision_data and (not images or len(images) == 0):
        cached_hit = get_cached_analysis(message, images=images)
        if cached_hit:
            logger.info(f"[agentic_chat] Serving from In-Memory Analysis Cache: {cached_hit.get('key')}")
            yield f"data: {json.dumps({'type': 'status', 'status': 'cached', 'message': 'تم استرجاع أحدث قراءة فنية موثقة من الذاكرة اللحظية...'}, ensure_ascii=False)}\n\n"

            cached_reply = cached_hit["reply"]
            words = cached_reply.split(" ")
            chunk_size = 5
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i : i + chunk_size]) + " "
                yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)

            total_lat = int((time.time() - start_time) * 1000)
            suggested_buttons = ["📊 تحديث المستويات الفنية", "🎯 أهداف السهم القادمة", "📈 ترشيح فرص بديلة"]
            done_ev = {
                "type": "done",
                "reply": cached_reply,
                "session_id": session_id,
                "suggested_buttons": suggested_buttons,
                "tables": cached_hit.get("tables") or [],
                "recommendations": cached_hit.get("recommendations") or [],
                "latency_ms": max(total_lat, 180),
                "is_pro": is_pro,
                "remaining_quota": remaining_quota,
                "quota_limit": quota_limit,
                "cached": True,
            }
            yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

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

                # Fallback: Intercept raw DSML markup in content if emitted instead of tool_calls
                content_raw = assistant_msg.get("content", "")
                if not tool_calls and content_raw and ("DSML" in content_raw or "dsml" in content_raw):
                    dsml_calls = parse_dsml_tool_calls(content_raw)
                    if dsml_calls:
                        logger.info(f"[agentic_chat] Intercepted {len(dsml_calls)} tool calls from raw DSML markup in content")
                        tool_calls = dsml_calls
                        assistant_msg["tool_calls"] = tool_calls
                        cleaned_content = strip_dsml(content_raw)
                        assistant_msg["content"] = cleaned_content if cleaned_content else None

                # If DeepSeek has NO more tool calls to make:
                if not tool_calls:
                    content = assistant_msg.get("content", "")
                    if not content and vision_data:
                        content = safe_image_evidence_reply(vision_data, message)
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
                logger.info(f"[agentic_chat] Phase timing: Turn{round_count}={t_turn1:.2f}s, Tools({len(tool_calls)})={t_tools:.2f}s")

                for tc, result in zip(tool_calls, tool_results):
                    tc_id = tc.get("id", f"call_{int(time.time()*1000)}")
                    if isinstance(result, Exception):
                        content_str = json.dumps({"status": "error", "message": str(result)}, ensure_ascii=False)
                    else:
                        content_str = json.dumps(result, ensure_ascii=False)
                        # Extract table data if present
                        if isinstance(result, dict):
                            if "stocks" in result and isinstance(result["stocks"], list):
                                tables_data.extend(result["stocks"])
                            elif "accumulation_stocks" in result and isinstance(result["accumulation_stocks"], list):
                                tables_data.extend(result["accumulation_stocks"])
                            if "recommendations" in result and isinstance(result["recommendations"], list):
                                recommendations_data.extend(result["recommendations"])

                    formatted_messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": content_str,
                    })

                # If reached max_rounds, break to final synthesis
                if round_count >= max_rounds:
                    break

            # If all rounds were consumed by tool calls and no text reply was generated yet:
            if tools_executed_count > 0 and not accumulated_reply:
                synthesis_payload = {
                    "model": "deepseek-chat",
                    "messages": formatted_messages,
                    "tools": AGENTIC_TOOLS_SCHEMA,
                    "tool_choice": "none",  # Forbid tools so DeepSeek produces only synthesis text
                    "temperature": 0.3,
                    "max_tokens": 4000,
                }

                yield f"data: {json.dumps({'type': 'status', 'status': 'generating', 'message': 'جاري صياغة التقرير والتحليل الفني...'}, ensure_ascii=False)}\n\n"

                t_turn2_start = time.time()
                synth_resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=synthesis_payload,
                )
                if synth_resp.status_code == 200:
                    synth_json = synth_resp.json()
                    synth_content = synth_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if synth_content:
                        accumulated_reply = filter_output(synth_content)
                        words = accumulated_reply.split(" ")
                        chunk_size = 4
                        for i in range(0, len(words), chunk_size):
                            chunk = " ".join(words[i : i + chunk_size]) + " "
                            yield f"data: {json.dumps({'type': 'token', 'token': chunk}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.015)
                else:
                    logger.error(f"[agentic_chat] Synthesis error: HTTP {synth_resp.status_code}")

                t_turn2 = time.time() - t_turn2_start
                logger.info(f"[agentic_chat] Synthesis finished: Turn2={t_turn2:.2f}s, Total={time.time()-start_time:.2f}s")

    except Exception as e:
        logger.exception(f"[agentic_chat] Unexpected exception in chat stream: {e}")
        yield f"data: {json.dumps({'type': 'error', 'detail': 'حدث خطأ أثناء معالجة المحادثة، يرجى المحاولة مرة أخرى.'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Apply compliance filter on final reply
    accumulated_reply = filter_output(accumulated_reply)

    # Cache repeatable public analyses in memory (0 tokens for subsequent queries)
    if accumulated_reply and not vision_data and (not images or len(images) == 0):
        try:
            set_cached_analysis(
                query=message,
                reply=accumulated_reply,
                tables=tables_data,
                recommendations=recommendations_data,
                images=images,
            )
        except Exception as cache_err:
            logger.warning(f"[agentic_chat] Cache set warning: {cache_err}")

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

    # 1. Recommendations Table
    if recommendations_data:
        rec_rows = []
        seen_rec = set()
        for r in recommendations_data:
            if isinstance(r, dict):
                sym = r.get("symbol") or ""
                if not sym or sym in seen_rec:
                    continue
                seen_rec.add(sym)
                name = (r.get("name") or r.get("name_ar") or sym).split(",")[0].strip()
                sig = r.get("signal") or "BUY"
                ep = f"{r.get('entry_price', '—')} ج.م" if r.get('entry_price') is not None else "—"
                tp = f"{r.get('target_price', '—')} ج.م" if r.get('target_price') is not None else "—"
                sl = f"{r.get('stop_loss', '—')} ج.م" if r.get('stop_loss') is not None else "—"
                status_txt = r.get("status") or "نشطة (مفتوحة)"
                d_str = str(r.get("date") or "")
                sharia_txt = "متوافق (EGX33)" if r.get("is_sharia_compliant") else "غير متوافق"
                rec_rows.append([sym, name, sig, ep, tp, sl, status_txt, d_str, sharia_txt])
        if rec_rows:
            excel_tables.append({
                "id": f"recs_{int(time.time())}",
                "title": "توصيات وإشارات التداول",
                "headers": ["الكود", "اسم الشركة", "الإشارة", "سعر الدخول", "المستهدف", "وقف الخسارة", "الحالة", "التاريخ", "التوافق الشرعي"],
                "rows": rec_rows,
                "source": "EGX BOTS",
                "data_time": time.strftime("%Y-%m-%d"),
            })

    # 2. Stocks Comparison Matrix or Stock Analysis Table
    if tables_data:
        merged_stocks = {}
        for s in tables_data:
            if not isinstance(s, dict) or not s.get("symbol"):
                continue
            sym = str(s["symbol"]).upper().strip()
            if sym not in merged_stocks:
                merged_stocks[sym] = dict(s)
            else:
                for k, v in s.items():
                    if v is not None and v != "" and v != "—":
                        if merged_stocks[sym].get(k) is None or merged_stocks[sym].get(k) == "" or merged_stocks[sym].get(k) == "—":
                            merged_stocks[sym][k] = v

        stocks_with_symbol = list(merged_stocks.values())[:10]  # Cap at 10 columns for clean UI display
        if len(stocks_with_symbol) >= 2:
            headers = ["المعيار"] + [f"{(s.get('name_ar') or s.get('symbol')).split(',')[0].strip()} ({s.get('symbol')})" for s in stocks_with_symbol]
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
        elif len(stocks_with_symbol) == 1:
            s = stocks_with_symbol[0]
            sym = s.get("symbol") or ""
            name = (s.get("name_ar") or sym).split(",")[0].strip()
            close_str = f"{s.get('close', '—')} ج.م" if s.get('close') is not None else "—"
            chg_str = f"{s.get('change_pct', '—')}%" if s.get('change_pct') is not None else "—"
            rsi_str = str(s.get('rsi_14', '—'))
            verdict_str = s.get('verdict') or "—"
            s1_str = f"{s.get('support_1', '—')} ج.م" if s.get('support_1') is not None else "—"
            r1_str = f"{s.get('resistance_1', '—')} ج.م" if s.get('resistance_1') is not None else "—"
            king_str = str(s.get('king_ai_score', '—'))
            sharia_str = "متوافق (EGX33)" if s.get('is_sharia_compliant') else "غير متوافق"
            excel_tables.append({
                "id": f"table_{int(time.time())}",
                "title": f"التحليل الفني لسهم {name} ({sym})",
                "headers": ["الكود", "اسم الشركة", "السعر", "التغير %", "RSI", "الدعم الأول", "المقاومة الأولى", "مؤشر King AI", "التقييم الفني", "التوافق الشرعي"],
                "rows": [[sym, name, close_str, chg_str, rsi_str, s1_str, r1_str, king_str, verdict_str, sharia_str]],
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
        "vision": vision_data,
    }

    yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
