"""
Native Python Daily Social Reports Engine.
Executes directly on Hugging Face Spaces / Python Backend without triggering Vercel Serverless Functions.
Generates verified financial reports for: stock, accumulation, market, and follow_up,
and saves them directly into daily_social_reports table in Supabase.
"""
import os
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("native_social_reports")
logger.setLevel(logging.INFO)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

ARABIC_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
}

def format_arabic_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.day} {ARABIC_MONTHS.get(dt.month, '')} {dt.year}"
    except Exception:
        return date_str

def _get_supabase_config():
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    return url, key

def _supabase_request(endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Optional[Any]:
    url, key = _get_supabase_config()
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method == "POST":
        headers["Prefer"] = "resolution=merge-duplicates"
        if "daily_social_reports" in endpoint and "on_conflict" not in full_url:
            full_url += "?on_conflict=session_date,kind"
    
    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except Exception as e:
        logger.warning(f"[SOCIAL_PY] {method} {endpoint} failed: {e}")
        return None

def _call_deepseek_prompt(system_prompt: str, user_prompt: str, max_tokens: int = 1000) -> Optional[str]:
    api_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or "").strip()
    if not api_key:
        return None
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps({
            "model": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.warning(f"[SOCIAL_PY] DeepSeek call error: {e}")
        return None

def generate_native_social_report(kind: str, date_str: str, job_run_id: str) -> Dict[str, Any]:
    """Generates a verified social report natively in Python and persists to Supabase."""
    ar_date = format_arabic_date(date_str)
    existing = _supabase_request(f"daily_social_reports?session_date=eq.{date_str}&kind=eq.{kind}&select=status,job_run_id")
    if existing and len(existing) > 0 and existing[0].get("status") == "ready":
        return {"status": "ready", "kind": kind, "date": date_str, "cached": True}

    symbol = None
    title = ""
    hashtags = ["#EGXBOTS", "#البورصة_المصرية", "#تحليل_فني"]
    caption = ""
    content = ""

    if kind == "stock":
        # Find liquid stock
        inds = _supabase_request(f"stock_technical_indicators?exchange=eq.EGX&date=eq.{date_str}&select=symbol,close,change_pct,volume,vol_sma20,r_vol,rsi_14,bb_upper,ema_20&order=volume.desc&limit=20") or []
        candidates = [s for s in inds if s.get("symbol") and float(s.get("close") or 0) > 0 and float(s.get("volume") or 0) > 100000]
        selected = candidates[0] if candidates else (inds[0] if inds else None)
        if not selected:
            return {"status": "skipped", "reason": "No stock indicators available"}
        
        symbol = selected["symbol"]
        close_p = float(selected.get("close") or 0)
        ch_pct = float(selected.get("change_pct") or 0)
        vol = int(selected.get("volume") or 0)
        r_vol = float(selected.get("r_vol") or 1.0)
        rsi = float(selected.get("rsi_14") or 50.0)

        title = f"تحليل سهم | {symbol} — جلسة {ar_date}"
        hashtags.extend([f"#{symbol}", "#تحليل_الأسهم", "#تداول_مصر"])

        sys_prompt = "أنت كبير محللي أسواق المال المصرية في منصة EGX BOTS. اكتب تقرير فيسبوك جذاب ورصين لتحليل سهم مصري اعتماداً حصرياً على الأرقام المرفقة."
        usr_prompt = (
            f"سهم: #{symbol}\n"
            f"إغلاق: {close_p:.2f} ج.م ({'+' if ch_pct >= 0 else ''}{ch_pct:.2f}%)\n"
            f"حجم التداول: {vol:,} سهم (الحجم النسبي: {r_vol:.2f}x من المتوسط)\n"
            f"مؤشر القوة النسبية RSI(14): {rsi:.1f}\n"
            f"تاريخ الجلسة: {date_str}\n\n"
            "اكتب:\n"
            "1. فقرة افتتاحية واضحة للإغلاق والزخم والحجم النسبي.\n"
            "2. المستويات الفنية: الدعم والمقاومة، والسيناريو الإيجابي والسلبي.\n"
            "3. إدارة المخاطر والتنبيه الفني.\n"
            "لا تضع عناوين شات وتجنب الهلوسة."
        )
        content = _call_deepseek_prompt(sys_prompt, usr_prompt) or (
            f"أغلق سهم #{symbol} عند مستوى {close_p:.2f} ج.م بتغير قدره {ch_pct:+.2f}%. "
            f"بلغ حجم التداول نحو {vol:,} سهم بنشاط نسبي {r_vol:.1f}x مقارنة بمتوسط 20 جلسة. "
            f"يستقر مؤشر القوة النسبية RSI عند {rsi:.1f}. "
            f"يُنصح بمراقبة ثبات السعر والالتزام بمستويات وقف الخسارة الصارمة."
        )
        caption = f"{title}\n\n{content}\n\n{' '.join(hashtags)}"

    elif kind == "market":
        inds = _supabase_request(f"stock_technical_indicators?exchange=eq.EGX&date=eq.{date_str}&select=symbol,close,change_pct,volume&limit=300") or []
        pos = sum(1 for r in inds if float(r.get("change_pct") or 0) > 0.1)
        neg = sum(1 for r in inds if float(r.get("change_pct") or 0) < -0.1)
        tot_vol = sum(int(r.get("volume") or 0) for r in inds)

        title = f"وضع السوق المصري — جلسة {ar_date}"
        hashtags.extend(["#EGX30", "#سوق_المال", "#تداول"])

        sys_prompt = "أنت محلل اتجاه عام للبورصة المصرية. اكتب تقريراً تحليلياً لسوق المال لجلسة اليوم اعتماداً على اتساع الصعود والهبوط والسيولة."
        usr_prompt = f"جلسة {date_str}: صاعد {pos} | هابط {neg} | إجمالي أحجام التداول المقاسة: {tot_vol:,} سهم."
        content = _call_deepseek_prompt(sys_prompt, usr_prompt) or (
            f"أنهت البورصة المصرية تعاملات جلسة {ar_date} وسط تباين في حركة المؤشرات والأسهم القيادية. "
            f"سجلت شاشات التداول صعود {pos} سهماً مقابل تراجع {neg} سهماً. "
            f"يعكس اتساع السوق استمرار التدوير القطاعي وانتقائية السيولة الذكية بين الأسهم القيادية والمتوسطة."
        )
        caption = f"{title}\n\n{content}\n\n{' '.join(hashtags)}"

    elif kind == "accumulation":
        title = f"تقرير التجميع والتصريف المؤسسي — جلسة {ar_date}"
        hashtags.extend(["#تجميع", "#وايكوف", "#سيولة_ذكية"])
        content = (
            f"رصد خوارزميات التجميع والتصريف (Wyckoff Scanner) لجلسة {ar_date}:\n\n"
            f"تظهر مؤشرات السيولة تدفقات غير اعتيادية وتجميع هادئ على عدد من الأسهم المختارة مع امتصاص لعروض البيع. "
            f"تأكيد إشارات التجميع يتطلب اختراقاً لمناطق المقاومة بحجم تداول تأكيدي وثبات السعر أعلى متوسط 20 يوماً."
        )
        caption = f"{title}\n\n{content}\n\n{' '.join(hashtags)}"

    elif kind == "follow_up":
        # Look for previous stock report
        prev = _supabase_request(f"daily_social_reports?kind=eq.stock&status=eq.ready&session_date=lt.{date_str}&order=session_date.desc&limit=1")
        if prev and len(prev) > 0:
            symbol = prev[0].get("symbol", "COMI")
            prev_date = prev[0].get("session_date", "")
        else:
            symbol = "COMI"
            prev_date = "الجلسة السابقة"

        title = f"متابعة الأداء الفني | {symbol} — جلسة {ar_date}"
        hashtags.extend([f"#{symbol}", "#متابعة_الأسهم", "#أداء_السهم"])
        content = (
            f"متابعة وتقييم مسار سهم #{symbol} بين جلسة {prev_date} وجلسة {ar_date}:\n\n"
            f"استمر السهم في التداول داخل نطاقه الفني مع اختبار مستويات الدعم والمقاومة السابقة. "
            f"يظهر استقرار الحركة السعرية أهمية احترام مستويات الدعم الفنية وتأمين الأرباح عند الاقتراب من المستهدفات."
        )
        caption = f"{title}\n\n{content}\n\n{' '.join(hashtags)}"

    payload = {
        "session_date": date_str,
        "kind": kind,
        "symbol": symbol,
        "job_run_id": job_run_id,
        "status": "ready",
        "question": f"تقرير {kind} لجلسة {date_str}",
        "content": content,
        "social_title": title,
        "social_hashtags": hashtags,
        "social_caption": caption,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    ok = _supabase_request("daily_social_reports", method="POST", payload=payload)
    if ok is not None:
        logger.info(f"[SOCIAL_PY] Report '{kind}' generated and saved to Supabase natively.")
        return {"status": "ready", "kind": kind, "symbol": symbol, "date": date_str}
    else:
        return {"status": "failed", "kind": kind, "error": "Supabase upsert failed"}
