import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
import dotenv

# Load environment from web/.env.local if needed
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_base_dir, "web", ".env.local")
if os.path.exists(_env_path):
    dotenv.load_dotenv(_env_path, override=False)

from api.stock_ai import _init_supabase, supabase
from api.support_analytics import (
    get_registrations_data,
    get_activity_data,
    get_chat_history_data,
    get_platform_kpis_data,
)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-flash"
EXPERIENTIAL_API_URL = "https://api.experientiallabs.ai/v1/chat/completions"
EXPERIENTIAL_MODEL = "deepseek-v4.1-flash-uncensored"


def _get_deepseek_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or ""
    return key.strip().strip('"').strip("'")


def _get_experiential_key() -> str:
    key = os.getenv("EXPLABS_API_KEY") or os.getenv("EXPERIENTIAL_API_KEY") or ""
    return key.strip().strip('"').strip("'")


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    """Sends a chat action (e.g. typing) to Telegram to provide instant visual feedback."""
    bot_token = os.getenv("SUPPORT_BOT_TOKEN") or ""
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
    data = json.dumps({"chat_id": chat_id, "action": action}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            pass
    except Exception:
        pass


# -------------------------------------------------------------------------
# Tool Implementations
# -------------------------------------------------------------------------

def tool_get_stock_quote(symbol: str) -> Dict[str, Any]:
    """Queries technical indicators and latest price for a stock symbol."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}
    sym = (symbol or "").strip().upper()
    try:
        ind_res = (
            supabase.table("stock_technical_indicators")
            .select("symbol, date, close, volume, change_pct, rsi_14, macd, bb_upper, bb_lower, ema_20, ema_50, king_ai_score, egx_ai_score")
            .eq("symbol", sym)
            .order("date", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if not ind_res.data:
            # Fallback to stock_prices
            p_res = (
                supabase.table("stock_prices")
                .select("symbol, date, close, open, high, low, volume")
                .eq("symbol", sym)
                .order("date", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not p_res.data:
                return {"symbol": sym, "found": False, "message": f"لا توجد بيانات مسجلة لرمز {sym}"}
            return {"symbol": sym, "found": True, "price_data": p_res.data}
        return {"symbol": sym, "found": True, "indicators": ind_res.data}
    except Exception as exc:
        return {"symbol": sym, "error": str(exc)}


def tool_get_open_recommendations() -> Dict[str, Any]:
    """Queries open buy recommendations from the platform scanner engine."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}
    try:
        rec_res = (
            supabase.table("scan_results")
            .select("symbol, created_at, signal, status, entry_price, target_price, stop_loss")
            .eq("status", "open")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        recs = rec_res.data or []
        return {
            "open_recommendations_count": len(recs),
            "recommendations": recs,
            "has_open_recommendations": len(recs) > 0,
        }
    except Exception as exc:
        return {"error": str(exc)}


def tool_get_market_overview() -> Dict[str, Any]:
    """Queries market leaders (top gainers and losers) from latest technical indicators."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}
    try:
        gainers_res = (
            supabase.table("stock_technical_indicators")
            .select("symbol, date, close, change_pct, volume, rsi_14")
            .order("date", desc=True)
            .order("change_pct", desc=True)
            .limit(5)
            .execute()
        )
        losers_res = (
            supabase.table("stock_technical_indicators")
            .select("symbol, date, close, change_pct, volume, rsi_14")
            .order("date", desc=True)
            .order("change_pct", desc=False)
            .limit(5)
            .execute()
        )
        return {
            "top_gainers": gainers_res.data or [],
            "top_losers": losers_res.data or [],
        }
    except Exception as exc:
        return {"error": str(exc)}


def tool_query_market_engine(query: str) -> Dict[str, Any]:
    """Provides market/platform analysis natively in Python without calling Vercel Serverless."""
    _init_supabase()
    if not supabase:
        return {"note": "Market database directly queried", "summary": "Database unavailable"}
    
    # Extract symbol if user asked about a specific stock
    words = [w.strip(".,;:!?()[]/\\").upper() for w in (query or "").split()]
    for word in words:
        if 2 <= len(word) <= 6 and word.isalpha():
            quote = tool_get_stock_quote(word)
            if quote.get("found"):
                return {"stock_data": quote, "note": f"بيانات مباشرة من البورصة المصرية لرمز {word}"}
                
    # Default to market overview
    return tool_get_market_overview()


# -------------------------------------------------------------------------
# Tool Definitions for DeepSeek
# -------------------------------------------------------------------------

ADMIN_AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_registrations_report",
            "description": "جلب تقرير وتفاصيل المستخدمين الجدد المسجلين في المنصة (أسماء، إيميلات، هواتف، مواعيد) لتاريخ محدد أو اليوم/أمس",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "تاريخ بصيغة YYYY-MM-DD أو 'today' أو 'yesterday'",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_report",
            "description": "جلب إحصائيات النشاط والتفاعل والصفحات الأكثر استخداماً وزيارة في تاريخ محدد أو اليوم/أمس",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "تاريخ بصيغة YYYY-MM-DD أو 'today' أو 'yesterday'",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chat_history_summary",
            "description": "جلب ملخص واستفسارات محادثات الدعم الفني وشات الذكاء الاصطناعي لتاريخ محدد لمعرفة ما يسأل عنه المستخدمون",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "تاريخ بصيغة YYYY-MM-DD أو 'today' أو 'yesterday'",
                    },
                    "chat_type": {
                        "type": "string",
                        "enum": ["all", "support", "ai"],
                        "description": "نوع المحادثات المطلوب",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_platform_kpis",
            "description": "جلب المؤشرات التنفيذية الشاملة للمنصة (إجمالي المستخدمين، مشتركي VIP، المستخدمين المجاني، DAU)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_analysis",
            "description": "تحليل سهم محدد في البورصة المصرية ومستويات الدعم والمقاومة والإغلاق والتغير الفني والمؤشرات",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "رمز السهم بالإنجليزية مثل COMI, FWRY, ABUK, IRON",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "جلب نظرة عامة على الأسهم الأكثر ارتفاعاً وانخفاضاً في البورصة المصرية وحالة السوق",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_recommendations",
            "description": "جلب توصيات وإشارات الشراء المفتوحة والنشطة حالياً وفق محرك الإشارات الفنية للمنصة",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_market_engine",
            "description": "توجيه سؤال تحليل مالي/فني أو طلب مضاربة لمحرك الشات الذكي الكامل للمنصة (نفس المسار المتاح للمستخدمين)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "سؤال المستخدم بالكامل للتحليل المالي أو الفني",
                    }
                },
                "required": ["query"],
            },
        },
    },
]


def execute_admin_tool(name: str, args: Dict[str, Any]) -> str:
    """Dispatches tool calls to the matching python functions."""
    try:
        if name == "get_registrations_report":
            return json.dumps(get_registrations_data(args.get("date")), ensure_ascii=False)
        elif name == "get_activity_report":
            return json.dumps(get_activity_data(args.get("date")), ensure_ascii=False)
        elif name == "get_chat_history_summary":
            return json.dumps(get_chat_history_data(args.get("date"), args.get("chat_type", "all")), ensure_ascii=False)
        elif name == "get_platform_kpis":
            return json.dumps(get_platform_kpis_data(), ensure_ascii=False)
        elif name == "get_stock_analysis":
            return json.dumps(tool_get_stock_quote(args.get("symbol", "")), ensure_ascii=False)
        elif name == "get_market_overview":
            return json.dumps(tool_get_market_overview(), ensure_ascii=False)
        elif name == "get_open_recommendations":
            return json.dumps(tool_get_open_recommendations(), ensure_ascii=False)
        elif name == "query_market_engine":
            return json.dumps(tool_query_market_engine(args.get("query", "")), ensure_ascii=False)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


ADMIN_SYSTEM_PROMPT = """أنت "ARTORO Admin Assistant" — المساعد الذكي الخاص بمؤسس وإدارة منصة EGX Bots للبورصة المصرية على تليجرام.

مهامك:
١. تزويد المؤسس بتقارير تنفيذية ذكية، تحليلية، ولحظية عن:
   - المستخدمين المسجلين الجدد، بياناتهم (أسماء، إيميلات، أرقام الموبايل).
   - نشاط المنصة (DAU)، الأحداث، والصفحات الأكثر تفاعلاً وزيارة.
   - استفسارات الدعم الفني وتذاكر العملاء وشات الذكاء الاصطناعي لمعرفة اهتمامات ومشاكل المستخدمين.
   - تحليلات الأسهم وأداء البورصة المصرية وتوصيات المنصة (بإمكانك استخدام نفس محرك تحليل الموقع).

إرشادات الأسلوب:
- لغة عربية فصحى احترافية، تنفيذية ومباشرة (بدون إطالة أو حشو).
- استخدم دائماً الأدوات المتاحة (Tools) للحصول على البيانات الدقيقة؛ لا تخمن أرقاماً أبداً.
- نسق الرد بتنسيق تليجرام أنيق: خطوط عريضة <b>...</b>، وسوم <code>...</code> للأرقام والأكواد، وقوائم نقطية واضحة.
- إذا لم تكن هناك بيانات مسجلة في يوم معين أو لا توجد توصيات، وضح ذلك بأمانة واقترح خطوات عملية.
"""


def _call_llm_with_fallback(payload_base: Dict[str, Any], exp_key: str, ds_key: str) -> Dict[str, Any]:
    """Calls official deepseek-flash first as default; falls back to Experiential V4.1 only if DeepSeek fails."""
    providers = []
    if ds_key:
        providers.append((DEEPSEEK_API_URL, DEEPSEEK_MODEL, ds_key))
    if exp_key:
        providers.append((EXPERIENTIAL_API_URL, EXPERIENTIAL_MODEL, exp_key))

    last_err: Optional[Exception] = None
    for url, model_name, token in providers:
        payload = {**payload_base, "model": model_name}
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_err = exc
            print(f"[ADMIN_AI] Model {model_name} failed ({exc}), trying fallback if available...")
    raise RuntimeError(str(last_err or "No AI provider available"))


def ask_admin_ai(user_message: str, chat_id: Optional[int] = None) -> str:
    """Interacts with DeepSeek V4.1 Flash (with fallback to DeepSeek Flash) to answer admin queries."""
    ds_key = _get_deepseek_key()
    exp_key = _get_experiential_key()
    if not ds_key and not exp_key:
        return "❌ <b>عذراً، مفتاح DeepSeek API غير معرف في السيرفر.</b>"

    if chat_id:
        send_chat_action(chat_id, "typing")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": ADMIN_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    payload: Dict[str, Any] = {
        "messages": messages,
        "tools": ADMIN_AI_TOOLS,
        "tool_choice": "auto",
        "temperature": 0.2,
        "max_tokens": 1500,
    }

    try:
        resp_body = _call_llm_with_fallback(payload, exp_key, ds_key)
    except Exception as exc:
        print(f"[ADMIN_AI] Initial AI request failed: {exc}")
        return f"❌ تعذر الاتصال بالمساعد الذكي حالياً: {exc}"

    choice = (resp_body.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    tool_calls = msg.get("tool_calls") or []

    # If no tool calls, return direct response
    if not tool_calls:
        return msg.get("content") or "تمت معالجة الطلب بدون إرجاع تفاصيل."

    # Execute tool calls
    messages.append(msg)
    if chat_id:
        send_chat_action(chat_id, "typing")

    for tc in tool_calls:
        call_id = tc.get("id")
        func = tc.get("function", {})
        fname = func.get("name")
        try:
            fargs = json.loads(func.get("arguments") or "{}")
        except Exception:
            fargs = {}

        print(f"[ADMIN_AI] Calling tool {fname} with args: {fargs}")
        tool_result = execute_admin_tool(fname, fargs)

        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": fname,
            "content": tool_result,
        })

    # Call AI with tool outputs to get the final synthesis
    synthesis_payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1500,
    }

    try:
        final_body = _call_llm_with_fallback(synthesis_payload, exp_key, ds_key)
        final_choice = (final_body.get("choices") or [{}])[0]
        return final_choice.get("message", {}).get("content") or "✅ تم استلام البيانات وتحليلها."
    except Exception as exc:
        print(f"[ADMIN_AI] Synthesis request failed: {exc}")
        return f"❌ تعذر استكمال توليد التقرير: {exc}"
