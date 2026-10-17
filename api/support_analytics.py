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


def _get_cairo_bounds_for_date(date_str: Optional[str] = None):
    """Parses date string or defaults to today in Africa/Cairo timezone."""
    now_cairo = datetime.datetime.now(CAIRO_TZ)
    today_cairo_start = now_cairo.replace(hour=0, minute=0, second=0, microsecond=0)

    clean = (date_str or "").strip().lower()
    if not clean or clean in ("today", "اليوم"):
        target_start = today_cairo_start
    elif clean in ("yesterday", "امس", "أمس"):
        target_start = today_cairo_start - datetime.timedelta(days=1)
    else:
        try:
            parsed = datetime.datetime.strptime(clean, "%Y-%m-%d")
            target_start = parsed.replace(tzinfo=CAIRO_TZ)
        except Exception:
            target_start = today_cairo_start

    target_end = target_start + datetime.timedelta(days=1)
    start_iso = target_start.astimezone(datetime.timezone.utc).isoformat()
    end_iso = target_end.astimezone(datetime.timezone.utc).isoformat()
    day_str = target_start.strftime("%Y-%m-%d")
    return start_iso, end_iso, day_str


def get_registrations_data(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Returns structured data of registrations for a given date."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}

    start_iso, end_iso, day_str = _get_cairo_bounds_for_date(date_str)
    try:
        res = supabase.table("profiles").select("id, created_at, whatsapp_number, display_name").gte("created_at", start_iso).lt("created_at", end_iso).order("created_at", desc=True).limit(50).execute()
        rows = res.data or []

        # Check active subscriptions
        sub_users = set()
        try:
            sub_res = supabase.table("subscriptions").select("user_id").in_("status", ["active", "trialing"]).execute()
            sub_users = set(s["user_id"] for s in (sub_res.data or []) if s.get("user_id"))
        except Exception:
            pass

        # Map with auth users
        auth_users_map = {}
        try:
            auth_res = supabase.auth.admin.list_users(page=1, per_page=50)
            for u in (auth_res or []):
                meta = getattr(u, "user_metadata", {}) or {}
                auth_users_map[str(u.id)] = {
                    "email": getattr(u, "email", "") or "",
                    "name": meta.get("full_name") or meta.get("name") or meta.get("display_name") or "",
                }
        except Exception:
            pass

        users_list = []
        for r in rows:
            uid = str(r["id"])
            ainfo = auth_users_map.get(uid, {})
            name = ainfo.get("name") or r.get("display_name") or "User"
            email = ainfo.get("email") or ""
            phone = r.get("whatsapp_number") or ""
            plan = "pro" if uid in sub_users else "free"
            created_raw = r.get("created_at") or ""
            cairo_time = ""
            if created_raw:
                try:
                    dt = datetime.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                    cairo_time = dt.astimezone(CAIRO_TZ).strftime("%I:%M %p")
                except Exception:
                    pass
            users_list.append({
                "name": name,
                "email": email,
                "phone": phone,
                "plan": plan,
                "registered_time_cairo": cairo_time,
            })

        return {
            "date": day_str,
            "new_registrations_count": len(rows),
            "users": users_list,
        }
    except Exception as exc:
        return {"error": str(exc), "date": day_str}


def get_activity_data(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Returns structured user activity and page visits for a given date."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}

    start_iso, end_iso, day_str = _get_cairo_bounds_for_date(date_str)
    try:
        res = supabase.table("user_activity_events").select("user_id, path", count="exact").gte("created_at", start_iso).lt("created_at", end_iso).limit(1000).execute()
        rows = res.data or []
        dau = len(set(r["user_id"] for r in rows if r.get("user_id")))
        total_events = res.count or len(rows)

        paths_count = {}
        for r in rows:
            path = (r.get("path") or "").strip().split("?")[0]
            if path:
                paths_count[path] = paths_count.get(path, 0) + 1

        top_pages = [{"path": p, "views": count} for p, count in sorted(paths_count.items(), key=lambda x: x[1], reverse=True)[:8]]

        return {
            "date": day_str,
            "dau": dau,
            "total_interactions": total_events,
            "top_visited_pages": top_pages,
        }
    except Exception as exc:
        return {"error": str(exc), "date": day_str}


def get_chat_history_data(date_str: Optional[str] = None, chat_type: str = "all") -> Dict[str, Any]:
    """Returns summary of support chats and AI chats for a given date."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}

    start_iso, end_iso, day_str = _get_cairo_bounds_for_date(date_str)
    result = {"date": day_str}

    try:
        if chat_type in ("all", "support"):
            sup_res = supabase.table("support_messages").select("id, session_id, sender, content, user_name, created_at").gte("created_at", start_iso).lt("created_at", end_iso).order("created_at", desc=False).limit(300).execute()
            sup_rows = sup_res.data or []

            # Group by session
            sessions = {}
            for m in sup_rows:
                sid = m.get("session_id")
                if sid not in sessions:
                    sessions[sid] = {
                        "session_id": sid,
                        "customer_name": m.get("user_name") or "عميل",
                        "customer_messages": [],
                        "admin_replies": [],
                        "has_admin_replied": False,
                    }
                if m.get("sender") == "admin":
                    sessions[sid]["admin_replies"].append(m.get("content", ""))
                    sessions[sid]["has_admin_replied"] = True
                else:
                    sessions[sid]["customer_messages"].append(m.get("content", ""))

            result["support_tickets"] = {
                "total_messages": len(sup_rows),
                "unique_sessions_count": len(sessions),
                "unanswered_sessions_count": len([s for s in sessions.values() if not s["has_admin_replied"]]),
                "sessions_sample": list(sessions.values())[:10],
            }

        if chat_type in ("all", "ai"):
            ai_res = supabase.table("ai_chat_messages").select("user_id, role, content, created_at").gte("created_at", start_iso).lt("created_at", end_iso).limit(500).execute()
            ai_rows = ai_res.data or []

            user_queries = [m.get("content", "") for m in ai_rows if m.get("role") == "user"]
            unique_users = len(set(m["user_id"] for m in ai_rows if m.get("user_id")))

            result["ai_chat"] = {
                "total_messages": len(ai_rows),
                "unique_users_count": unique_users,
                "user_questions_count": len(user_queries),
                "sample_questions_asked": user_queries[-15:] if user_queries else [],
            }

        return result
    except Exception as exc:
        return {"error": str(exc), "date": day_str}


def get_platform_kpis_data() -> Dict[str, Any]:
    """Returns platform executive KPIs and subscription status."""
    _init_supabase()
    if not supabase:
        return {"error": "Database unavailable"}

    today_iso, yesterday_iso, now_str, today_start, now_cairo = _get_cairo_day_bounds()
    try:
        total_p = supabase.table("profiles").select("id", count="exact").limit(1).execute()
        total_users = total_p.count or 0

        pro_sub = supabase.table("subscriptions").select("id", count="exact").in_("status", ["active", "trialing"]).execute()
        pro_count = pro_sub.count or 0

        # Today's signups
        today_p = supabase.table("profiles").select("id", count="exact").gte("created_at", today_iso).execute()

        # Today's DAU
        act_today = supabase.table("user_activity_events").select("user_id").gte("created_at", today_iso).limit(1000).execute()
        dau_today = len(set(e["user_id"] for e in (act_today.data or []) if e.get("user_id")))

        return {
            "current_cairo_time": now_str,
            "total_registered_users": total_users,
            "pro_vip_subscribers": pro_count,
            "free_users": max(0, total_users - pro_count),
            "new_registrations_today": today_p.count or 0,
            "dau_today": dau_today,
        }
    except Exception as exc:
        return {"error": str(exc)}

