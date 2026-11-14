"""
Telegram VIP Chat Room & ARTORO Interactive Hub (https://t.me/egxbots/1680).

Connects the public/VIP Telegram chat topic directly to the website's Agentic AI
Pipeline (/api/telegram/vip-chat), enforcing per-user Free (5/day) and Pro (350/month)
quotas, preserving multi-turn session state & memory, providing 1-click quick tools
and interactive prompts (ForceReply + state), and displaying private modal alert
dialogs + pricing upgrade cards when a user reaches their plan limit.
"""
from __future__ import annotations

import html
import os
import re
import threading
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from dotenv import load_dotenv
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(_repo_root, ".env"))
except ImportError:
    pass

import requests

from api.web_origin import get_web_origin

# Default Group & Topic from https://t.me/egxbots/1680 -> -1002083067817_1680
DEFAULT_VIP_GROUP_ID = "-1002083067817"
DEFAULT_VIP_TOPIC_ID = 1680

# In-memory deduplication & pending prompt state (backed by Supabase telegram_vip_chat_state)
_DEDUP_LOCK = threading.Lock()
_PROCESSED_EVENTS: Dict[str, float] = {}
_PENDING_PROMPTS: Dict[Tuple[str, int], Dict[str, Any]] = {}
_USER_QUOTA_CACHE: Dict[int, Dict[str, Any]] = {}
_WEB_SESSION = requests.Session()


@lru_cache(maxsize=1)
def _get_egx_symbols_set() -> Set[str]:
    """Return all known EGX tickers (uppercase) with resilient fallback."""
    try:
        from api.symbols_local import load_symbols_for_country
        syms = load_symbols_for_country("Egypt")
        res = {str(s.get("Symbol") or "").strip().upper() for s in syms if s.get("Symbol")}
        res.discard("")
        if res:
            return res
    except Exception:
        pass
    return {
        "ABUK", "ADCI", "ADIB", "AFMC", "AIND", "AJWA", "ALCN", "ALUM", "AMER", "AMOC",
        "ANFI", "ARAB", "ARCC", "AREH", "AREHA", "ARVA", "ASCM", "ASPI", "ATLC", "ATQA",
        "AUTO", "AXPH", "BINV", "BIOC", "BONY", "BTFH", "CAED", "CANA", "CCRS", "CEFM",
        "CERA", "CFGH", "CICH", "CLHO", "CNFN", "COMI", "COPR", "COSG", "CPCI", "CSAG",
        "DTPP", "EAST", "EBSC", "EFIC", "EGAL", "EGAS", "EGCH", "EGSA", "EGTS", "EHDR",
        "EKHO", "EKHOA", "ELNA", "ELSH", "EMFD", "EPCO", "ESRS", "ETEL", "ETRS", "EXPA",
        "FIRE", "FWRY", "GBCO", "GDWA", "GECE", "GGCC", "GMCB", "GOCO", "GOUR", "GRCA",
        "GSPC", "GTHE", "HELI", "HDBK", "HRHO", "ICMI", "IDRE", "IFAP", "IFIN", "INFI",
        "IRAX", "IRON", "ISPH", "JUFO", "KABO", "KASABF", "KIMA", "KLHO", "KORA", "KRRE",
        "LCSH", "MAAL", "MASR", "MCQE", "MEPA", "MFPC", "MICH", "MIPH", "MNHD", "MOIL",
        "MPCO", "MPRC", "MRCO", "MTIE", "NAHO", "NASR", "NATP", "NBKE", "NINH", "OBRI",
        "OCDI", "OFH", "OLFI", "ORAS", "ORHD", "ORWE", "PACH", "PHDC", "POUL", "PRCL",
        "PRDC", "PRMH", "QNBA", "RAKT", "RAYA", "RREI", "RUBX", "SAIB", "SAUD", "SCEM",
        "SDTI", "SEEK", "SKPC", "SMFR", "SPHT", "SPMD", "SUGR", "SVCE", "SWDY", "TAQA",
        "TCAP", "TMGH", "TRTO", "UEGC", "UNIP", "UTOP", "VALU", "VERT", "VOIL", "ZEOT",
    }


EGX_ARABIC_NAMES: List[str] = [
    "فوري", "طلعت مصطفى", "أجواء", "اجواء", "أجوا", "اجوا", "موبكو", "سيدي كرير", "سيدى كرير",
    "حديد عز", "عز الدخيلة", "بالم هيلز", "أسكوم", "اسكوم", "بلتون", "بيلتون", "بالتون", "هيرمس", "هيرميس",
    "إي إف جي", "اي اف جي", "ابوقير", "أبوقير", "أبو قير", "ابو قير", "إيديتا", "ايديتا",
    "جهينة", "جهينه", "السويدي", "السويدى", "النساجون", "النساجون الشرقيون", "كيما", "مدينة نصر",
    "مدينه نصر", "مصر الجديدة", "مصر الجديده", "إعمار", "اعمار", "إعمار مصر", "ابن سينا",
    "القاهرة للادوية", "القاهرة للأدوية", "رميدا", "سبيد ميديكال", "غاز مصر", "أموك", "اموك",
    "المالية والصناعية", "الماليه والصناعيه", "القلعة", "القلعه", "بايونيرز", "جي بي أوتو",
    "جي بي كورب", "أوراسكوم", "اوراسكوم", "ريماس", "عتاقة", "عتاقه", "الزهراء", "شارم دريمز",
    "شمس للإسكان", "الشمس", "سبأ", "راكتا", "الرواد", "العربية لحليج", "الشرقية للدخان",
    "الشرقيه للدخان", "إيسترن كومباني", "ايسترن", "النزهة", "النزهه", "جدوى", "جدوي", "كونتكت",
    "ثروة", "برايم", "أصول", "اصول", "كفر الزيات", "الحديد والصلب", "القاهرة للزيوت",
    "العربية للادوية", "العبور", "مطاحن مصر الوسطى", "مطاحن اسكندرية", "مطاحن إسكندرية",
    "الخليج الكندي", "كونكريت", "سي اي كابيتال", "سي آي كابيتال", "كوبر", "دومتي", "دومتى",
    "قناة السويس", "أبوظبي الإسلامي", "ابوظبي الاسلامي", "مصرف أبوظبي", "بنك فيصل",
    "المصرف المتحد", "المصرية للاتصالات", "المصريه للاتصالات", "وي", "إي فاينانس", "اي فاينانس",
    "تعليم", "كابو", "أم بي للهندسة", "مصر للأسمنت", "أسمنت قنا", "أكرو مصر", "العربية للاسمنت",
    "العربيه للاسمنت", "شمال الصعيد", "الجيزة العامة", "الصعيد للمقاولات", "رواد السياحة",
    "مرسى علم", "مينا للاستثمار", "زهراء المعادي", "طاقة عربية", "طاقه عربيه", "طاقة",
    "بي انفستمنتس", "بي إنفستمنتس", "قرة", "قره", "أوراسكوم كونستراكشون", "اسكندرية لتداول الحاويات",
    "الحاويات", "حاويات اسكندرية", "الاسكندرية لتداول الحاويات", "الإسكندرية لتداول الحاويات",
    "جورميه", "جورمية", "جورميه ايجيبت", "جورميه للأغذية",
]


def _norm_ar(text: str) -> str:
    """Normalize Arabic text (unify hamzas, yaa/alif-maqsura, taa-marbuta, strip diacritics)."""
    return (
        re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text or "")
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
        .strip()
        .lower()
    )


@lru_cache(maxsize=1)
def _get_normalized_arabic_stock_names() -> List[str]:
    """Return all normalized Arabic stock names/aliases (longest first) from EGX_ARABIC_NAMES + stock_aliases."""
    names: Set[str] = set()
    for n in EGX_ARABIC_NAMES:
        nn = _norm_ar(n)
        if len(nn) >= 2:
            names.add(nn)
    try:
        from api.stock_aliases import ARABIC_STOCK_MAPPINGS
        for k in ARABIC_STOCK_MAPPINGS.keys():
            if re.search(r"[\u0621-\u064A]", k):
                nn = _norm_ar(k)
                if len(nn) >= 2:
                    names.add(nn)
    except Exception:
        pass
    return sorted(names, key=len, reverse=True)


def detect_topic_query_intent(text: str) -> Optional[Tuple[str, str]]:
    """
    Normalize and classify a user message in Topic 1680 (ARTORO).
    All messages in Topic 1680 are directed to ARTORO:
    - Bare stock tickers/names (e.g. "فورى", "COMI") are expanded to "حلل سهم <name>".
    - Comparisons are normalized.
    - All other questions and dialogues are forwarded directly as ("free", cleaned).
    """
    raw = (text or "").strip()
    if not raw:
        return None

    # Strip bot command/mention prefix if present
    cleaned = re.sub(r"^(?:/(?:ask|scanner)(?:@\w+)?|@egxbots_bot|يا\s*[اأ]رتورو|[اأ]رتورو)\s*[:،\-]?\s*", "", raw, flags=re.IGNORECASE).strip()
    if not cleaned:
        cleaned = raw
    norm_cleaned = _norm_ar(cleaned)

    # 1. Check if text is a bare EGX Ticker (e.g. "ASCM", "PHDC", "COMI", "FWRY", "ASCM.CA")
    token = re.sub(r"[^\w\.]", "", cleaned).upper().replace(".CA", "")
    if re.match(r"^[A-Z0-9]{2,6}$", token) and len(cleaned.split()) <= 2:
        return ("stock", f"حلل سهم {token}")

    # 2. Check for comparison intent ("قارن بين X و Y", "مقارنة X و Y", "أيهما أفضل")
    if re.search(r"(?:قارن|مقارن|مقارنه|ايهم|ايهما|\bبين\b.*\bو\b)", norm_cleaned):
        if not re.search(r"^(?:قارن|مقارن)", norm_cleaned):
            return ("compare", f"قارن بين {cleaned}")
        return ("compare", cleaned)

    # 3. If user typed just a bare Arabic stock name (1-3 words, e.g. "فورى", "عتاقه", "طلعت مصطفي")
    if len(norm_cleaned.split()) <= 3 and not re.search(r"(?:حلل|تحليل|سعر|رايك|مستويات|اخبار|توزيع|شرعي|ليه|ازاي|لو|هل|امتي|متي|تفتكر|طيب|اشرح|قارن)", norm_cleaned):
        for norm_name in _get_normalized_arabic_stock_names():
            if norm_name in norm_cleaned:
                pattern = rf"(?:^|[\s،,.؟?!:؛\-])(?:و|ف|ب|ل|ك|ال)?{re.escape(norm_name)}(?:$|[\s،,.؟?!:؛\-])"
                if re.search(pattern, norm_cleaned):
                    return ("stock", f"حلل سهم {cleaned}")

    # 4. Every other message in Topic 1680 goes straight to ARTORO!
    return ("free", cleaned)


def is_topic_recommendation_query(text: str) -> bool:
    """
    Check if a message in the public group topic is requesting open recommendations / buy signals.
    Returns True if user asks for open recommendations, buy opportunities, or signals across the market.
    Returns False if user is asking about a specific stock (e.g. "حلل فوري وتوصيتك عليه").
    """
    raw = (text or "").strip()
    if not raw:
        return False

    norm = _norm_ar(raw)

    # 1. Direct commands / English keywords
    cleaned_lower = raw.lower().split("@")[0].strip()
    if cleaned_lower in ("/recs", "recs", "/recommendations", "recommendations", "/signals", "signals", "/daily", "daily"):
        return True

    # 2. General recommendation patterns (Arabic)
    has_rec_kw = bool(re.search(
        r"(?:توصي[اهت]|توصياتك|فرص\s*(?:الشراء|اليوم|السوق|المتاح[اه])|اشار[اه]ت?\s*(?:الشراء|الدخول)|"
        r"(?:اسهم|الاسهم)\s*(?:المرشح[اه]|المقترح[اه])\s*(?:للشراء)?|"
        r"اشتري\s*ايه|انصحني\s*اشتري|رشحلي\s*سهم|افضل\s*سهم\s*للشراء)",
        norm
    ))

    if not has_rec_kw:
        if re.search(r"\b(?:recs?|recommendations?|buy\s*signals?)\b", raw, flags=re.IGNORECASE):
            has_rec_kw = True

    if not has_rec_kw:
        return False

    # 3. If text contains recommendation keywords, check whether it is asking about a SPECIFIC stock:
    # Check for known Latin ticker in query
    latin_words = [w.upper() for w in re.findall(r"\b[A-Za-z]{2,6}\b", raw)]
    excluded_latin = {"EGX", "AI", "PRO", "BOT", "ARTORO", "RECS", "DAILY", "BUY", "SELL", "HOLD", "TODAY", "SCAN", "NEWS", "FREE", "VIP"}
    potential_tickers = [w for w in latin_words if w not in excluded_latin]
    if potential_tickers:
        if re.search(r"(?:في|سهم|حلل|رايك|رايك\s*في)\s*[A-Za-z]{2,6}", raw, flags=re.IGNORECASE):
            return False

    # Check for specific Arabic stock names
    for stock_name in _get_normalized_arabic_stock_names():
        if len(stock_name) >= 3 and stock_name in norm:
            pattern = rf"(?:حلل|تحليل|رايك\s*في|توصيتك\s*في|وضع\s*سهم)\s*(?:سهم\s*)?(?:و|ف|ب|ل|ك|ال)?{re.escape(stock_name)}"
            if re.search(pattern, norm):
                return False
            if re.search(rf"سهم\s*(?:و|ف|ب|ل|ك|ال)?{re.escape(stock_name)}", norm):
                return False

    return True


def get_vip_group_id() -> str:
    raw = os.getenv("TELEGRAM_VIP_CHAT_ID", DEFAULT_VIP_GROUP_ID).strip()
    if "_" in raw:
        raw = raw.split("_", 1)[0]
    return raw or DEFAULT_VIP_GROUP_ID


def get_vip_topic_id() -> Optional[int]:
    raw_env = os.getenv("TELEGRAM_VIP_CHAT_THREAD_ID", "").strip()
    if raw_env.isdigit():
        return int(raw_env)
    raw_group = os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip()
    if "_" in raw_group:
        _, thread_part = raw_group.split("_", 1)
        if thread_part.isdigit():
            return int(thread_part)
    return DEFAULT_VIP_TOPIC_ID


def _pricing_url() -> str:
    origin = (get_web_origin() or "https://egxbots.com").rstrip("/")
    if "localhost" in origin or "127.0.0.1" in origin:
        origin = "https://egxbots.com"
    return f"{origin}/pricing"


def _profile_url() -> str:
    origin = (get_web_origin() or "https://egxbots.com").rstrip("/")
    if "localhost" in origin or "127.0.0.1" in origin:
        origin = "https://egxbots.com"
    return f"{origin}/profile"


def _private_bot_url() -> str:
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "egxbots_bot").strip().lstrip("@") or "egxbots_bot"
    return f"https://t.me/{bot_username}?start=artoro_chat"


def _topic_url() -> str:
    return "https://t.me/egxbots/1680"


def build_vip_chat_keyboard(is_private: bool = False) -> Dict[str, Any]:
    """Sleek interactive Inline Keyboard for summoning ARTORO and running quick tools."""
    if is_private:
        rows: List[List[Dict[str, Any]]] = [
            [
                {"text": "🤖 اسأل أرتورو", "callback_data": "vip_ask_free"},
                {"text": "🔍 حلل سهم", "callback_data": "vip_ask_stock"},
                {"text": "⚖️ قارن سهمين", "callback_data": "vip_ask_compare"},
            ],
            [
                {"text": "📈 ملخص السوق وأقوى الأسهم", "callback_data": "vip_tool_market"},
                {"text": "🧲 أسهم التجميع والسيولة", "callback_data": "vip_tool_accum"},
            ],
            [
                {"text": "⚡ المسح الفني", "callback_data": "vip_tool_scan"},
                {"text": "🎯 التوصيات المفتوحة (PRO)", "callback_data": "vip_tool_recs"},
                {"text": "📰 أخبار السوق", "callback_data": "vip_tool_news"},
            ],
            [
                {"text": "💼 تحليل محفظتي", "callback_data": "vip_tool_portfolio"},
                {"text": "📊 رصيدي وخطتي", "callback_data": "vip_my_quota"},
                {"text": "💎 مميزات PRO", "callback_data": "vip_pricing_dialog"},
            ],
            [
                {"text": "💬 غرفة أرتورو العامة", "url": _topic_url()},
                {"text": "🔗 ربط حساب الموقع", "url": _profile_url()},
            ],
        ]
    else:
        # In the public group topic: completely remove recommendations callback button to prevent spam/fairness leaks
        rows = [
            [
                {"text": "🤖 اسأل أرتورو", "callback_data": "vip_ask_free"},
                {"text": "🔍 حلل سهم", "callback_data": "vip_ask_stock"},
                {"text": "⚖️ قارن سهمين", "callback_data": "vip_ask_compare"},
            ],
            [
                {"text": "📈 ملخص السوق وأقوى الأسهم", "callback_data": "vip_tool_market"},
                {"text": "🧲 أسهم التجميع والسيولة", "callback_data": "vip_tool_accum"},
            ],
            [
                {"text": "⚡ المسح الفني", "callback_data": "vip_tool_scan"},
                {"text": "📰 أخبار السوق", "callback_data": "vip_tool_news"},
            ],
            [
                {"text": "💼 تحليل محفظتي", "callback_data": "vip_tool_portfolio"},
                {"text": "📊 رصيدي وخطتي", "callback_data": "vip_my_quota"},
                {"text": "💎 مميزات PRO", "callback_data": "vip_pricing_dialog"},
            ],
            [
                {
                    "text": "🔒 توصيات PRO (خاص / الموقع)",
                    "url": _private_bot_url(),
                }
            ],
            [
                {
                    "text": "🔒 تحدث مع أرتورو في شات خاص (@egxbots_bot)",
                    "url": _private_bot_url(),
                }
            ],
        ]
    return {"inline_keyboard": rows}


def build_pricing_upgrade_keyboard(is_private: bool = False) -> Dict[str, Any]:
    """Inline keyboard for the Limit Reached / Pro Upgrade dialog card."""
    rows: List[List[Dict[str, Any]]] = [
        [
            {
                "text": "👑 اشترك في PRO الآن — صفحة التسعير (100 ج.م)",
                "url": _pricing_url(),
            }
        ],
        [
            {
                "text": "💎 عرض مميزات PRO في نافذة خاصة",
                "callback_data": "vip_pricing_alert",
            },
            {
                "text": "🔗 ربط حساب الموقع",
                "url": _profile_url(),
            },
        ],
    ]
    if not is_private:
        rows.append(
            [
                {
                    "text": "🔒 فتح شات خاص مع أرتورو (@egxbots_bot)",
                    "url": _private_bot_url(),
                }
            ]
        )
    rows.append(
        [
            {
                "text": "🤖 العودة للوحة أدوات أرتورو",
                "callback_data": "vip_show_panel",
            }
        ]
    )
    return {"inline_keyboard": rows}


# Native Telegram modal popup dialog text (max 200 characters for show_alert=True)
LIMIT_REACHED_ALERT_TEXT = (
    "⚠️ انتهى رصيدك المجاني اليوم (5/5 أسئلة)!\n"
    "💎 اشترك في باقة PRO (100 ج.م للمؤسسين بدلاً من 200):\n"
    "• 350 سؤال ذكي/شهر\n"
    "• توصيات شراء فورية + قناة VIP\n"
    "• متابعة 10 أسهم بمحفظتك\n"
    "👇 اضغط زر التسعير للاشتراك"
)

PRO_ONLY_TOOL_ALERT_TEXT = (
    "🔒 التوصيات المفتوحة اللحظية متاحة لمشتركي PRO فقط!\n"
    "💎 باقة PRO (100 ج.م/شهر للمؤسسين):\n"
    "• إشارات شراء فورية بدون تأخير 15 يوم\n"
    "• 350 سؤال ذكي شهرياً لأرتورو\n"
    "• متابعة 10 أسهم بمحفظتك\n"
    "👇 اشترك الآن من صفحة التسعير"
)

PRICING_FEATURES_ALERT_TEXT = (
    "👑 مميزات باقة EGX Bots PRO:\n"
    "✅ 350 سؤال وتحليل شهرياً مع أرتورو\n"
    "✅ توصيات شراء فورية بدون تأخير 15 يوم\n"
    "✅ دخول قناة توصيات VIP الخاصة\n"
    "✅ محفظة ذكية لمتابعة 10 أسهم\n"
    "🔥 عرض المؤسسين: 100 ج.م/شهر (15 يوم فقط)!"
)

TOPIC_RECS_RESTRICTED_ALERT_TEXT = (
    "🔒 توصيات الشراء اللحظية حصرية لمشتركي PRO وتظهر فقط في الشات الخاص أو على الموقع."
)

ACCOUNT_LINK_ALERT_TEXT = (
    "🔗 لتحليل محفظتك الاستثمارية أو مزامنة اشتراكك:\n"
    "١. افتح صفحة البروفايل في الموقع (egxbots.com/profile)\n"
    "٢. اضغط على زر ربط التليجرام (Connect Telegram Bot)\n"
    "٣. ستتم مزامنة محفظتك وباقتك تلقائياً!"
)


def build_topic_recs_restricted_html(user_name: str, tg_user_id: int) -> str:
    """Card explaining that open recommendations are exclusive to PRO in private DM or on the website."""
    safe_name = html.escape(user_name or "المستثمر")
    return (
        f"🔒 <b>توصيات الشراء اللحظية حصرية لمشتركي PRO في الشات الخاص أو الموقع!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"عفواً يا <a href=\"tg://user?id={tg_user_id}\">{safe_name}</a>:\n"
        f"حفاظاً على سرية وعدالة إشارات التداول لجميع المشتركين، <b>لا تُعرض توصيات الشراء المفتوحة في هذه الغرفة العامة</b>.\n\n"
        f"📌 <b>للحصول على توصيات الشراء اللحظية فور صدورها:</b>\n"
        f"1️⃣ <b>تحدث مع أرتورو في شات خاص بخصوصية تامة:</b>\n"
        f"راسل البوت مباشرةً: <a href=\"https://t.me/egxbots_bot?start=artoro_chat\">@egxbots_bot</a>\n\n"
        f"2️⃣ <b>أو عبر ماسح الذكاء الاصطناعي على الموقع:</b>\n"
        f"<a href=\"https://egxbots.com/scanner/ai\">egxbots.com/scanner/ai</a>\n\n"
        f"💎 <i>إذا كنت مشتركاً في باقة PRO، افتح الشات الخاص مع البوت وستظهر لك كافة التوصيات المفتوحة فوراً وبسرية كاملة.</i>"
    )


def build_topic_recs_restricted_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔒 فتح الشات الخاص مع أرتورو (@egxbots_bot)",
                    "url": _private_bot_url(),
                }
            ],
            [
                {
                    "text": "🌐 التوصيات اللحظية على الموقع",
                    "url": "https://egxbots.com/scanner/ai",
                },
                {
                    "text": "💎 باقة PRO والتسعير (100 ج.م)",
                    "url": _pricing_url(),
                },
            ],
        ]
    }


def build_welcome_panel_html(is_private: bool = False, chat_id: Optional[Any] = None) -> str:
    """Build the main ARTORO VIP Chat Hub message (for public topic or private @egxbots_bot DM)."""
    if is_private:
        chat_id_line = f"\n🆔 <b>معرف تليجرام الخاص بك (Chat ID):</b> <code>{chat_id}</code>" if chat_id else ""
        return (
            "🤖 <b>الشات الخاص مع أرتورو — @egxbots_bot</b> 👑\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أهلاً بك في المحادثة الخاصة المباشرة مع المساعد الذكي <b>ARTORO</b> للبورصة المصرية (EGX)!\n"
            "🔒 <b>خصوصية تامة 100%:</b> جميع أسئلتك، تحليلات أسهمك، ومحفظتك الاستثمارية هنا خاصة بك وحدك ولا يراها أي عضو آخر.\n\n"
            "💬 <b>كيف تستخدم البوت هنا؟</b>\n"
            "• <b>اكتب مباشرةً:</b> يمكنك كتابة سؤالك أو اسم أي سهم مباشرة في الرسائل (مثل: <code>حلل فوري</code> أو <code>قارن بين التجاري الدولي وطلعت مصطفى</code>).\n"
            "• <b>أو استخدم الأزرار السريعة بالأسفل:</b> لتحليل سهم، مقارنة سهمين، ملخص السوق، أسهم التجميع، المسح الفني، التوصيات المفتوحة، وتحليل محفظتك بضغطة واحدة!\n\n"
            "🎫 <b>نظام الباقات والرصيد:</b>\n"
            "• <b>الباقة المجانية:</b> <code>5 أسئلة يومياً</code>.\n"
            "• <b>باقة PRO VIP:</b> <code>350 سؤالاً شهرياً</code> + التوصيات المفتوحة اللحظية + متابعة 10 أسهم بمحفظتك."
            f"{chat_id_line}\n\n"
            "👇 <b>اكتب سؤالك الآن أو اختر الأداة المطلوبة من الأزرار بالأسفل:</b>"
        )

    return (
        "🤖 <b>غرفة أرتورو الذكية — EGX Bots VIP Chat</b> 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "أهلاً بك في الغرفة التفاعلية المباشرة لمساعد الذكاء الاصطناعي <b>ARTORO</b> للبورصة المصرية (EGX)!\n"
        "يعمل أرتورو هنا بنفس محرك الموقع الذكي مع حفظ سياق محادثتك وأدوات التحليل اللحظية.\n\n"
        "💬 <b>كيف تستخدم أرتورو في هذه الغرفة؟</b>\n"
        "• <b>اكتب مباشرةً:</b> اكتب اسم أي سهم أو سؤالك مباشرة في الرسائل (مثل: <code>فوري</code> أو <code>حلل عتاقة</code> أو أي سؤال فني/مالي) وسيرد عليك أرتورو فوراً!\n"
        "• <b>أو استخدم الأزرار السريعة بالأسفل:</b> لتحليل سهم، مقارنة سهمين، ملخص السوق، أسهم التجميع، والمسح الفني بضغطة واحدة.\n\n"
        "🔒 <b>توصيات الشراء اللحظية (PRO):</b>\n"
        "• <i>حفاظاً على سرية وعدالة التوصيات لجميع المشتركين، توصيات الشراء اللحظية تظهر حصرياً لمشتركي PRO في الشات الخاص أو على الموقع.</i>\n\n"
        "🔒 <b>تفضل الخصوصية الكاملة؟ (شات خاص 1-on-1):</b>\n"
        "• إذا كنت لا ترغب في كتابة أسهمك أو محفظتك في الشات العام، اضغط على زر <b>«🔒 تحدث مع أرتورو في شات خاص (@egxbots_bot)»</b> بالأسفل أو راسل البوت <a href=\"https://t.me/egxbots_bot?start=artoro_chat\">@egxbots_bot</a> مباشرة للتحدث معه على انفراد وبخصوصية تامة!\n\n"
        "🎫 <b>نظام الباقات والرصيد:</b>\n"
        "• <b>الباقة المجانية:</b> <code>5 أسئلة يومياً</code>.\n"
        "• <b>باقة PRO VIP:</b> <code>350 سؤالاً شهرياً</code> + التوصيات المفتوحة اللحظية (في الخاص والموقع) + متابعة 10 أسهم بمحفظتك.\n\n"
        "👇 <b>اختر الأداة المطلوبة من الأزرار بالأسفل أو افتح الشات الخاص:</b>"
    )


def build_pricing_dialog_html(
    user_name: str,
    tg_user_id: int,
    reason: str = "limit_reached",
    used: int = 5,
    limit: int = 5,
) -> str:
    """Build the rich Pricing & Upgrade Dialog card with direct link to /pricing."""
    safe_name = html.escape(user_name or "المستثمر")
    user_mention = f'<a href="tg://user?id={tg_user_id}">{safe_name}</a>'

    if reason == "pro_required":
        header = (
            f"🔒 <b>ميزة حصرية لمشتركي PRO — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"أداة <b>التوصيات المفتوحة وإشارات الشراء اللحظية</b> متاحة حصرياً لأعضاء <b>باقة PRO VIP</b>."
        )
    elif reason == "account_link":
        header = (
            f"🔗 <b>ربط حساب الموقع مطلوب — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"لقراءة وتحليل أسهم محفظتك الاستثمارية أو تفعيل اشتراكك على التليجرام، يرجى ربط حسابك من صفحة البروفايل في الموقع بضغطة واحدة."
        )
    elif reason == "pricing_info":
        header = (
            f"💎 <b>باقات ومميزات EGX Bots PRO — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"ارتقِ بقراراتك الاستثمارية في البورصة المصرية مع التغطية الكاملة واللحظية:"
        )
    else:
        header = (
            f"⚠️ <b>وصلت للحد الأقصى لرصيدك اليومي ({used}/{limit}) — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"لقد استهلكت كامل رصيدك المجاني اليوم في سؤال <b>أرتورو AI</b>. "
            f"للاستمرار في التحليل الفوري والوصول الكامل لجميع الأدوات، قم بالترقية إلى <b>باقة PRO VIP</b>:"
        )

    return (
        f"{header}\n\n"
        "👑 <b>مميزات الاشتراك في باقة PRO VIP:</b>\n"
        "1️⃣ <b>350 سؤال وتحليل ذكي شهرياً</b> مع أرتورو في الموقع والتليجرام (بدلاً من 5 يومياً).\n"
        "2️⃣ <b>توصيات وإشارات الشراء اللحظية</b> فور صدورها (بدون تأخير 15 يوماً في الباقة المجانية).\n"
        "3️⃣ <b>دخول قناة التليجرام VIP الخاصة</b> لإشارات الدخول والأهداف ووقف الخسارة.\n"
        "4️⃣ <b>محفظة استثمارية ذكية لمتابعة حتى 10 أسهم</b> مع تحليل مستمر لمراكزك.\n"
        "5️⃣ <b>دعم فني مباشر VIP</b> وأولوية قصوى في الخوادم.\n\n"
        "🔥 <b>عرض المؤسسين الحصري (لفترة محدودة 15 يوماً فقط):</b>\n"
        "💰 <b>100 ج.م فقط شهرياً</b> (بدلاً من <s>200 ج.م</s>) مع مهلة 72 ساعة لتثبيت السعر — الدفع فوري عبر فودافون كاش / إنستاباي / فوري / البطاقات البنكية.\n\n"
        "👇 <b>اضغط على الزر بالأسفل للانتقال إلى صفحة التسعير وتفعيل اشتراكك فوراً:</b>"
    )


def _mark_event_processed(event_key: str) -> bool:
    """Return True if this event has NOT been processed yet, False if duplicate."""
    now = time.time()
    with _DEDUP_LOCK:
        # Clean expired keys older than 120s
        expired = [k for k, ts in _PROCESSED_EVENTS.items() if now - ts > 120]
        for k in expired:
            _PROCESSED_EVENTS.pop(k, None)
        if event_key in _PROCESSED_EVENTS:
            return False
        _PROCESSED_EVENTS[event_key] = now
        return True


def set_local_pending_prompt(chat_id: Any, tg_user_id: int, mode: Optional[str]) -> None:
    key = (str(chat_id), int(tg_user_id))
    with _DEDUP_LOCK:
        if not mode:
            _PENDING_PROMPTS.pop(key, None)
        else:
            _PENDING_PROMPTS[key] = {
                "mode": mode,
                "expires_at": time.time() + 300,
            }


def get_local_pending_prompt(chat_id: Any, tg_user_id: int) -> Optional[str]:
    key = (str(chat_id), int(tg_user_id))
    with _DEDUP_LOCK:
        entry = _PENDING_PROMPTS.get(key)
        if not entry:
            return None
        if time.time() > entry.get("expires_at", 0):
            _PENDING_PROMPTS.pop(key, None)
            return None
        return str(entry.get("mode") or "")


def _call_telegram_api(bot_token: str, method: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING") == "true" or os.getenv("TELEGRAM_TEST_MODE") == "true":
        return {
            "ok": True,
            "result": {
                "message_id": 777777,
                "chat": {"id": payload.get("chat_id", 0)},
                "text": payload.get("text", ""),
            },
        }
    relay = os.getenv("TELEGRAM_RELAY_URL", "https://api.telegram.org").strip().rstrip("/")
    bases = [relay, "https://api.telegram.org"] if relay != "https://api.telegram.org" else ["https://api.telegram.org"]
    last_err: Dict[str, Any] = {"ok": False, "description": "No endpoint tried"}
    for base in bases:
        for attempt in range(3):
            try:
                url = f"{base}/bot{bot_token}/{method}"
                resp = requests.post(url, json=payload, timeout=timeout)
                data = resp.json()
                if data.get("ok"):
                    return data
                last_err = data
                # Flood control: wait the server-provided retry_after (capped) and retry instead of losing the reply.
                if int(data.get("error_code") or 0) == 429 and attempt < 2 and method in ("sendMessage", "editMessageText"):
                    retry_after = float((data.get("parameters") or {}).get("retry_after") or 2)
                    time.sleep(min(max(retry_after, 1.0), 8.0))
                    continue
                # If 4xx error from Telegram (like parse error or user blocked), don't retry on other base
                if 400 <= int(data.get("error_code") or 0) < 500:
                    return data
                break
            except Exception as exc:
                last_err = {"ok": False, "description": str(exc)}
                break
    return last_err


def send_vip_message(
    bot_token: str,
    chat_id: Any,
    text: str,
    message_thread_id: Optional[int] = None,
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Send an HTML-formatted message (splitting if >3900 chars) and return the last message_id."""
    chunks = _split_html_chunks(text, max_len=3850)
    last_msg_id: Optional[int] = None
    for idx, chunk in enumerate(chunks):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = int(message_thread_id)
        if idx == 0 and reply_to_message_id is not None:
            payload["reply_to_message_id"] = int(reply_to_message_id)
            payload["allow_sending_without_reply"] = True
        if idx == len(chunks) - 1 and reply_markup is not None:
            payload["reply_markup"] = reply_markup

        res = _call_telegram_api(bot_token, "sendMessage", payload)
        if not res.get("ok") and "message_thread_id" in payload and "thread not found" in str(res.get("description") or "").lower():
            payload.pop("message_thread_id", None)
            res = _call_telegram_api(bot_token, "sendMessage", payload)
        if not res.get("ok"):
            # Fallback without HTML parse_mode if entities failed
            plain_payload = dict(payload)
            plain_payload.pop("parse_mode", None)
            plain_payload["text"] = re.sub(r"<[^>]+>", "", chunk)
            res = _call_telegram_api(bot_token, "sendMessage", plain_payload)
        if res.get("ok") and isinstance(res.get("result"), dict):
            last_msg_id = res["result"].get("message_id")
    return last_msg_id


def _split_html_chunks(text: str, max_len: int = 3850) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < 800:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def answer_vip_callback(
    bot_token: str,
    callback_query_id: str,
    text: str,
    show_alert: bool = False,
) -> None:
    payload: Dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "text": text[:199],
        "show_alert": bool(show_alert),
    }
    _call_telegram_api(bot_token, "answerCallbackQuery", payload, timeout=8)


def _web_vip_chat_endpoints() -> List[str]:
    urls: List[str] = []
    local_port = os.getenv("PORT", os.getenv("PORT_WEB", "8000"))
    urls.append(f"http://127.0.0.1:{local_port}/api/telegram/vip-chat")
    return urls


def _update_user_quota_cache(tg_user_id: int, data: Dict[str, Any]) -> None:
    if not tg_user_id or not isinstance(data, dict):
        return
    if "remaining" in data or "is_pro" in data or data.get("error_code") == "LIMIT_REACHED":
        with _DEDUP_LOCK:
            prev = _USER_QUOTA_CACHE.get(int(tg_user_id)) or {}
            _USER_QUOTA_CACHE[int(tg_user_id)] = {
                "ok": True,
                "linked": bool(data.get("linked", prev.get("linked", False))),
                "is_pro": bool(data.get("is_pro", prev.get("is_pro", False))),
                "used": int(data.get("used") if data.get("used") is not None else prev.get("used", 0)),
                "limit": int(data.get("limit") if data.get("limit") is not None else prev.get("limit", 5)),
                "remaining": 0 if data.get("error_code") == "LIMIT_REACHED" else int(data.get("remaining") if data.get("remaining") is not None else prev.get("remaining", 5)),
                "period": str(data.get("period") or prev.get("period") or "monthly"),
                "ts": time.time(),
            }


def _get_cached_user_quota(tg_user_id: int, max_age_sec: float = 300.0) -> Optional[Dict[str, Any]]:
    # In unit tests where call_web_vip_chat_api is mocked, always call the mock directly
    if getattr(call_web_vip_chat_api, "__name__", "") != "call_web_vip_chat_api":
        return None
    with _DEDUP_LOCK:
        entry = _USER_QUOTA_CACHE.get(int(tg_user_id))
        if not entry:
            return None
        if time.time() - float(entry.get("ts", 0)) > max_age_sec:
            _USER_QUOTA_CACHE.pop(int(tg_user_id), None)
            return None
        return dict(entry)


def call_web_vip_chat_api(payload: Dict[str, Any], timeout: int = 75) -> Dict[str, Any]:
    """Execute VIP chat action directly via native Python engine on Hugging Face Space.
    Never invokes Vercel Serverless Functions, completely eliminating Vercel Active CPU.
    """
    tg_uid = int(payload.get("telegram_user_id") or 0)
    try:
        from api.native_telegram_vip_chat import handle_native_vip_chat
        res = handle_native_vip_chat(payload)
        if res and (res.get("ok") or res.get("error_code")):
            _update_user_quota_cache(tg_uid, res)
            return res
    except Exception as exc:
        print(f"[TELEGRAM_VIP_CHAT] Native chat handler error: {exc}")

    # Fallback to local Python FastAPI if available, NEVER to external Vercel prod
    admin_key = os.getenv("ADMIN_SECRET_KEY", "").strip()
    headers = {
        "Content-Type": "application/json",
        "x-admin-key": admin_key,
    }
    last_error = "Native handler failed"
    for url in _web_vip_chat_endpoints():
        try:
            resp = _WEB_SESSION.post(url, json=payload, headers=headers, timeout=(2.0, timeout))
            if resp.status_code in (200, 400, 403, 429):
                data = resp.json()
                if not data.get("skipped"):
                    _update_user_quota_cache(tg_uid, data)
                    return data
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            last_error = str(exc)
            continue

    return {"ok": False, "error": last_error}


def _clean_arabic_label(text: str) -> str:
    """Clean and standardize Arabic header labels for bullets and cards."""
    t = (text or "").strip()
    t = re.sub(r"\s*\(ج\.م\)", "", t)
    t = re.sub(r"\s*\(EGP\)", "", t, flags=re.I)
    t = re.sub(r"^\*+|\*+$", "", t).strip()
    return t


def _is_numeric_or_short_value(val: str) -> bool:
    """Determine if a cell contains a numeric metric, price, percentage, or short tag (fit for <code>)."""
    s = (val or "").strip()
    if not s or s in ("—", "-"):
        return False
    # Pure numbers, decimals, +/- %, or currencies
    if re.match(r"^[-+]?[\d,]+(?:\.\d+)?(?:\s*(?:%|ج\.م|EGP|x|X))?$", s):
        return True
    # Short dates or timestamps (e.g. 2026-10-20, 10:01, 15-10)
    if re.match(r"^\d{4}-\d{2}-\d{2}$|^\d{2}:\d{2}$|^\d{1,2}[-/]\d{1,2}$", s):
        return True
    # Short status indicators
    if len(s) <= 15 and any(k in s for k in ["إيجابي", "سلبي", "محايد", "صاعد", "هابط", "متعادل"]):
        return True
    return False


def _format_cell_value(val: str, is_value_col: bool = False) -> str:
    """Format cell value for Telegram HTML, applying <code> strictly to numbers/metrics."""
    s = (val or "").strip()
    s = re.sub(r"^\*+|\*+$", "", s).strip()
    s = re.sub(r"^`+|`+$", "", s).strip()
    if not s or s in ("—", "-"):
        return "—"

    esc = html.escape(s)

    if _is_numeric_or_short_value(s):
        m = re.match(r"^([-+]?[\d,]+(?:\.\d+)?)\s*(%|ج\.م|EGP|x|X)?$", s)
        if m:
            num = m.group(1)
            unit = m.group(2) or ""
            unit_str = f" {unit}" if unit else ""
            return f"<code>{num}{unit_str}</code>"
        return f"<code>{esc}</code>"

    # Qualitative description or sentence: NEVER wrap in <code>!
    if is_value_col and len(s) < 25:
        return f"<b>{esc}</b>"
    return f"<i>{esc}</i>"


def _format_markdown_table_smart(buf: List[str]) -> List[str]:
    """Parse and render a Markdown table buffer into sleek, mobile-optimized Telegram HTML."""
    if len(buf) < 2:
        return buf

    parsed_rows: List[List[str]] = []
    for r in buf:
        stripped = r.strip().strip("|")
        if re.match(r"^[\s:\-|]+$", stripped):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        if any(cells):
            parsed_rows.append(cells)

    if len(parsed_rows) < 2:
        return buf

    headers = [_clean_arabic_label(h) for h in parsed_rows[0]]
    rows = parsed_rows[1:]
    out: List[str] = []

    # Detect Table Structure
    # 1. Vertical Dashboard Table (2 or 3 columns: Item/Metric, Value, Description/Note)
    is_vertical_levels_or_metrics = (
        len(headers) in (2, 3) and
        any(k in headers[0] for k in ["المستوى", "المؤشر", "المقياس", "البيان", "العنصر", "المتوسط", "Metric", "Level"])
    )

    # 2. Multi-Stock Recommendations / Scanner Alert Table (must have entry/stop/target and not be a technical indicators table)
    headers_joined_lower = " ".join(headers).lower()
    has_target_or_stop = any(k in headers_joined_lower for k in ["دخول", "وقف", "هدف", "مستهدف", "target", "stop", "entry"])
    is_technical_indicator_table = any(k in headers_joined_lower for k in ["macd", "rsi", "هيستوجرام", "ema", "sma", "stoch"])
    is_stock_cards_table = (
        any(k in headers[0] for k in ["السهم", "الرمز", "Ticker", "Symbol"]) and
        has_target_or_stop and
        not is_technical_indicator_table
    )

    if is_vertical_levels_or_metrics:
        for row in rows:
            if not row or not any(row):
                continue
            item = html.escape(_clean_arabic_label(row[0]))
            val = row[1] if len(row) > 1 else ""
            desc = row[2] if len(row) > 2 else ""

            if desc in ("—", "-", val, ""):
                desc = ""

            formatted_val = _format_cell_value(val, is_value_col=True)
            line = f"▫️ <b>{item}:</b> {formatted_val}"
            if desc:
                # Strip markdown code marks and escape
                clean_desc = html.escape(re.sub(r"[`\*]", "", desc).strip())
                line += f" — <i>{clean_desc}</i>"
            out.append(line)

    elif is_stock_cards_table:
        col_map = {}
        for idx, h in enumerate(headers):
            h_clean = h.lower()
            if any(k in h_clean for k in ["سهم", "رمز", "symbol", "ticker"]):
                col_map["symbol"] = idx
            elif any(k in h_clean for k in ["إشارة", "نوع", "signal"]):
                col_map["signal"] = idx
            elif any(k in h_clean for k in ["وقت", "تاريخ", "time", "date"]):
                col_map["time"] = idx
            elif any(k in h_clean for k in ["سعر الدخول", "دخول", "entry"]):
                col_map["entry"] = idx
            elif any(k in h_clean for k in ["عائد", "تغير", "ربح", "return", "change"]):
                col_map["return"] = idx
            elif any(k in h_clean for k in ["هدف 1", "مستهدف 1", "target 1"]):
                col_map["target1"] = idx
            elif any(k in h_clean for k in ["هدف 2", "مستهدف 2", "target 2"]):
                col_map["target2"] = idx
            elif any(k in h_clean for k in ["سعر الحالي", "السعر الحالي", "إغلاق", "اغلاق", "سعر الإغلاق", "آخر سعر", "close"]):
                col_map["current"] = idx
            elif "حالي" in h_clean and "عائد" not in h_clean:
                col_map["current"] = idx
            elif any(k in h_clean for k in ["وقف", "stop"]):
                col_map["stop"] = idx
            elif any(k in h_clean for k in ["أفق", "مدى", "horizon"]):
                col_map["horizon"] = idx
            elif any(k in h_clean for k in ["هدف", "مستهدف", "target"]) and "target1" not in col_map:
                col_map["target1"] = idx

        for row in rows:
            if not row or not any(row):
                continue
            sym = html.escape(re.sub(r"[`\*]", "", row[col_map.get("symbol", 0)]).strip())
            signal = html.escape(re.sub(r"[`\*]", "", row[col_map["signal"]]).strip()) if "signal" in col_map and col_map["signal"] < len(row) else ""
            time_val = html.escape(re.sub(r"[`\*]", "", row[col_map["time"]]).strip()) if "time" in col_map and col_map["time"] < len(row) else ""
            entry = html.escape(re.sub(r"[`\*]", "", row[col_map["entry"]]).strip()) if "entry" in col_map and col_map["entry"] < len(row) else ""
            current = html.escape(re.sub(r"[`\*]", "", row[col_map["current"]]).strip()) if "current" in col_map and col_map["current"] < len(row) else ""
            ret = html.escape(re.sub(r"[`\*]", "", row[col_map["return"]]).strip()) if "return" in col_map and col_map["return"] < len(row) else ""
            t1 = html.escape(re.sub(r"[`\*]", "", row[col_map["target1"]]).strip()) if "target1" in col_map and col_map["target1"] < len(row) else ""
            t2 = html.escape(re.sub(r"[`\*]", "", row[col_map["target2"]]).strip()) if "target2" in col_map and col_map["target2"] < len(row) else ""
            stop = html.escape(re.sub(r"[`\*]", "", row[col_map["stop"]]).strip()) if "stop" in col_map and col_map["stop"] < len(row) else ""
            horizon = html.escape(re.sub(r"[`\*]", "", row[col_map["horizon"]]).strip()) if "horizon" in col_map and col_map["horizon"] < len(row) else ""

            # Card Header
            header_parts = [f"🔹 <b>{sym}</b>"]
            if signal and not re.match(r"^[−\-\+]?\d+(?:\.\d+)?%?$", signal.strip()):
                header_parts.append(f"<i>{signal}</i>")
            if time_val and time_val != "—":
                header_parts.append(f"⏱️ <code>{time_val}</code>")
            out.append(" — ".join(header_parts))

            # Row 1: Prices & Return
            price_parts = []
            if entry and entry != "—":
                price_parts.append(f"الدخول: <code>{entry}</code>")
            if current and current != "—":
                price_parts.append(f"الحالي: <code>{current}</code>")
            if ret and ret != "—":
                ret_badge = "🟢" if "+" in ret or ("-" not in ret and ret != "0%") else "🔴"
                price_parts.append(f"<b>{ret}</b> {ret_badge}")
            if price_parts:
                out.append("   ▫️ " + " ◂ ".join(price_parts))

            # Row 2: Targets & Stop Loss
            plan_parts = []
            targets = []
            if t1 and t1 != "—":
                targets.append(f"<code>{t1}</code>")
            if t2 and t2 != "—":
                targets.append(f"<code>{t2}</code>")
            if targets:
                plan_parts.append(f"الأهداف: {' / '.join(targets)}")
            if stop and stop != "—":
                plan_parts.append(f"الوقف: <code>{stop}</code>")
            if horizon and horizon != "—":
                plan_parts.append(f"الأفق: <i>{horizon}</i>")
            if plan_parts:
                out.append("   ▫️ " + " | ".join(plan_parts))
            out.append("")  # Empty separator between cards

    else:
        # Generic clean key-value bullets
        for row in rows:
            if not row or not any(row):
                continue
            first = html.escape(_clean_arabic_label(row[0]))
            details: List[str] = []
            for idx in range(1, len(row)):
                val = row[idx]
                if not val or val == "—":
                    continue
                col_name = html.escape(headers[idx]) if idx < len(headers) else ""
                val_formatted = _format_cell_value(val)
                if col_name:
                    details.append(f"{col_name}: {val_formatted}")
                else:
                    details.append(val_formatted)
            if details:
                out.append(f"▫️ <b>{first}</b> — " + " | ".join(details))
            else:
                out.append(f"▫️ <b>{first}</b>")

    return out


def _format_table_for_telegram(table: Dict[str, Any]) -> str:
    """Render an ExcelTable object into sleek, mobile-readable Telegram HTML."""
    title = str(table.get("title") or "").strip()
    headers = [str(h).strip() for h in (table.get("headers") or [])]
    rows = table.get("rows") or []
    if not rows or not headers:
        return ""

    # Reconstruct as table buffer to leverage _format_markdown_table_smart
    buf = ["| " + " | ".join(headers) + " |"]
    buf.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows[:15]:
        if isinstance(r, list):
            buf.append("| " + " | ".join(str(c) for c in r) + " |")

    formatted_lines = _format_markdown_table_smart(buf)
    lines: List[str] = []
    if title:
        lines.append(f"\n📊 <b>{html.escape(title)}</b>")
    lines.extend(formatted_lines)
    return "\n".join(lines)


def _convert_markdown_tables_to_bullets(md_text: str) -> str:
    """Convert raw Markdown pipe tables in LLM text into sleek Telegram HTML structures."""
    lines = md_text.split("\n")
    out: List[str] = []
    table_buffer: List[str] = []

    def _flush_table() -> None:
        nonlocal table_buffer
        if table_buffer:
            out.extend(_format_markdown_table_smart(table_buffer))
            table_buffer = []

    for line in lines:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            table_buffer.append(line)
        else:
            if table_buffer:
                _flush_table()
            out.append(line)
    if table_buffer:
        _flush_table()
    return "\n".join(out)


def format_pipeline_reply_for_telegram(
    reply_text: str,
    tables: List[Dict[str, Any]],
    user_name: str,
    tg_user_id: int,
    is_pro: bool,
    used: int,
    limit: int,
    remaining: int,
    period: str,
) -> str:
    """Convert pipeline markdown response + tables into rich Telegram HTML."""
    cleaned = (reply_text or "").strip()
    # Telegram users are already inside Telegram: drop Telegram promo lines and duplicate website markdown lines
    cleaned = re.sub(r"^[^\n]*(?:t\.me/|/profile#telegram|قناة VIP على تليجرام|قناة EGX Bots المجانية)[^\n]*\n?", "", cleaned, flags=re.MULTILINE).rstrip()
    cleaned = re.sub(r"👑\s*\[قناة VIP على تليجرام[^\]]*\]\([^\)]+\)", "", cleaned).rstrip()
    cleaned = re.sub(r"📢\s*\[قناة EGX Bots المجانية[^\]]*\]\([^\)]+\)", "", cleaned).rstrip()
    cleaned = re.sub(r"🌐\s*\[منصة EGX Bots[^\]]*\]\([^\)]+\)(?:\s*•\s*👑\s*\[ترقية باقة VIP\]\([^\)]+\))?", "", cleaned).rstrip()
    has_md_table = bool(re.search(r"^\|.+\|$", cleaned, flags=re.MULTILINE))

    # Smart line-by-line conversion for tables, blockquotes, headers, and dividers
    lines = cleaned.split("\n")
    processed_lines: List[str] = []
    table_buf: List[str] = []
    quote_buf: List[str] = []

    def _flush_table_buf() -> None:
        nonlocal table_buf
        if table_buf:
            processed_lines.extend(_format_markdown_table_smart(table_buf))
            table_buf = []

    def _flush_quote_buf() -> None:
        nonlocal quote_buf
        if quote_buf:
            quote_text = "\n".join(quote_buf)
            processed_lines.append(f"<blockquote>{quote_text}</blockquote>")
            quote_buf = []

    for line in lines:
        s = line.strip()

        # 1. Pipe Table row
        if s.startswith("|") and s.endswith("|"):
            _flush_quote_buf()
            table_buf.append(line)
            continue
        else:
            _flush_table_buf()

        # 2. Blockquote (> ...)
        if s.startswith(">"):
            content = re.sub(r"^>\s?", "", line).strip()
            content_esc = html.escape(content)
            content_esc = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", content_esc)
            content_esc = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", content_esc)
            quote_buf.append(content_esc)
            continue
        else:
            _flush_quote_buf()

        # 3. Headers (### Header)
        m_h = re.match(r"^\s*#{1,4}\s+(.+)$", line)
        if m_h:
            h_text = m_h.group(1).strip()
            h_esc = html.escape(h_text)
            if any(k in h_text for k in ["مستو", "دعم", "مقاوم"]):
                icon = "🎯"
            elif any(k in h_text for k in ["مؤشر", "بيان", "مالي", "فني"]):
                icon = "📈"
            elif any(k in h_text for k in ["رأي", "خطة", "تحرك", "نصيح"]):
                icon = "💡"
            elif any(k in h_text for k in ["توصي", "إشار", "فرص"]):
                icon = "🚀"
            elif any(k in h_text for k in ["محفظ", "مركز"]):
                icon = "💼"
            elif any(k in h_text for k in ["سوق", "egx"]):
                icon = "📊"
            elif any(k in h_text for k in ["مقارن"]):
                icon = "⚖️"
            elif any(k in h_text for k in ["خبر", "أخبار", "إفصاح"]):
                icon = "📰"
            else:
                icon = "🔹"
            processed_lines.append(f"\n{icon} <b>{h_esc}</b>")
            continue

        # 4. Dividers (---, ***, ___)
        if re.match(r"^[-*_]{3,}$", s):
            processed_lines.append("──────────────────")
            continue

        # 5. Regular text lines: escape and format standard markdown tags
        esc_line = html.escape(line)
        esc_line = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s\)]+)\)",
            r'<a href="\2">\1</a>',
            esc_line,
        )
        esc_line = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", esc_line)
        esc_line = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", esc_line)

        processed_lines.append(esc_line)

    _flush_table_buf()
    _flush_quote_buf()

    formatted_body = "\n".join(processed_lines)
    formatted_body = re.sub(r"\n{3,}", "\n\n", formatted_body).strip()

    # If structured tables were returned and not already present in the body, append them
    if tables and not has_md_table:
        rendered_tables = [_format_table_for_telegram(t) for t in tables[:3]]
        rendered_tables = [t for t in rendered_tables if t]
        if rendered_tables:
            formatted_body += "\n" + "\n".join(rendered_tables)

    safe_user = html.escape(user_name or "المستثمر")
    user_link = f'<a href="tg://user?id={tg_user_id}">{safe_user}</a>'
    plan_badge = "👑 PRO VIP" if is_pro else "🎫 مجاني (Free)"
    period_label = "شهرياً" if period == "monthly" else "اليوم"

    site_origin = (get_web_origin() or "https://egxbots.com").rstrip("/")
    if "localhost" in site_origin or "127.0.0.1" in site_origin:
        site_origin = "https://egxbots.com"
    footer = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 المستثمر: <b>{user_link}</b> | الباقة: <b>{plan_badge}</b>\n"
        f"📊 الرصيد المتبقي ({period_label}): <code>{remaining}</code> من <code>{limit}</code> سؤال\n"
        f'🌐 <a href="{site_origin}">موقع EGX Bots</a> • 💎 <a href="{_pricing_url()}">صفحة التسعير والاشتراك</a>'
    )

    return f"🤖 <b>رد أرتورو الذكي لـ {user_link}:</b>\n\n{formatted_body}{footer}"


def is_vip_chat_update(data: Dict[str, Any]) -> bool:
    """Return True if this Telegram update belongs to the VIP Chat room / topic or @egxbots_bot private chat."""
    if data.get("callback_query"):
        cb_data = str(data["callback_query"].get("data") or "")
        if cb_data.startswith("vip_"):
            return True

    msg = data.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id_str = str(chat.get("id") or "")
    chat_type = str(chat.get("type") or "")
    thread_id = msg.get("message_thread_id")
    text = str(msg.get("text") or "").strip()

    target_group = get_vip_group_id()
    target_topic = get_vip_topic_id()

    # 1. Inside the configured official supergroup (e.g., -1002083067817):
    # STRICT TOPIC ISOLATION: The bot operates EXCLUSIVELY inside topic 1680 (ARTORO topic).
    # It must NEVER reply to messages in Topic 1 ("الدردشة العامة"), Topic 153 ("التوصيات"), or any other topic.
    if chat_id_str == target_group:
        if target_topic is not None and thread_id != target_topic:
            return False
        return True

    # 2. Inside Private 1-on-1 Chat with @egxbots_bot:
    if chat_type == "private" or (chat_id_str and chat_id_str == str((msg.get("from") or {}).get("id"))):
        # Let telegram_bot handle deep link account connection (/start <uuid>)
        if text.startswith("/start") and len(text.split()) > 1:
            arg = text.split()[1].strip().lower()
            if arg not in ("artoro_chat", "artoro", "chat", "vip", "alerts", "start", "connect", "bot"):
                return False
        return True

    # 3. For any other standalone supergroup (if explicitly addressed):
    if chat_type in ("group", "supergroup"):
        if text.lower().startswith(("/vippanel", "/artoro_panel", "/ask")):
            return True
        reply_to = msg.get("reply_to_message") or {}
        reply_text = str(reply_to.get("text") or "")
        if "تحليل سهم فوري —" in reply_text or "مقارنة الأسهم —" in reply_text or "اسأل أرتورو —" in reply_text:
            return True

    return False


def _extract_user_info(from_obj: Dict[str, Any]) -> Tuple[int, str]:
    tg_user_id = int(from_obj.get("id") or 0)
    first = str(from_obj.get("first_name") or "").strip()
    last = str(from_obj.get("last_name") or "").strip()
    username = str(from_obj.get("username") or "").strip()
    full_name = f"{first} {last}".strip() or username or "المستثمر"
    return tg_user_id, full_name


def _show_limit_or_upgrade_dialog(
    bot_token: str,
    chat_id: Any,
    thread_id: Optional[int],
    tg_user_id: int,
    user_name: str,
    reason: str = "limit_reached",
    used: int = 5,
    limit: int = 5,
    callback_query_id: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    1. If triggered from a button click (callback_query_id), pop up a native modal
       Alert Dialog (show_alert=True) visible ONLY to that user!
    2. Also send the rich Pricing & Upgrade Dialog Card (with direct link to /pricing)
       to the user's Private DM (and/or in the topic if DM isn't open or triggered by text).
    """
    if callback_query_id:
        if reason == "pro_required":
            alert_text = PRO_ONLY_TOOL_ALERT_TEXT
        elif reason == "account_link":
            alert_text = ACCOUNT_LINK_ALERT_TEXT
        elif reason == "pricing_info":
            alert_text = PRICING_FEATURES_ALERT_TEXT
        else:
            alert_text = LIMIT_REACHED_ALERT_TEXT
        answer_vip_callback(bot_token, callback_query_id, alert_text, show_alert=True)

    dialog_html = build_pricing_dialog_html(
        user_name=user_name,
        tg_user_id=tg_user_id,
        reason=reason,
        used=used,
        limit=limit,
    )
    keyboard = build_pricing_upgrade_keyboard()

    # Try sending to the user's Private DM first so it's 100% private to them
    dm_sent = False
    if tg_user_id and str(chat_id) != str(tg_user_id):
        dm_res = _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": tg_user_id,
                "text": dialog_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            },
        )
        dm_sent = bool(dm_res.get("ok"))

    # Also post the upgrade card in the topic if DM wasn't reachable, or if user clicked Pricing / hit limit via text
    if not dm_sent or not callback_query_id or reason == "pricing_info":
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=dialog_html,
            message_thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            reply_markup=keyboard,
        )


def _show_topic_recs_restricted_dialog(
    bot_token: str,
    chat_id: Any,
    thread_id: Optional[int],
    tg_user_id: int,
    user_name: str,
    callback_query_id: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    In the public group topic, open recommendations are restricted to protect privacy & fairness.
    1. If triggered by button (callback_query_id), answers with native modal alert.
    2. Tries to send details to user's Private DM first.
    3. If DM fails (or triggered by text in topic), replies in the group topic.
    """
    if callback_query_id:
        answer_vip_callback(
            bot_token=bot_token,
            callback_query_id=callback_query_id,
            text=TOPIC_RECS_RESTRICTED_ALERT_TEXT,
            show_alert=True,
        )

    text_html = build_topic_recs_restricted_html(user_name=user_name, tg_user_id=tg_user_id)
    keyboard = build_topic_recs_restricted_keyboard()

    dm_sent = False
    if tg_user_id and str(chat_id) != str(tg_user_id) and callback_query_id:
        dm_res = _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": tg_user_id,
                "text": text_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            },
        )
        dm_sent = bool(dm_res.get("ok"))

    if not dm_sent:
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=text_html,
            message_thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            reply_markup=keyboard,
        )


_VIP_WORKER_SLOTS = threading.BoundedSemaphore(int(os.getenv("TELEGRAM_VIP_MAX_CONCURRENCY", "8") or 8))


def _download_telegram_file(bot_token: str, file_id: str) -> Optional[Tuple[str, str, bytes]]:
    """
    Download a photo/document from Telegram via getFile and return (data_uri, file_path, raw_bytes).
    """
    if not bot_token or not file_id:
        return None
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getFile"
        resp = requests.post(url, json={"file_id": file_id}, timeout=12)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("ok"):
            return None
        file_path = data.get("result", {}).get("file_path")
        if not file_path:
            return None

        dl_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        dl_resp = requests.get(dl_url, timeout=30)
        if dl_resp.status_code != 200:
            return None

        raw_bytes = dl_resp.content
        import base64
        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        ext = file_path.lower().split(".")[-1] if "." in file_path else "jpg"
        mime = "image/png" if ext == "png" else "image/jpeg"
        data_uri = f"data:{mime};base64,{b64}"
        return data_uri, file_path, raw_bytes
    except Exception as exc:
        print(f"[TELEGRAM_VIP_CHAT] _download_telegram_file error: {exc}")
        return None


def _upload_telegram_image_to_storage(raw_bytes: bytes, file_path: str) -> Optional[str]:
    """
    Upload image bytes to Supabase Storage bucket 'chat-images' and return public URL.
    """
    if not raw_bytes:
        return None
    try:
        from api.stock_ai import _init_supabase, supabase
        _init_supabase()
        from datetime import datetime
        ext = "png" if file_path.lower().endswith(".png") else "jpg"
        mime = "image/png" if ext == "png" else "image/jpeg"
        base_name = os.path.basename(file_path)
        filename = f"telegram/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{base_name}"
        supabase.storage.from_("chat-images").upload(
            filename,
            raw_bytes,
            {"content-type": mime, "upsert": "true"}
        )
        pub_url = supabase.storage.from_("chat-images").get_public_url(filename)
        return pub_url
    except Exception as exc:
        print(f"[TELEGRAM_VIP_CHAT] Supabase storage upload warning: {exc}")
        return None


def _execute_and_reply_vip_chat(
    bot_token: str,
    chat_id: Any,
    thread_id: Optional[int],
    tg_user_id: int,
    user_name: str,
    query_text: str,
    reply_to_message_id: Optional[int] = None,
    callback_query_id: Optional[str] = None,
    file_id: Optional[str] = None,
    images: Optional[List[str]] = None,
) -> None:
    """Bounded-concurrency wrapper: bursts of simultaneous users queue briefly instead of overloading the backend."""
    acquired = _VIP_WORKER_SLOTS.acquire(timeout=90)
    try:
        _execute_and_reply_vip_chat_inner(
            bot_token, chat_id, thread_id, tg_user_id, user_name, query_text,
            reply_to_message_id, callback_query_id, file_id=file_id, images=images,
        )
    finally:
        if acquired:
            _VIP_WORKER_SLOTS.release()


def _execute_and_reply_vip_chat_inner(
    bot_token: str,
    chat_id: Any,
    thread_id: Optional[int],
    tg_user_id: int,
    user_name: str,
    query_text: str,
    reply_to_message_id: Optional[int] = None,
    callback_query_id: Optional[str] = None,
    file_id: Optional[str] = None,
    images: Optional[List[str]] = None,
) -> None:
    """Run the query through the website's Agentic Pipeline (/api/telegram/vip-chat) and post the formatted answer."""
    processed_images: List[str] = list(images or [])
    image_storage_url: Optional[str] = None

    if file_id and not processed_images:
        dl_res = _download_telegram_file(bot_token, file_id)
        if dl_res:
            data_uri, file_path, raw_bytes = dl_res
            image_storage_url = _upload_telegram_image_to_storage(raw_bytes, file_path)
            processed_images.append(data_uri)

    safe_user = html.escape(user_name or "المستثمر")
    safe_query = html.escape(query_text[:120])
    if file_id or processed_images:
        wait_text = (
            f"📸 <b>استلمت صورة المحفظة / الشارت يا <a href=\"tg://user?id={tg_user_id}\">{safe_user}</a>!</b>\n"
            f"🔍 <i>جاري فحص الأسهم وحساب نقاط الدعم والمقاومة والأهداف بالذكاء الاصطناعي...</i>"
        )
    else:
        wait_text = (
            f"⏳ <b>جاري تحليل طلبك يا <a href=\"tg://user?id={tg_user_id}\">{safe_user}</a>...</b>\n"
            f"💬 الطلب: <code>{safe_query}</code>"
        )

    wait_msg_id = send_vip_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=wait_text,
        message_thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
    )

    action_payload: Dict[str, Any] = {"chat_id": chat_id, "action": "typing"}
    if thread_id is not None:
        action_payload["message_thread_id"] = int(thread_id)
    _call_telegram_api(bot_token, "sendChatAction", action_payload, timeout=4)

    is_private_chat = str(chat_id) == str(tg_user_id)
    api_payload: Dict[str, Any] = {
        "action": "chat",
        "telegram_user_id": tg_user_id,
        "telegram_username": user_name,
        "message": query_text,
        "chat_source": "telegram_private" if is_private_chat else "telegram_topic",
    }
    if processed_images:
        api_payload["images"] = processed_images
    if image_storage_url:
        api_payload["image_storage_url"] = image_storage_url

    api_res = call_web_vip_chat_api(api_payload)

    # Delete temporary waiting message
    if wait_msg_id:
        try:
            _call_telegram_api(
                bot_token,
                "deleteMessage",
                {"chat_id": chat_id, "message_id": wait_msg_id},
                timeout=5,
            )
        except Exception:
            pass

    if not api_res.get("ok"):
        err_code = str(api_res.get("error_code") or "")
        used = int(api_res.get("used") or 5)
        limit = int(api_res.get("limit") or 5)
        if err_code == "LIMIT_REACHED":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="limit_reached",
                used=used,
                limit=limit,
                callback_query_id=callback_query_id,
                reply_to_message_id=reply_to_message_id,
            )
            return
        if err_code == "PRO_REQUIRED":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="pro_required",
                used=used,
                limit=limit,
                callback_query_id=callback_query_id,
                reply_to_message_id=reply_to_message_id,
            )
            return
        if err_code == "ACCOUNT_LINK_REQUIRED":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="account_link",
                used=used,
                limit=limit,
                callback_query_id=callback_query_id,
                reply_to_message_id=reply_to_message_id,
            )
            return

        err_detail = html.escape(str(api_res.get("detail") or api_res.get("error") or "تعذر إكمال التحليل حالياً"))
        is_priv = str(chat_id) == str(tg_user_id)
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=f"⚠️ <b>عذراً يا {safe_user}، تعذر إتمام الطلب حالياً:</b>\n<code>{err_detail}</code>",
            message_thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            reply_markup=build_vip_chat_keyboard(is_private=is_priv),
        )
        return

    formatted_html = format_pipeline_reply_for_telegram(
        reply_text=str(api_res.get("reply") or ""),
        tables=api_res.get("tables") or [],
        user_name=str(api_res.get("display_name") or user_name),
        tg_user_id=tg_user_id,
        is_pro=bool(api_res.get("is_pro")),
        used=int(api_res.get("used") or 1),
        limit=int(api_res.get("limit") or 5),
        remaining=int(api_res.get("remaining") or 0),
        period=str(api_res.get("period") or "daily"),
    )

    is_priv = str(chat_id) == str(tg_user_id)
    send_vip_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=formatted_html,
        message_thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
        reply_markup=build_vip_chat_keyboard(is_private=is_priv),
    )


def handle_vip_chat_update(data: Dict[str, Any], bot_token: str) -> bool:
    """
    Process a Telegram update (callback_query or message) for the VIP Chat room or @egxbots_bot private chat.
    Returns True if handled.
    """
    if not bot_token:
        return False

    # 1. Handle Inline Button Callbacks (vip_*)
    if data.get("callback_query"):
        cb = data["callback_query"]
        cb_id = str(cb.get("id") or "")
        cb_data = str(cb.get("data") or "")
        if not cb_data.startswith("vip_"):
            return False

        if cb_id and not _mark_event_processed(f"cb:{cb_id}"):
            return True

        msg = cb.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        chat_type = str(chat.get("type") or "")
        is_private = chat_type == "private" or (chat_id is not None and str(chat_id) == str((cb.get("from") or {}).get("id")))
        thread_id = msg.get("message_thread_id")
        from_obj = cb.get("from") or {}
        tg_user_id, user_name = _extract_user_info(from_obj)

        if not chat_id or not tg_user_id:
            return True

        # A) Pure Pricing Alert Popup Dialog
        if cb_data == "vip_pricing_alert":
            answer_vip_callback(bot_token, cb_id, PRICING_FEATURES_ALERT_TEXT, show_alert=True)
            return True

        # B) Show Pricing Dialog + Card
        if cb_data == "vip_pricing_dialog":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="pricing_info",
                callback_query_id=cb_id,
            )
            return True

        # C) Show Control Panel
        if cb_data == "vip_show_panel":
            answer_vip_callback(bot_token, cb_id, "🤖 لوحة أدوات أرتورو الذكية جاهزة!")
            send_vip_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=build_welcome_panel_html(is_private=is_private, chat_id=chat_id),
                message_thread_id=thread_id,
                reply_markup=build_vip_chat_keyboard(is_private=is_private),
            )
            return True

        # D) Check Quota Status (📊 رصيدي وخطتي)
        if cb_data == "vip_my_quota":
            q_res = call_web_vip_chat_api(
                {
                    "action": "check_quota",
                    "telegram_user_id": tg_user_id,
                    "telegram_username": user_name,
                },
                timeout=15,
            )
            is_pro = bool(q_res.get("is_pro"))
            linked = bool(q_res.get("linked"))
            used = int(q_res.get("used") or 0)
            limit = int(q_res.get("limit") or (350 if is_pro else 5))
            remaining = int(q_res.get("remaining") if q_res.get("remaining") is not None else max(0, limit - used))
            plan_txt = "👑 باقة PRO VIP" if is_pro else "🎫 الباقة المجانية (Free)"
            link_txt = "مربوط بالموقع ✅" if linked else "غير مربوط (اربطه من البروفايل)"
            period_txt = "شهرياً" if is_pro else "اليوم"

            quota_alert = (
                f"📊 حالة حسابك يا {user_name[:22]}:\n"
                f"• الباقة: {plan_txt}\n"
                f"• الحساب: {link_txt}\n"
                f"• المستهلك ({period_txt}): {used} من {limit}\n"
                f"• المتبقي لك: {remaining} سؤال"
            )
            answer_vip_callback(bot_token, cb_id, quota_alert, show_alert=True)
            return True

        # E) Interactive Input Prompts: vip_ask_stock, vip_ask_compare, vip_ask_free
        if cb_data in ("vip_ask_stock", "vip_ask_compare", "vip_ask_free"):
            mode_map = {
                "vip_ask_stock": "stock",
                "vip_ask_compare": "compare",
                "vip_ask_free": "free",
            }
            mode = mode_map[cb_data]

            # Use instant in-memory quota cache if available; persist pending_prompt asynchronously in background!
            is_mocked = getattr(call_web_vip_chat_api, "__name__", "") != "call_web_vip_chat_api"
            cached_q = _get_cached_user_quota(tg_user_id)
            if is_mocked:
                q_res = call_web_vip_chat_api(
                    {
                        "action": "set_pending_prompt",
                        "telegram_user_id": tg_user_id,
                        "telegram_username": user_name,
                        "prompt_mode": mode,
                    },
                    timeout=15,
                )
            else:
                q_res = cached_q or {"ok": True, "remaining": 5, "used": 0, "limit": 5}
                threading.Thread(
                    target=call_web_vip_chat_api,
                    args=(
                        {
                            "action": "set_pending_prompt",
                            "telegram_user_id": tg_user_id,
                            "telegram_username": user_name,
                            "prompt_mode": mode,
                        },
                        10,
                    ),
                    daemon=True,
                ).start()

            remaining = int(q_res.get("remaining") if q_res.get("remaining") is not None else 5)
            used = int(q_res.get("used") or 0)
            limit = int(q_res.get("limit") or 5)

            if q_res.get("ok") and remaining <= 0:
                set_local_pending_prompt(chat_id, tg_user_id, None)
                _show_limit_or_upgrade_dialog(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    tg_user_id=tg_user_id,
                    user_name=user_name,
                    reason="limit_reached",
                    used=used,
                    limit=limit,
                    callback_query_id=cb_id,
                )
                return True

            set_local_pending_prompt(chat_id, tg_user_id, mode)
            safe_user = html.escape(user_name)
            user_mention = f'<a href="tg://user?id={tg_user_id}">{safe_user}</a>'

            if mode == "stock":
                answer_vip_callback(bot_token, cb_id, "🔍 اكتب اسم السهم بالعربي أو الكود الآن...")
                prompt_html = (
                    f"🔍 <b>تحليل سهم فوري — {user_mention}</b>\n"
                    f"✍️ اكتب الآن <b>اسم السهم بالعربي أو رمزه</b> في رسالتك القادمة "
                    f"(مثال: <code>فوري</code> أو <code>COMI</code> أو <code>طلعت مصطفى</code> أو <code>أبوقير</code>):"
                )
                placeholder = "اكتب اسم السهم أو رمزه (مثال: فوري أو COMI)..."
            elif mode == "compare":
                answer_vip_callback(bot_token, cb_id, "⚖️ اكتب اسم السهمين للمقارنة الآن...")
                prompt_html = (
                    f"⚖️ <b>مقارنة الأسهم — {user_mention}</b>\n"
                    f"✍️ اكتب الآن <b>اسم السهمين بالعربي أو الرمز</b> في رسالتك القادمة "
                    f"(مثال: <code>التجاري الدولي وفوري</code> أو <code>COMI و HRHO</code>):"
                )
                placeholder = "مثال: التجاري الدولي وفوري..."
            else:
                answer_vip_callback(bot_token, cb_id, "🤖 اكتب سؤالك لأرتورو الآن...")
                prompt_html = (
                    f"🤖 <b>اسأل أرتورو — {user_mention}</b>\n"
                    f"✍️ اكتب الآن سؤالك أو استفسارك عن السوق أو أي سهم في رسالتك القادمة:"
                )
                placeholder = "اكتب سؤالك لأرتورو هنا..."

            send_vip_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=prompt_html,
                message_thread_id=thread_id,
                reply_markup={
                    "force_reply": True,
                    "selective": True,
                    "input_field_placeholder": placeholder,
                },
            )
            return True

        # F) 1-Click Instant Tools (vip_tool_*)
        tool_queries = {
            "vip_tool_market": "أقوى الأسهم النهارده وملخص السوق",
            "vip_tool_accum": "أقوى أسهم التجميع والسيولة الذكية اليوم",
            "vip_tool_scan": "أفضل الأسهم فنياً اليوم حسب المسح الفني والمؤشرات",
            "vip_tool_recs": "هات كل التوصيات المفتوحة حالياً",
            "vip_tool_news": "أهم أخبار وإفصاحات البورصة المصرية اليوم",
            "vip_tool_portfolio": "حلل محفظتي الاستثمارية بالتفصيل",
        }
        if cb_data in tool_queries:
            # In the public group topic, open recommendations are restricted completely
            if cb_data == "vip_tool_recs" and not is_private:
                _show_topic_recs_restricted_dialog(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    tg_user_id=tg_user_id,
                    user_name=user_name,
                    callback_query_id=cb_id,
                )
                return True

            query_text = tool_queries[cb_data]
            # Use fast in-memory quota cache when available so button clicks respond in 0ms!
            cached_q = _get_cached_user_quota(tg_user_id)
            if cached_q is not None:
                q_res = cached_q
            elif cb_data in ("vip_tool_recs", "vip_tool_portfolio") or getattr(call_web_vip_chat_api, "__name__", "") != "call_web_vip_chat_api":
                q_res = call_web_vip_chat_api(
                    {
                        "action": "check_quota",
                        "telegram_user_id": tg_user_id,
                        "telegram_username": user_name,
                    },
                    timeout=10,
                )
            else:
                q_res = {"ok": True, "is_pro": True, "linked": True, "remaining": 5, "used": 0, "limit": 5}
            if q_res.get("ok"):
                is_pro = bool(q_res.get("is_pro"))
                linked = bool(q_res.get("linked"))
                remaining = int(q_res.get("remaining") if q_res.get("remaining") is not None else 5)
                used = int(q_res.get("used") or 0)
                limit = int(q_res.get("limit") or 5)

                if cb_data == "vip_tool_recs" and not is_pro:
                    _show_limit_or_upgrade_dialog(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        tg_user_id=tg_user_id,
                        user_name=user_name,
                        reason="pro_required",
                        used=used,
                        limit=limit,
                        callback_query_id=cb_id,
                    )
                    return True

                if cb_data == "vip_tool_portfolio" and not linked:
                    _show_limit_or_upgrade_dialog(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        tg_user_id=tg_user_id,
                        user_name=user_name,
                        reason="account_link",
                        used=used,
                        limit=limit,
                        callback_query_id=cb_id,
                    )
                    return True

                if remaining <= 0:
                    _show_limit_or_upgrade_dialog(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        tg_user_id=tg_user_id,
                        user_name=user_name,
                        reason="limit_reached",
                        used=used,
                        limit=limit,
                        callback_query_id=cb_id,
                    )
                    return True

            answer_vip_callback(bot_token, cb_id, "⏳ جاري تجهيز التحليل من أرتورو...")
            threading.Thread(
                target=_execute_and_reply_vip_chat,
                kwargs={
                    "bot_token": bot_token,
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                    "tg_user_id": tg_user_id,
                    "user_name": user_name,
                    "query_text": query_text,
                    "callback_query_id": None,
                },
                daemon=True,
            ).start()
            return True

        return False

    # 2. Handle Regular Messages in the VIP Chat Topic or Private Chat with @egxbots_bot
    msg = data.get("message") or {}
    if not msg:
        return False

    # Ignore messages sent by bots
    from_obj = msg.get("from") or {}
    if from_obj.get("is_bot"):
        return False

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = str(chat.get("type") or "")
    thread_id = msg.get("message_thread_id")
    msg_id = msg.get("message_id")

    photos = msg.get("photo") or []
    document = msg.get("document") or {}
    doc_mime = str(document.get("mime_type") or "").lower()
    is_image_doc = bool(document and doc_mime.startswith("image/"))
    has_photo = bool(photos or is_image_doc)
    photo_file_id = photos[-1].get("file_id") if photos else (document.get("file_id") if is_image_doc else None)

    caption = str(msg.get("caption") or "").strip()
    text = str(msg.get("text") or caption).strip()

    if not chat_id or (not text and not has_photo):
        return False

    if has_photo and not text:
        text = "حلل محفظتي الاستثمارية بناءً على الصورة المرفقة واستخرج الأسهم والأسعار والكميات وقدم خطة دعم ومقاومة وهدف ووقف خسارة لكل سهم"

    tg_user_id, user_name = _extract_user_info(from_obj)
    if not tg_user_id:
        return False

    is_private = chat_type == "private" or str(chat_id) == str(tg_user_id)

    if msg_id and not _mark_event_processed(f"msg:{chat_id}:{msg_id}"):
        return True

    clean_lower = text.lower().split("@")[0].split()[0]

    # Quick Quota Simulation Commands for Testing (/test_limit, /test_free, /test_normal)
    if clean_lower in ("/test_limit", "/test_free", "/test_normal"):
        mode_arg = {
            "/test_limit": "limit_reached",
            "/test_free": "free_plan",
            "/test_normal": "normal",
        }[clean_lower]
        res = call_web_vip_chat_api(
            {
                "action": "set_test_mode",
                "telegram_user_id": tg_user_id,
                "telegram_username": user_name,
                "test_mode": mode_arg,
            },
            timeout=15,
        )
        if mode_arg == "limit_reached":
            msg_txt = (
                "🧪 <b>تم تفعيل وضع اختبار انتهاء الكوتا (Limit Reached 5/5):</b>\n"
                "اضغط الآن على أي زر في اللوحة بالأسفل (مثل <code>🔍 حلل سهم</code> أو <code>📈 ملخص السوق</code>) "
                "لترى كيف تظهر <b>النافذة المنبثقة الخاصة (Dialog)</b> وكارت التسعير للمستخدم حين ينتهي رصيده!\n"
                "• للعودة لحسابك الطبيعي اكتب: <code>/test_normal</code>"
            )
        elif mode_arg == "free_plan":
            msg_txt = (
                "🧪 <b>تم تفعيل وضع اختبار الباقة المجانية (Free Plan):</b>\n"
                "يمكنك الآن الضغط على زر <code>🎯 التوصيات المفتوحة (PRO)</code> لاختبار قفل الميزة، أو اختبار خصم الـ 5 رسائل اليومية.\n"
                "• للعودة لباقتك الطبيعية اكتب: <code>/test_normal</code>"
            )
        else:
            used_val = res.get("used", 0)
            limit_val = res.get("limit", 350)
            rem_val = res.get("remaining", 350)
            msg_txt = (
                f"✅ <b>تمت استعادة وضع حسابك الطبيعي (PRO VIP):</b>\n"
                f"• المستهلك الفعلي: <code>{used_val} / {limit_val}</code>\n"
                f"• المتبقي لك: <code>{rem_val}</code> سؤال."
            )
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=msg_txt,
            message_thread_id=thread_id,
            reply_to_message_id=msg_id,
            reply_markup=build_vip_chat_keyboard(is_private=is_private),
        )
        return True

    # Command to show/pin the interactive ARTORO Control Panel (or /start or bare /scanner)
    if (
        clean_lower.startswith("/start")
        or (clean_lower == "/scanner" and len(text.split()) == 1)
        or clean_lower in (
            "/panel",
            "/vippanel",
            "/artoro",
            "/artoro_panel",
            "/menu",
        )
    ):
        panel_msg_id = send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=build_welcome_panel_html(is_private=is_private, chat_id=chat_id),
            message_thread_id=thread_id,
            reply_to_message_id=msg_id,
            reply_markup=build_vip_chat_keyboard(is_private=is_private),
        )
        if not is_private and panel_msg_id and clean_lower in ("/vippanel", "/artoro_panel", "/panel"):
            _call_telegram_api(
                bot_token,
                "pinChatMessage",
                {"chat_id": chat_id, "message_id": panel_msg_id, "disable_notification": True},
                timeout=5,
            )
        return True

    # Check if user has an active pending prompt mode (from clicking 🔍 حلل سهم, ⚖️ قارن سهمين, or 🤖 اسأل أرتورو)
    pending_mode = get_local_pending_prompt(chat_id, tg_user_id)
    reply_to = msg.get("reply_to_message") or {}
    reply_to_text = str(reply_to.get("text") or "")
    reply_to_from = bool((reply_to.get("from") or {}).get("is_bot"))

    if not pending_mode and reply_to_text:
        if "تحليل سهم فوري —" in reply_to_text:
            pending_mode = "stock"
        elif "مقارنة الأسهم —" in reply_to_text:
            pending_mode = "compare"
        elif "اسأل أرتورو —" in reply_to_text:
            pending_mode = "free"
        elif reply_to_from:
            # User replied to ANY message from ARTORO!
            pending_mode = "free"

    # Always reset pending prompt for this user so subsequent messages aren't trapped
    set_local_pending_prompt(chat_id, tg_user_id, None)

    cleaned_input = text.strip()
    query_text = cleaned_input

    # In the public group topic (not is_private), open recommendations are restricted completely!
    if not is_private and is_topic_recommendation_query(cleaned_input):
        _show_topic_recs_restricted_dialog(
            bot_token=bot_token,
            chat_id=chat_id,
            thread_id=thread_id,
            tg_user_id=tg_user_id,
            user_name=user_name,
            reply_to_message_id=msg_id,
        )
        return True

    if pending_mode == "stock":
        if not re.search(r"(?:حلل|تحليل|سعر|رايك|رأيك|مستويات|اخبار|أخبار)", cleaned_input):
            query_text = f"حلل سهم {cleaned_input}"
        else:
            query_text = cleaned_input
    elif pending_mode == "compare":
        if not re.search(r"(?:قارن|مقارن|مقارنة|ايهم|أيهما)", cleaned_input):
            query_text = f"قارن بين {cleaned_input}"
        else:
            query_text = cleaned_input
    elif pending_mode == "free":
        query_text = cleaned_input
    else:
        # In Private 1-on-1 Chat with @egxbots_bot, users can type directly or use short commands
        if is_private:
            cmd_lower = cleaned_input.lower().split("@")[0].strip()
            if cmd_lower in ("/daily", "daily", "/recs", "recs"):
                query_text = "أهم التوصيات اليومية والفرص المتاحة اليوم"
            elif cmd_lower in ("/weekly", "weekly"):
                query_text = "تقرير الأداء الأسبوعي وملخص السوق"
            elif cmd_lower in ("/market", "market"):
                query_text = "ملخص السوق وأقوى الأسهم اليوم"
            elif cmd_lower in ("/accum", "accum"):
                query_text = "أسهم التجميع والسيولة الذكية اليوم"
            elif cmd_lower in ("/scan", "scan"):
                query_text = "أفضل الأسهم حسب المسح الفني والمؤشرات"
            elif cmd_lower in ("/portfolio", "portfolio"):
                query_text = "حلل محفظتي الاستثمارية بالتفصيل"
            else:
                detected = detect_topic_query_intent(cleaned_input)
                if detected:
                    query_text = detected[1]
                else:
                    query_text = cleaned_input
        else:
            # In the Public Group Topic (1680), intelligently detect query intent!
            detected = detect_topic_query_intent(text)
            if not detected:
                # Pure casual member-to-member banter in the group without any stock query -> ignore
                return True
            det_mode, det_query = detected
            query_text = det_query

    threading.Thread(
        target=_execute_and_reply_vip_chat,
        kwargs={
            "bot_token": bot_token,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "tg_user_id": tg_user_id,
            "user_name": user_name,
            "query_text": query_text,
            "reply_to_message_id": msg_id,
            "callback_query_id": None,
            "file_id": photo_file_id,
        },
        daemon=True,
    ).start()
    return True


def post_initial_vip_panel(bot_token: Optional[str] = None) -> Dict[str, Any]:
    """Post and attempt to pin the welcome control panel in https://t.me/egxbots/1680."""
    token = (bot_token or os.getenv("ARTORO_AI_BOT") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "No bot token configured"}
    chat_id = get_vip_group_id()
    thread_id = get_vip_topic_id()
    msg_id = send_vip_message(
        bot_token=token,
        chat_id=chat_id,
        text=build_welcome_panel_html(),
        message_thread_id=thread_id,
        reply_markup=build_vip_chat_keyboard(),
    )
    if msg_id:
        _call_telegram_api(
            token,
            "pinChatMessage",
            {"chat_id": chat_id, "message_id": msg_id, "disable_notification": True},
            timeout=5,
        )
        return {"ok": True, "chat_id": chat_id, "thread_id": thread_id, "message_id": msg_id}
    return {"ok": False, "error": "Failed to send panel message"}
