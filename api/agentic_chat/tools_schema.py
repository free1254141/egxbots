"""
api/agentic_chat/tools_schema.py
OpenAI/DeepSeek compatible tool schemas for the dual-market (EGX & Saudi TASI) agentic financial chatbot.
"""

from typing import List, Dict, Any

_MARKET_PARAM_SCHEMA: Dict[str, Any] = {
    "type": "string",
    "enum": ["EGX", "TASI"],
    "description": "السوق المطلوب: 'EGX' للبورصة المصرية أو 'TASI' للسوق السعودي (تداول). اتركه فارغاً لاستخدام السوق النشط أو التوجيه التلقائي حسب الرموز.",
}

AGENTIC_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": (
                "جلب أحدث سعر ومؤشرات فنية وأسماء الشركات والتقييم الفني والبيانات الأساسية لسهم أو قائمة أسهم "
                "في البورصة المصرية (EGX، ج.م) أو السوق السعودي تداول (TASI، ر.س) أو كليهما معاً. "
                "يتم التوجيه تلقائياً حسب رمز السهم (أحرف مثل COMI/FWRY لمصر، أو 4 أرقام مثل 2222/1120 للسعودية) أو الاسم العربي (أرامكو، الراجحي، فوري)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "قائمة بأكواد أو أسماء الأسهم مثل ['FWRY', 'COMI', '2222', '1120'] أو ['أرامكو', 'الراجحي', 'فوري']",
                    }
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_levels",
            "description": (
                "جلب مستويات الدعم والمقاومة الأولى والثانية ومناطق الدخول المقترحة ووقف الخسارة (Stop Loss) "
                "والمستهدفات الفنية وجني الأرباح (Take Profit) لسهم معين أو قائمة أسهم في السوق المصري (EGX) أو السعودي (TASI)، "
                "مع فحص وجود توصية شراء مفتوحة."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "قائمة بأكواد الأسهم مثل ['FWRY', 'COMI', '2222', '1120']",
                    }
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market",
            "description": (
                "جلب حالة السوق الكاملة: في البورصة المصرية (EGX30، سيولة السوق، الصاعد والهابط) "
                "أو في السوق السعودي تداول (مؤشر TASI، اتساع السوق، وأعلى الأسهم صعوداً وهبوطاً بالريال السعودي ر.س)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": (
                "جلب إشارات وتوصيات الشراء الصادرة رسمياً من خوارزميات المنصة في السوق المصري (EGX) أو السعودي (TASI)، "
                "تشمل صفقات السوينغ والإشارات اللحظية. يدعم فلترة الشريعة عبر sharia_only واختيار السوق عبر market. "
                "استدعِ هذه الأداة حتماً عند سؤال المستخدم عن ترشيح سهم أو مضاربة أو فرص شراء أو إشارات اليوم."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "حالة التوصية: open للمفتوحة، closed للمغلقة، all للكل",
                    },
                    "timeframe": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "all"],
                        "description": "الفترة الزمنية المطلوبة",
                    },
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "رموز الأسهم لتصفية توصياتها",
                    },
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية للأسهم المتوافقة مع الشريعة الإسلامية",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "الحد الأقصى للتوصيات المعروضة",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_scan",
            "description": (
                "مسح فني للسوق واستخراج أفضل الأسهم بناءً على معايير فنية محددة (أقوى زخم وسيولة، ذروة البيع RSI، "
                "اختراق حجم، التقاطع الذهبي MACD، إلخ) في البورصة المصرية (EGX) أو السوق السعودي تداول (TASI). "
                "يدعم فلترة الشريعة عبر sharia_only وتحديد السوق عبر market."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "preset": {
                        "type": "string",
                        "enum": ["momentum_and_volume", "top_gainers", "top_losers", "rsi_oversold", "macd_cross", "smart_money_flow"],
                        "description": "قالب المسح الفني المطلوب",
                    },
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية للأسهم المتوافقة مع الشريعة",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
                "required": ["preset"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_accumulation_stocks",
            "description": (
                "جلب الأسهم التي تمر بمرحلة تجميع مؤسسي وفق منهجية وايكوف (Wyckoff Accumulation) وتدفق سيولة ذكية (CMF / Volume) "
                "في البورصة المصرية (EGX) أو السوق السعودي (TASI). يدعم فلترة الشريعة وتحديد السوق عبر market."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية للأسهم المتوافقة مع الشريعة",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": (
                "جلب عناوين الأخبار الجوهرية الموثقة والإفصاحات الحديثة لسهم محدد أو لأخبار السوق العامة في EGX أو TASI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "أكواد الأسهم المطلوبة، أو اتركها فارغة لأخبار السوق العامة",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_comparison",
            "description": (
                "مقارنة فنية مباشرة بين سهمين أو أكثر من حيث السعر، العملة، الزخم (RSI)، السيولة، والدعم والمقاومة — "
                "يدعم المقارنة داخل نفس السوق أو بين السوقين معاً (مثل ['2222', 'COMI'] أو ['2222', '1120'] أو ['ETEL', 'COMI'])."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "أكواد أو أسماء الأسهم المراد مقارنتها، مثل ['2222', 'COMI'] أو ['1120', '2010'] أو ['ETEL', 'COMI']",
                    }
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fair_value",
            "description": (
                "حساب واستخراج السعر العادل ومؤشر الرخص لسهم أو أكثر في البورصة المصرية (ج.م) أو السوق السعودي تداول (ر.س)، "
                "أو استخراج أرخص الأسهم المقومة بأقل من قيمتها العادلة في السوق المحدد."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "قائمة بأكواد الأسهم مثل ['COMI', 'FWRY'] أو ['2222', '1120']",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["screen_undervalued", "screen_overvalued", "specific_stocks"],
                        "description": "وضع الفحص: screen_undervalued لأرخص الأسهم في السوق، screen_overvalued للمتضخمة، أو specific_stocks لأسهم محددة",
                    },
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية لأسهم الشريعة",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "الحد الأقصى لعدد النتائج",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sharia_cleanser",
            "description": (
                "فحص التوافق الشرعي للأسهم (مؤشر EGX33 Shariah للبورصة المصرية، وحاسبة التطهير والزكاة للسوق المصري والسوق السعودي تداول)، "
                "وحساب مبلغ تطهير الكوبونات والتوزيعات النقدية وزكاة الأسهم بالعملة المناسبة (ج.م أو ر.س)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "كود السهم مثل ABUK أو COMI (مصر) أو 2222 أو 1120 (السعودية)",
                    },
                    "shares_count": {
                        "type": "number",
                        "description": "عدد الأسهم المملوكة للمستخدم لحساب مبلغ التطهير أو الزكاة",
                    },
                    "coupon_per_share": {
                        "type": "number",
                        "description": "قيمة الكوبون أو التوزيع النقدي للسهم الواحد (ج.م للمصري أو ر.س للسعودي)",
                    },
                    "purification_rate_pct": {
                        "type": "number",
                        "description": "نسبة التطهير المئوية % (اختياري)",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_traps",
            "description": (
                "كاشف المصائد السعرية والانعكاسات الحية بعد إغلاق الجلسة في السوق المصري (EGX) أو السوق السعودي (TASI): "
                "مصيدة الدببة والكسر الوهمي الارتدادي (Bear Trap / Spring) ومصيدة الثيران والاختراق الكاذب للتصريف (Bull Trap / Upthrust)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trap_type": {
                        "type": "string",
                        "enum": ["all", "BEAR_TRAP", "BULL_TRAP"],
                        "description": "نوع المصيدة: BEAR_TRAP أو BULL_TRAP أو all",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disclosures",
            "description": (
                "جلب إفصاحات الشركات المخزنة (تعاملات الداخليين، كبار المساهمين، قرارات مجلس الإدارة) مع رابط المستند الرسمي "
                "في السوق المصري (EGX) أو فحص حالة إفصاحات السوق السعودي (TASI)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "كود السهم مثل COMI أو 2222",
                    },
                    "disclosure_type": {
                        "type": "string",
                        "enum": ["all", "insider_trading", "major_shareholders", "board_resolution", "material_event"],
                        "description": "نوع الإفصاح",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "الحد الأقصى",
                    },
                    "market": dict(_MARKET_PARAM_SCHEMA),
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_portfolio",
            "description": "عرض أو تسجيل أو تحديث مراكز محفظة المستخدم الاستثمارية في قاعدة البيانات (يدعم الأسهم المصرية والسعودية مثل COMI و 2222).",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["view", "add", "update", "remove", "sell"],
                        "description": "نوع العملية",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "كود السهم مثل COMI أو 2222",
                    },
                    "quantity": {
                        "type": "number",
                        "description": "عدد الأسهم",
                    },
                    "price": {
                        "type": "number",
                        "description": "سعر الشراء أو البيع بعملة السهم",
                    },
                },
                "required": ["operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_position",
            "description": "حساب مركز مؤقت دون حفظ في المحفظة (حساب القيمة السوقية والتكلفة والأرباح والخسائر بالجنيه المصري أو الريال السعودي حسب السهم).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "quantity": {"type": "number"},
                    "entry_price": {"type": "number"},
                    "total_cost": {"type": "number"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enable_autonomous_recommendations",
            "description": "تفعيل وضع التوصيات الحرة المستقلة للذكاء الاصطناعي في واجهة الشات بناءً على طلب المستخدم.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disable_autonomous_recommendations",
            "description": "إيقاف وضع التوصيات الحرة المستقلة للذكاء الاصطناعي في واجهة الشات.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"}
                },
            },
        },
    },
]
