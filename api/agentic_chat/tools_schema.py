"""
api/agentic_chat/tools_schema.py
OpenAI/DeepSeek compatible tool schemas for the agentic financial chatbot.
"""

from typing import List, Dict, Any

AGENTIC_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "آخر سعر يومي مخزن مؤرخ ومؤشرات فنية وأسماء الشركات وحالة التوافق مع الشريعة الإسلامية ومؤشر EGX33 وسكورات الذكاء الاصطناعي (KING AI و EGX AI). استخدم لكل سهم مطلوب تحليله أو معرفة سعره الحالي.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "قائمة بأكواد الأسهم مثل ['FWRY', 'COMI', 'TMGH', 'SWDY']"
                    }
                },
                "required": ["symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_levels",
            "description": "جلب مستويات الدعم والمقاومة الأولى والثانية ومناطق الدخول المقترحة ووقف الخسارة (Stop Loss) والمستهدفات الفنية وجني الأرباح (Take Profit) لسهم معين أو قائمة أسهم، مع فحص ما إذا كان السهم يحمل توصية شراء مفتوحة أو إشارة إسكان لحظي.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "قائمة بأكواد الأسهم مثل ['FWRY', 'COMI']"
                    }
                },
                "required": ["symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market",
            "description": "جلب حالة السوق المصري الكاملة: مؤشر EGX30، مؤشر الشريعة EGX33، سيولة السوق، توزيع السيولة، وأعلى الأسهم صعوداً وهبوطاً واستحواذاً على التداول.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "جلب إشارات وتوصيات الشراء الصادرة رسمياً من خوارزميات المنصة تشمل إشارات إسكان الـ 15 دقيقة اللحظية وصفقات السوينغ اليومية والمتوسطة مصنفة حسب الأفق الزمني (لحظية سريعة ⚡ / سوينغ قصير 🎯 / متوسطة 📈). يدعم فلترة الشريعة عبر sharia_only. استدعِ هذه الأداة حتماً عند سؤال المستخدم عن ترشيح سهم أو مضاربة أو فرص شراء أو إشارات اليوم.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "حالة التوصية: open للمفتوحة، closed للمغلقة، all للكل"
                    },
                    "timeframe": {
                        "type": "string",
                        "enum": ["this_week", "last_week", "this_month", "last_month", "last_30_days", "all"],
                        "description": "الفترة الزمنية المطلوبة"
                    },
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "رموز الأسهم لتصفية توصياتها"
                    },
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية للأسهم المتوافقة مع الشريعة الإسلامية ومؤشر EGX33"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "الحد الأقصى للتوصيات المعروضة"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_scan",
            "description": "مسح فني للسوق واستخراج أفضل الأسهم بناءً على معايير فنية محددة (أقوى زخم وسيولة، ذروة البيع RSI، اختراق حجم، التقاطع الذهبي MACD، إلخ). يدعم فلترة الشريعة عبر sharia_only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preset": {
                        "type": "string",
                        "enum": ["momentum_and_volume", "top_gainers", "top_losers", "rsi_oversold", "macd_cross", "smart_money_flow"],
                        "description": "قالب المسح الفني المطلوب"
                    },
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية للأسهم المتوافقة مع الشريعة"
                    }
                },
                "required": ["preset"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_accumulation_stocks",
            "description": "جلب الأسهم التي تمر بمرحلة تجميع مؤسسي وفق منهجية وايكوف (Wyckoff Accumulation) وتدفق سيولة ذكية. يدعم فلترة الشريعة عبر sharia_only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية للأسهم المتوافقة مع الشريعة"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "جلب عناوين الأخبار الجوهرية الموثقة والإفصاحات الحديثة لسهم محدد أو لأخبار السوق العامة.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "أكواد الأسهم المطلوبة، أو اتركها فارغة لأخبار السوق العامة"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_comparison",
            "description": "مقارنة فنية مباشرة بين سهمين أو أكثر من حيث السعر، الزخم (RSI)، السيولة، ونماذج الذكاء الاصطناعي.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "أكواد الأسهم المراد مقارنتها، مثل ['ETEL', 'COMI']"
                    }
                },
                "required": ["symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fair_value",
            "description": "حساب واستخراج السعر العادل ومؤشر الرخص لسهم أو أكثر من البورصة المصرية، أو استخراج أرخص الأسهم المقومة بأقل من قيمتها العادلة في السوق ككل.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "قائمة بأكواد الأسهم"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["screen_undervalued", "screen_overvalued", "specific_stocks"],
                        "description": "وضع الفحص: screen_undervalued لأرخص الأسهم في السوق، screen_overvalued للمتضخمة، أو specific_stocks لأسهم محددة"
                    },
                    "sharia_only": {
                        "type": "boolean",
                        "description": "تصفية حصرية لأسهم الشريعة EGX33"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "الحد الأقصى لعدد النتائج"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sharia_cleanser",
            "description": "فحص التوافق الشرعي للأسهم وفق مؤشر الشريعة الرسمي للبورصة المصرية (EGX33 Shariah) المعتمد من الرقابة المالية، وحساب نسبة ومبلغ تطهير الكوبونات والتوزيعات النقدية وزكاة الأسهم.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "كود السهم مثل ABUK أو ISPH أو COMI"
                    },
                    "shares_count": {
                        "type": "number",
                        "description": "عدد الأسهم المملوكة للمستخدم لحساب مبلغ التطهير أو الزكاة"
                    },
                    "coupon_per_share": {
                        "type": "number",
                        "description": "قيمة الكوبون أو التوزيع النقدي بالجنيه للسهم الواحد"
                    },
                    "purification_rate_pct": {
                        "type": "number",
                        "description": "نسبة التطهير المئوية % (اختياري)"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_traps",
            "description": "كاشف المصائد السعرية والانعكاسات الحية بعد إغلاق الجلسة: مصيدة الدببة والكسر الوهمي الارتدادي (Bear Trap / Spring) ومصيدة الثيران والاختراق الكاذب للتصريف (Bull Trap / Upthrust).",
            "parameters": {
                "type": "object",
                "properties": {
                    "trap_type": {
                        "type": "string",
                        "enum": ["all", "BEAR_TRAP", "BULL_TRAP"],
                        "description": "نوع المصيدة: BEAR_TRAP أو BULL_TRAP أو all"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_disclosures",
            "description": "جلب إفصاحات البورصة المصرية المخزنة (تعاملات الداخليين، كبار المساهمين، قرارات مجلس الإدارة) مع رابط المستند الرسمي.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "كود السهم"
                    },
                    "disclosure_type": {
                        "type": "string",
                        "enum": ["all", "insider_trading", "major_shareholders", "board_resolution", "material_event"],
                        "description": "نوع الإفصاح"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "الحد الأقصى"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_portfolio",
            "description": "عرض أو تسجيل أو تحديث مراكز محفظة المستخدم الاستثمارية في قاعدة البيانات.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["view", "add", "update", "remove", "sell"],
                        "description": "نوع العملية"
                    },
                    "symbol": {
                        "type": "string",
                        "description": "كود السهم"
                    },
                    "quantity": {
                        "type": "number",
                        "description": "عدد الأسهم"
                    },
                    "price": {
                        "type": "number",
                        "description": "سعر الشراء أو البيع"
                    }
                },
                "required": ["operation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_position",
            "description": "حساب مركز مؤقت دون حفظ في المحفظة (حساب القيمة السوقية والتكلفة والأرباح والخسائر).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "quantity": {"type": "number"},
                    "entry_price": {"type": "number"},
                    "total_cost": {"type": "number"}
                },
                "required": ["symbol"]
            }
        }
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
                }
            }
        }
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
                }
            }
        }
    }
]
