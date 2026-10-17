import datetime
import zoneinfo
from typing import Dict, Any, List, Optional
from api.stock_ai import _init_supabase, supabase

CAIRO_TZ = zoneinfo.ZoneInfo("Africa/Cairo")

def _get_cairo_day_bounds():
    """Returns (today_iso, yesterday_iso, now_cairo_str) based on Africa/Cairo timezone."""
    now_cairo = datetime.datetime.now(CAIRO_TZ)
    today_cairo_start = now_cairo.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_cairo_start = today_cairo_start - datetime.timedelta(days=1)
    
    today_iso = today_cairo_start.astimezone(datetime.timezone.utc).isoformat()
    yesterday_iso = yesterday_cairo_start.astimezone(datetime.timezone.utc).isoformat()
    now_str = now_cairo.strftime("%Y-%m-%d %I:%M %p")
    return today_iso, yesterday_iso, now_str, today_cairo_start, now_cairo

def get_registrations_summary() -> str:
    """Generates detailed registration report for today and yesterday."""
    _init_supabase()
    if not supabase:
        return "❌ يتعذر الاتصال بقاعدة البيانات حالياً."
        
    today_iso, yesterday_iso, now_str, today_start, now_cairo = _get_cairo_day_bounds()
    
    try:
        # 1. Registered today & yesterday from profiles
        p_today = supabase.table("profiles").select("id", count="exact").gte("created_at", today_iso).execute()
        p_yesterday = supabase.table("profiles").select("id", count="exact").gte("created_at", yesterday_iso).lt("created_at", today_iso).execute()
        p_total = supabase.table("profiles").select("id", count="exact").limit(1).execute()
        
        count_today = p_today.count or 0
        count_yesterday = p_yesterday.count or 0
        count_total = p_total.count or 0
        
        # 2. Pro subscribers count
        sub_res = supabase.table("subscriptions").select("id", count="exact").in_("status", ["active", "trialing"]).execute()
        count_pro = sub_res.count or 0
        count_free = max(0, count_total - count_pro)
        
        # 3. Fetch latest 5 registered users from auth & profiles
        recent_profiles_res = supabase.table("profiles").select("id, created_at, whatsapp_number, display_name").order("created_at", desc=True).limit(5).execute()
        recent_profiles = recent_profiles_res.data or []
        
        # Map with auth users to get full names & emails
        auth_users_map = {}
        try:
            auth_res = supabase.auth.admin.list_users(page=1, per_page=15)
            for u in (auth_res or []):
                meta = getattr(u, "user_metadata", {}) or {}
                auth_users_map[str(u.id)] = {
                    "email": getattr(u, "email", "") or "",
                    "name": meta.get("full_name") or meta.get("name") or meta.get("display_name") or "",
                    "created_at": getattr(u, "created_at", "")
                }
        except Exception as e:
            print(f"[ANALYTICS] Auth admin list error: {e}")

        # Format trend indicator
        if count_today > count_yesterday:
            trend = f"🟢 <b>+{count_today - count_yesterday}</b> مقارنة بأمس"
        elif count_today < count_yesterday:
            trend = f"🔻 <b>-{count_yesterday - count_today}</b> مقارنة بأمس"
        else:
            trend = "⚪ <b>نفس معدل أمس</b>"

        lines = [
            "👥 <b>تقرير المستخدمين والمسجلين الجدد</b>",
            f"📅 <i>بتوقيت القاهرة: {now_str}</i>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🔹 <b>المسجلين اليوم:</b> <code>{count_today}</code> مستخدم ({trend})",
            f"🔹 <b>المسجلين أمس:</b> <code>{count_yesterday}</code> مستخدم",
            f"🔹 <b>إجمالي مستخدمي المنصة:</b> <code>{count_total}</code> مستخدم",
            f"👑 <b>مشتركي VIP (PRO):</b> <code>{count_pro}</code> | <b>المجاني:</b> <code>{count_free}</code>",
            "━━━━━━━━━━━━━━━━━━━━",
            "📋 <b>آخر المسجلين بالمنصة:</b>"
        ]
        
        if recent_profiles:
            for idx, p in enumerate(recent_profiles, start=1):
                uid = str(p["id"])
                auth_info = auth_users_map.get(uid, {})
                name = auth_info.get("name") or p.get("display_name") or "مستخدم جديد"
                email = auth_info.get("email") or ""
                phone = p.get("whatsapp_number") or ""
                created_raw = p.get("created_at") or ""
                
                cairo_time_str = ""
                if created_raw:
                    try:
                        dt = datetime.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        cairo_dt = dt.astimezone(CAIRO_TZ)
                        cairo_time_str = cairo_dt.strftime("%d/%m %I:%M %p")
                    except Exception:
                        pass
                
                contact = f" | 📱 <code>{phone}</code>" if phone else ""
                lines.append(f"{idx}. <b>{name}</b> ({email}){contact}")
                if cairo_time_str:
                    lines.append(f"   ⏱ <i>{cairo_time_str}</i>")
        else:
            lines.append("<i>لا يوجد مسجلين جدد مؤخراً</i>")
            
        return "\n".join(lines)
    except Exception as e:
        print(f"[ANALYTICS] get_registrations_summary error: {e}")
        return f"❌ خطأ أثناء جلب بيانات المسجلين: {e}"

def get_activity_summary() -> str:
    """Generates user engagement and activity report for today and yesterday."""
    _init_supabase()
    if not supabase:
        return "❌ يتعذر الاتصال بقاعدة البيانات حالياً."
        
    today_iso, yesterday_iso, now_str, today_start, now_cairo = _get_cairo_day_bounds()
    
    try:
        # 1. User activity events today & yesterday
        act_today = supabase.table("user_activity_events").select("user_id, path", count="exact").gte("created_at", today_iso).limit(1000).execute()
        act_yesterday = supabase.table("user_activity_events").select("user_id", count="exact").gte("created_at", yesterday_iso).lt("created_at", today_iso).limit(1000).execute()
        
        events_today_count = act_today.count or len(act_today.data or [])
        events_yesterday_count = act_yesterday.count or len(act_yesterday.data or [])
        
        users_today = set(e["user_id"] for e in (act_today.data or []) if e.get("user_id"))
        users_yesterday = set(e["user_id"] for e in (act_yesterday.data or []) if e.get("user_id"))
        
        dau_today = len(users_today)
        dau_yesterday = len(users_yesterday)
        
        # 2. Top pages visited today
        paths_count = {}
        for e in (act_today.data or []):
            path = (e.get("path") or "").strip()
            if path:
                # normalize path
                clean_path = path.split("?")[0]
                paths_count[clean_path] = paths_count.get(clean_path, 0) + 1
                
        sorted_pages = sorted(paths_count.items(), key=lambda x: x[1], reverse=True)[:5]
        
        page_labels = {
            "/": "🏠 الرئيسية",
            "/chat": "🤖 شات الذكاء الاصطناعي",
            "/pricing": "💎 الأسعار والترقية",
            "/profile": "👤 الحساب والمحفظة",
            "/radar": "📡 رادار السوق",
            "/reports": "📑 تقارير الأسهم",
            "/admin": "⚙️ لوحة الإدارة",
            "/login": "🔐 تسجيل الدخول",
            "/signup": "📝 إنشاء حساب"
        }

        lines = [
            "⚡ <b>تقرير النشاط وتفاعل المستخدمين (Activity)</b>",
            f"📅 <i>بتوقيت القاهرة: {now_str}</i>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"👤 <b>المستخدمين النشطين اليوم (DAU):</b> <code>{dau_today}</code>",
            f"👤 <b>المستخدمين النشطين أمس:</b> <code>{dau_yesterday}</code>",
            f"📊 <b>إجمالي التفاعلات اليوم:</b> <code>{events_today_count}</code> حدث",
            f"📊 <b>إجمالي التفاعلات أمس:</b> <code>{events_yesterday_count}</code> حدث",
            "━━━━━━━━━━━━━━━━━━━━",
            "🔥 <b>أكثر الصفحات زيارة وتفاعلاً اليوم:</b>"
        ]
        
        if sorted_pages:
            for path, cnt in sorted_pages:
                label = page_labels.get(path, path)
                lines.append(f"• <b>{label}</b> (<code>{path}</code>): {cnt} زيارة")
        else:
            lines.append("<i>جاري رصد تفاعلات جديدة...</i>")
            
        return "\n".join(lines)
    except Exception as e:
        print(f"[ANALYTICS] get_activity_summary error: {e}")
        return f"❌ خطأ أثناء جلب بيانات النشاط: {e}"

def get_chat_summary() -> str:
    """Generates statistics for both Support Chat (human) and AI Chatbot (ARTORO)."""
    _init_supabase()
    if not supabase:
        return "❌ يتعذر الاتصال بقاعدة البيانات حالياً."
        
    today_iso, yesterday_iso, now_str, today_start, now_cairo = _get_cairo_day_bounds()
    
    try:
        # 1. Support Chat messages (human support)
        sup_today = supabase.table("support_messages").select("session_id, user_name, sender", count="exact").gte("created_at", today_iso).limit(500).execute()
        sup_yesterday = supabase.table("support_messages").select("session_id, sender", count="exact").gte("created_at", yesterday_iso).lt("created_at", today_iso).limit(500).execute()
        
        sup_today_data = sup_today.data or []
        sup_yesterday_data = sup_yesterday.data or []
        
        sup_msgs_today = len(sup_today_data)
        sup_msgs_yesterday = len(sup_yesterday_data)
        
        sup_user_msgs_today = len([m for m in sup_today_data if m.get("sender") == "user"])
        sup_admin_replies_today = len([m for m in sup_today_data if m.get("sender") == "admin"])
        
        sup_customers_today = len(set(m["session_id"] for m in sup_today_data if m.get("sender") == "user"))
        sup_customers_yesterday = len(set(m["session_id"] for m in sup_yesterday_data if m.get("sender") == "user"))
        
        # 2. AI Chatbot messages (ARTORO)
        ai_today = supabase.table("ai_chat_messages").select("user_id, role", count="exact").gte("created_at", today_iso).limit(1000).execute()
        ai_yesterday = supabase.table("ai_chat_messages").select("user_id, role", count="exact").gte("created_at", yesterday_iso).lt("created_at", today_iso).limit(1000).execute()
        
        ai_today_data = ai_today.data or []
        ai_yesterday_data = ai_yesterday.data or []
        
        ai_msgs_today = len(ai_today_data)
        ai_msgs_yesterday = len(ai_yesterday_data)
        
        ai_users_today = len(set(m["user_id"] for m in ai_today_data if m.get("user_id")))
        ai_users_yesterday = len(set(m["user_id"] for m in ai_yesterday_data if m.get("user_id")))
        
        ai_user_queries_today = len([m for m in ai_today_data if m.get("role") == "user"])
        ai_bot_replies_today = len([m for m in ai_today_data if m.get("role") == "assistant"])

        lines = [
            "💬 <b>تقرير مستخدمي الشات والمحادثات</b>",
            f"📅 <i>بتوقيت القاهرة: {now_str}</i>",
            "━━━━━━━━━━━━━━━━━━━━",
            "🎧 <b>١. دعم العملاء المباشر (VIP Support):</b>",
            f"• <b>عملاء تواصلوا اليوم:</b> <code>{sup_customers_today}</code> عميل (أمس: <code>{sup_customers_yesterday}</code>)",
            f"• <b>رسائل العملاء اليوم:</b> <code>{sup_user_msgs_today}</code> رسالة",
            f"• <b>ردود الإدارة اليوم:</b> <code>{sup_admin_replies_today}</code> رد",
            f"• <b>إجمالي رسائل الدعم اليوم:</b> <code>{sup_msgs_today}</code> (أمس: <code>{sup_msgs_yesterday}</code>)",
            "━━━━━━━━━━━━━━━━━━━━",
            "🤖 <b>٢. شات الذكاء الاصطناعي (ARTORO):</b>",
            f"• <b>مستخدمين فريدين اليوم:</b> <code>{ai_users_today}</code> مستخدم (أمس: <code>{ai_users_yesterday}</code>)",
            f"• <b>أسئلة واستفسارات اليوم:</b> <code>{ai_user_queries_today}</code> سؤال",
            f"• <b>إجابات وتحليلات البوت:</b> <code>{ai_bot_replies_today}</code> تحليل",
            f"• <b>إجمالي رسائل الذكاء اليوم:</b> <code>{ai_msgs_today}</code> (أمس: <code>{ai_msgs_yesterday}</code>)",
        ]
        
        return "\n".join(lines)
    except Exception as e:
        print(f"[ANALYTICS] get_chat_summary error: {e}")
        return f"❌ خطأ أثناء جلب بيانات الشات: {e}"

def get_comprehensive_report() -> str:
    """Generates unified executive report covering Registrations, Activity, and Chat."""
    _init_supabase()
    if not supabase:
        return "❌ يتعذر الاتصال بقاعدة البيانات حالياً."
        
    today_iso, yesterday_iso, now_str, today_start, now_cairo = _get_cairo_day_bounds()
    
    try:
        # Profiles
        p_today = supabase.table("profiles").select("id", count="exact").gte("created_at", today_iso).execute()
        p_yesterday = supabase.table("profiles").select("id", count="exact").gte("created_at", yesterday_iso).lt("created_at", today_iso).execute()
        p_total = supabase.table("profiles").select("id", count="exact").limit(1).execute()
        
        # Pro subscriptions
        sub_res = supabase.table("subscriptions").select("id", count="exact").in_("status", ["active", "trialing"]).execute()
        
        # Activity
        act_today = supabase.table("user_activity_events").select("user_id", count="exact").gte("created_at", today_iso).limit(1000).execute()
        act_yesterday = supabase.table("user_activity_events").select("user_id", count="exact").gte("created_at", yesterday_iso).lt("created_at", today_iso).limit(1000).execute()
        dau_today = len(set(e["user_id"] for e in (act_today.data or []) if e.get("user_id")))
        dau_yesterday = len(set(e["user_id"] for e in (act_yesterday.data or []) if e.get("user_id")))
        
        # Support Chat
        sup_today = supabase.table("support_messages").select("session_id, sender", count="exact").gte("created_at", today_iso).limit(500).execute()
        sup_customers = len(set(m["session_id"] for m in (sup_today.data or []) if m.get("sender") == "user"))
        
        # AI Chat
        ai_today = supabase.table("ai_chat_messages").select("user_id, role", count="exact").gte("created_at", today_iso).limit(1000).execute()
        ai_users = len(set(m["user_id"] for m in (ai_today.data or []) if m.get("user_id")))
        ai_queries = len([m for m in (ai_today.data or []) if m.get("role") == "user"])

        lines = [
            "📊 <b>التقرير التنفيذي الشامل للمنصة</b>",
            f"📅 <i>بتوقيت القاهرة: {now_str}</i>",
            "━━━━━━━━━━━━━━━━━━━━",
            "👥 <b>المسجلين الجدد:</b>",
            f"• اليوم: <b>{p_today.count or 0}</b> | أمس: <b>{p_yesterday.count or 0}</b>",
            f"• إجمالي قاعدة المستخدمين: <b>{p_total.count or 0}</b> مستخدم",
            f"• باقات VIP النشطة: <b>{sub_res.count or 0}</b> مشترك",
            "━━━━━━━━━━━━━━━━━━━━",
            "⚡ <b>النشاط والتفاعل (Engagement):</b>",
            f"• مستخدمين نشطين اليوم (DAU): <b>{dau_today}</b>",
            f"• مستخدمين نشطين أمس: <b>{dau_yesterday}</b>",
            f"• إجمالي الأحداث اليوم: <b>{act_today.count or len(act_today.data or [])}</b> حدث",
            "━━━━━━━━━━━━━━━━━━━━",
            "💬 <b>استخدام المحادثات والشات:</b>",
            f"• عملاء الدعم المباشر اليوم: <b>{sup_customers}</b> عميل",
            f"• مستخدمين شات الذكاء اليوم: <b>{ai_users}</b> مستخدم",
            f"• استفسارات الذكاء الاصطناعي اليوم: <b>{ai_queries}</b> سؤال",
            "━━━━━━━━━━━━━━━━━━━━",
            "💡 <i>استخدم الأزرار أدناه لعرض تفاصيل كل قسم.</i>"
        ]
        return "\n".join(lines)
    except Exception as e:
        print(f"[ANALYTICS] get_comprehensive_report error: {e}")
        return f"❌ خطأ أثناء توليد التقرير الشامل: {e}"
