"""
api/gcc_metals_sync.py — UAE (DFM & ADX), Qatar (QSE), and Gold & Silver (COMMODITIES) Sync.

Stores all market data in SAUDI_SUPABASE using the exact Saudi market architecture:
1. `stocks` (on_conflict="symbol,exchange")
2. `stock_technical_indicators` (latest indicators per symbol, on_conflict="symbol,exchange")
3. `stock_prices` (recent 260 trading days for fast chatbot & chart queries)
4. `market_index` (equal-weight index per exchange, on_conflict="exchange,date")
5. Supabase Storage `market-history` bucket:
   - `prices/{EXCHANGE}/symbols/{SYMBOL}.json.gz` (full per-symbol history)
   - `prices/{EXCHANGE}/stock_prices.json.gz` (combined exchange archive)
   - `prices/{EXCHANGE}/metadata.json`
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

from api.stock_ai import add_technical_indicators

STORAGE_BUCKET = "market-history"
DB_RECENT_DAYS_LIMIT = 260

# (symbol, exchange, country, currency, yahoo_ticker, tv_symbol, tv_exchange, name_en, name_ar, sector)
InstrumentDef = Tuple[str, str, str, str, Optional[str], str, str, str, str, str]

GCC_AND_METALS_UNIVERSE: List[InstrumentDef] = [
    # ================= COMMODITIES (Gold & Silver) =================
    ("XAUUSD", "COMMODITIES", "Global", "USD", "GC=F", "GOLD", "TVC", "Gold Spot / Futures (XAU/USD)", "الذهب (أونصة عالمية)", "Precious Metals"),
    ("XAGUSD", "COMMODITIES", "Global", "USD", "SI=F", "SILVER", "TVC", "Silver Spot / Futures (XAG/USD)", "الفضة (أونصة عالمية)", "Precious Metals"),

    # ================= DFM (Dubai Financial Market) =================
    ("EMAAR", "DFM", "UAE", "AED", "EMAAR.AE", "EMAAR", "DFM", "Emaar Properties", "إعمار العقارية", "Real Estate"),
    ("EMAARDEV", "DFM", "UAE", "AED", "EMAARDEV.AE", "EMAARDEV", "DFM", "Emaar Development", "إعمار للتطوير", "Real Estate"),
    ("EMIRATESNBD", "DFM", "UAE", "AED", "EMIRATESNBD.AE", "EMIRATESNBD", "DFM", "Emirates NBD", "بنك الإمارات دبي الوطني", "Banks"),
    ("DIB", "DFM", "UAE", "AED", "DIB.AE", "DIB", "DFM", "Dubai Islamic Bank", "بنك دبي الإسلامي", "Banks"),
    ("DEWA", "DFM", "UAE", "AED", "DEWA.AE", "DEWA", "DFM", "Dubai Electricity & Water Authority", "هيئة كهرباء ومياه دبي (ديوا)", "Utilities"),
    ("SALIK", "DFM", "UAE", "AED", "SALIK.AE", "SALIK", "DFM", "Salik Company", "سالك", "Transportation"),
    ("PARKIN", "DFM", "UAE", "AED", "PARKIN.AE", "PARKIN", "DFM", "Parkin Company", "باركن", "Transportation"),
    ("AIRARABIA", "DFM", "UAE", "AED", "AIRARABIA.AE", "AIRARABIA", "DFM", "Air Arabia", "العربية للطيران", "Transportation"),
    ("TALABAT", "DFM", "UAE", "AED", "TALABAT.AE", "TALABAT", "DFM", "Talabat Holding", "طلبات", "Technology"),
    ("ARMX", "DFM", "UAE", "AED", "ARMX.AE", "ARMX", "DFM", "Aramex", "أرامكس", "Transportation"),
    ("DIC", "DFM", "UAE", "AED", "DIC.AE", "DIC", "DFM", "Dubai Investments", "دبي للاستثمار", "Financial Services"),
    ("DFM", "DFM", "UAE", "AED", "DFM.AE", "DFM", "DFM", "Dubai Financial Market", "سوق دبي المالي", "Financial Services"),
    ("DU", "DFM", "UAE", "AED", "DU.AE", "DU", "DFM", "Emirates Integrated Telecommunications (du)", "دو للاتصالات", "Telecom"),
    ("TECOM", "DFM", "UAE", "AED", "TECOM.AE", "TECOM", "DFM", "TECOM Group", "مجموعة تيكوم", "Real Estate"),
    ("EMPOWER", "DFM", "UAE", "AED", "EMPOWER.AE", "EMPOWER", "DFM", "Emirates Central Cooling (Empower)", "إمباور للتبريد", "Utilities"),
    ("SPINNEYS", "DFM", "UAE", "AED", "SPINNEYS.AE", "SPINNEYS", "DFM", "Spinneys 1961 Holding", "سبينيس", "Consumer"),
    ("TAALEEM", "DFM", "UAE", "AED", "TAALEEM.AE", "TAALEEM", "DFM", "Taaleem Holdings", "تعليم القابضة", "Consumer"),
    ("AMANAT", "DFM", "UAE", "AED", "AMANAT.AE", "AMANAT", "DFM", "Amanat Holdings", "أمانات القابضة", "Healthcare"),
    ("GFH", "DFM", "UAE", "AED", "GFH.AE", "GFH", "DFM", "GFH Financial Group", "مجموعة جي إف إتش المالية", "Financial Services"),
    ("SHUAA", "DFM", "UAE", "AED", "SHUAA.AE", "SHUAA", "DFM", "SHUAA Capital", "شعاع كابيتال", "Financial Services"),
    ("DEYAAR", "DFM", "UAE", "AED", "DEYAAR.AE", "DEYAAR", "DFM", "Deyaar Development", "ديار للتطوير", "Real Estate"),
    ("UPP", "DFM", "UAE", "AED", "UPP.AE", "UPP", "DFM", "Union Properties", "الاتحاد العقارية", "Real Estate"),
    ("TABREED", "DFM", "UAE", "AED", "TABREED.AE", "TABREED", "DFM", "National Central Cooling (Tabreed)", "تبريد", "Utilities"),
    ("CBD", "DFM", "UAE", "AED", "CBD.AE", "CBD", "DFM", "Commercial Bank of Dubai", "بنك دبي التجاري", "Banks"),
    ("AJMANBANK", "DFM", "UAE", "AED", "AJMANBANK.AE", "AJMANBANK", "DFM", "Ajman Bank", "مصرف عجمان", "Banks"),
    ("AMLAK", "DFM", "UAE", "AED", "AMLAK.AE", "AMLAK", "DFM", "Amlak Finance", "أملاك للتمويل", "Financial Services"),
    ("ALANSARI", "DFM", "UAE", "AED", "ALANSARI.AE", "ALANSARI", "DFM", "Al Ansari Financial Services", "الأنصاري للخدمات المالية", "Financial Services"),
    ("DTC", "DFM", "UAE", "AED", "DTC.AE", "DTC", "DFM", "Dubai Taxi Company", "تاكسي دبي", "Transportation"),
    ("AMCREIT", "DFM", "UAE", "AED", None, "AMCREIT", "DFM", "Al Mal Capital REIT", "المال كابيتال ريت", "Real Estate"),
    ("ERC", "DFM", "UAE", "AED", "ERC.AE", "ERC", "DFM", "Emirates Refreshments", "الإمارات للمرطبات", "Consumer"),
    ("DSI", "DFM", "UAE", "AED", "DSI.AE", "DSI", "DFM", "Drake & Scull International", "دريك آند سكل", "Industrials"),
    ("SALAMA", "DFM", "UAE", "AED", "SALAMA.AE", "SALAMA", "DFM", "Islamic Arab Insurance (Salama)", "سلامة للتأمين", "Insurance"),
    ("SUKOON", "DFM", "UAE", "AED", "SUKOON.AE", "SUKOON", "DFM", "Sukoon Insurance", "سكون للتأمين", "Insurance"),

    # ================= ADX (Abu Dhabi Securities Exchange) =================
    ("IHC", "ADX", "UAE", "AED", None, "IHC", "ADX", "International Holding Company", "العالمية القابضة", "Conglomerates"),
    ("ALDAR", "ADX", "UAE", "AED", None, "ALDAR", "ADX", "Aldar Properties", "الدار العقارية", "Real Estate"),
    ("FAB", "ADX", "UAE", "AED", None, "FAB", "ADX", "First Abu Dhabi Bank", "بنك أبوظبي الأول", "Banks"),
    ("ADIB", "ADX", "UAE", "AED", None, "ADIB", "ADX", "Abu Dhabi Islamic Bank", "مصرف أبوظبي الإسلامي", "Banks"),
    ("ADCB", "ADX", "UAE", "AED", None, "ADCB", "ADX", "Abu Dhabi Commercial Bank", "بنك أبوظبي التجاري", "Banks"),
    ("EAND", "ADX", "UAE", "AED", None, "EAND", "ADX", "e& (Etisalat)", "اتصالات (e&)", "Telecom"),
    ("ADNOCGAS", "ADX", "UAE", "AED", None, "ADNOCGAS", "ADX", "ADNOC Gas", "أدنوك للغاز", "Energy"),
    ("ADNOCDIST", "ADX", "UAE", "AED", None, "ADNOCDIST", "ADX", "ADNOC Distribution", "أدنوك للتوزيع", "Energy"),
    ("ADNOCDRILL", "ADX", "UAE", "AED", None, "ADNOCDRILL", "ADX", "ADNOC Drilling", "أدنوك للحفر", "Energy"),
    ("ADNOCLS", "ADX", "UAE", "AED", None, "ADNOCLS", "ADX", "ADNOC Logistics & Services", "أدنوك للإمداد والخدمات", "Transportation"),
    ("FERTIGLBE", "ADX", "UAE", "AED", None, "FERTIGLBE", "ADX", "Fertiglobe", "فيرتيغلوب", "Materials"),
    ("BOROUGE", "ADX", "UAE", "AED", None, "BOROUGE", "ADX", "Borouge", "بروج", "Materials"),
    ("ALPHADHABI", "ADX", "UAE", "AED", None, "ALPHADHABI", "ADX", "Alpha Dhabi Holding", "ألفا ظبي القابضة", "Conglomerates"),
    ("MULTIPLY", "ADX", "UAE", "AED", None, "MULTIPLY", "ADX", "Multiply Group", "مجموعة ملتيبلاي", "Conglomerates"),
    ("DANA", "ADX", "UAE", "AED", None, "DANA", "ADX", "Dana Gas", "دانة غاز", "Energy"),
    ("TAQA", "ADX", "UAE", "AED", None, "TAQA", "ADX", "Abu Dhabi National Energy (TAQA)", "طاقة أبوظبي", "Utilities"),
    ("PRESIGHT", "ADX", "UAE", "AED", None, "PRESIGHT", "ADX", "Presight AI Holding", "بريسايت للذكاء الاصطناعي", "Technology"),
    ("SPACE42", "ADX", "UAE", "AED", None, "SPACE42", "ADX", "Space42", "سبيس 42", "Technology"),
    ("NMDC", "ADX", "UAE", "AED", None, "NMDC", "ADX", "NMDC Group", "الجرافات البحرية الوطنية", "Industrials"),
    ("NMDCENR", "ADX", "UAE", "AED", None, "NMDCENR", "ADX", "NMDC Energy", "إن إم دي سي إنيرجي", "Energy"),
    ("BURJEEL", "ADX", "UAE", "AED", None, "BURJEEL", "ADX", "Burjeel Holdings", "برجيل القابضة", "Healthcare"),
    ("PUREHEALTH", "ADX", "UAE", "AED", None, "PUREHEALTH", "ADX", "PureHealth Holding", "بيور هيلث", "Healthcare"),
    ("MODON", "ADX", "UAE", "AED", None, "MODON", "ADX", "Modon Holding", "مدن القابضة", "Real Estate"),
    ("PHOENIX", "ADX", "UAE", "AED", None, "PHOENIX", "ADX", "Phoenix Group", "مجموعة فينيكس", "Technology"),
    ("AGTHIA", "ADX", "UAE", "AED", None, "AGTHIA", "ADX", "Agthia Group", "مجموعة أغذية", "Consumer"),
    ("ASM", "ADX", "UAE", "AED", None, "ASM", "ADX", "Al Seer Marine", "السير للمعدات البحرية", "Industrials"),
    ("ESG", "ADX", "UAE", "AED", None, "ESG", "ADX", "Emirates Stallions Group", "إي إس جي ستاليونز", "Real Estate"),
    ("PALMS", "ADX", "UAE", "AED", None, "PALMS", "ADX", "Palms Sports", "بالمز الرياضية", "Consumer"),
    ("LULU", "ADX", "UAE", "AED", None, "LULU", "ADX", "Lulu Retail Holdings", "لولو للتجزئة", "Consumer"),
    ("ADPORTS", "ADX", "UAE", "AED", None, "ADPORTS", "ADX", "AD Ports Group", "مجموعة موانئ أبوظبي", "Transportation"),
    ("RAKBANK", "ADX", "UAE", "AED", None, "RAKBANK", "ADX", "RAKBank", "بنك رأس الخيمة الوطني", "Banks"),
    ("SIB", "ADX", "UAE", "AED", None, "SIB", "ADX", "Sharjah Islamic Bank", "مصرف الشارقة الإسلامي", "Banks"),
    ("BOS", "ADX", "UAE", "AED", None, "BOS", "ADX", "Bank of Sharjah", "بنك الشارقة", "Banks"),
    ("DRIVE", "ADX", "UAE", "AED", None, "DRIVE", "ADX", "Emirates Driving Company", "الإمارات لتعليم قيادة السيارات", "Consumer"),
    ("RAKPROP", "ADX", "UAE", "AED", None, "RAKPROP", "ADX", "RAK Properties", "رأس الخيمة العقارية", "Real Estate"),
    ("ESHRAQ", "ADX", "UAE", "AED", None, "ESHRAQ", "ADX", "Eshraq Investments", "إشراق للاستثمار", "Real Estate"),
    ("WAHA", "ADX", "UAE", "AED", None, "WAHA", "ADX", "Waha Capital", "الواحة كابيتال", "Financial Services"),
    ("YAHSAT", "ADX", "UAE", "AED", None, "ALPHADATA", "ADX", "Alpha Data", "ألفا داتا", "Technology"),
    ("ADNH", "ADX", "UAE", "AED", None, "ADNH", "ADX", "Abu Dhabi National Hotels", "أبوظبي الوطنية للفنادق", "Consumer"),
    ("RAKCER", "ADX", "UAE", "AED", None, "RAKCER", "ADX", "RAK Ceramics", "سيراميك رأس الخيمة", "Materials"),

    # ================= QSE (Qatar Stock Exchange) =================
    ("QNBK", "QSE", "Qatar", "QAR", "QNBK.QA", "QNBK", "QSE", "Qatar National Bank (QNB)", "بنك قطر الوطني", "Banks"),
    ("QIBK", "QSE", "Qatar", "QAR", "QIBK.QA", "QIBK", "QSE", "Qatar Islamic Bank", "مصرف قطر الإسلامي", "Banks"),
    ("CBQK", "QSE", "Qatar", "QAR", "CBQK.QA", "CBQK", "QSE", "Commercial Bank of Qatar", "البنك التجاري القطري", "Banks"),
    ("MARK", "QSE", "Qatar", "QAR", "MARK.QA", "MARK", "QSE", "Masraf Al Rayan", "مصرف الريان", "Banks"),
    ("QIIK", "QSE", "Qatar", "QAR", "QIIK.QA", "QIIK", "QSE", "Qatar International Islamic Bank", "الدولي الإسلامي", "Banks"),
    ("ABQK", "QSE", "Qatar", "QAR", "ABQK.QA", "ABQK", "QSE", "Ahli Bank Qatar", "البنك الأهلي القطري", "Banks"),
    ("DHBK", "QSE", "Qatar", "QAR", "DHBK.QA", "DHBK", "QSE", "Doha Bank", "بنك الدوحة", "Banks"),
    ("QFBQ", "QSE", "Qatar", "QAR", "QFBQ.QA", "QFBQ", "QSE", "Lesha Bank", "بنك لشا", "Banks"),
    ("DUBK", "QSE", "Qatar", "QAR", "DUBK.QA", "DUBK", "QSE", "Dukhan Bank", "بنك دخان", "Banks"),
    ("IQCD", "QSE", "Qatar", "QAR", "IQCD.QA", "IQCD", "QSE", "Industries Qatar", "صناعات قطر", "Industrials"),
    ("MPHC", "QSE", "Qatar", "QAR", "MPHC.QA", "MPHC", "QSE", "Mesaieed Petrochemical", "مسيعيد للبتروكيماويات", "Materials"),
    ("QGTS", "QSE", "Qatar", "QAR", "QGTS.QA", "QGTS", "QSE", "Qatar Gas Transport (Nakilat)", "ناقلات", "Transportation"),
    ("ORDS", "QSE", "Qatar", "QAR", "ORDS.QA", "ORDS", "QSE", "Ooredoo", "أوريدو", "Telecom"),
    ("VFQS", "QSE", "Qatar", "QAR", "VFQS.QA", "VFQS", "QSE", "Vodafone Qatar", "فودافون قطر", "Telecom"),
    ("BRES", "QSE", "Qatar", "QAR", "BRES.QA", "BRES", "QSE", "Barwa Real Estate", "بروة العقارية", "Real Estate"),
    ("UDCD", "QSE", "Qatar", "QAR", "UDCD.QA", "UDCD", "QSE", "United Development Company", "المتحدة للتنمية", "Real Estate"),
    ("ERES", "QSE", "Qatar", "QAR", "ERES.QA", "ERES", "QSE", "Ezdan Holding Group", "إزدان القابضة", "Real Estate"),
    ("MRDS", "QSE", "Qatar", "QAR", "MRDS.QA", "MRDS", "QSE", "Mazaya Real Estate", "مزايا للتطوير العقاري", "Real Estate"),
    ("MERS", "QSE", "Qatar", "QAR", "MERS.QA", "MERS", "QSE", "Al Meera Consumer Goods", "الميرة للمواد الاستهلاكية", "Consumer"),
    ("QGMD", "QSE", "Qatar", "QAR", "QGMD.QA", "QGMD", "QSE", "Qatari German Medical Devices", "القطرية الألمانية للمستلزمات الطبية", "Healthcare"),
    ("MCGS", "QSE", "Qatar", "QAR", "MCGS.QA", "MCGS", "QSE", "Medicare Group", "الرعاية الطبية", "Healthcare"),
    ("GWCS", "QSE", "Qatar", "QAR", "GWCS.QA", "GWCS", "QSE", "Gulf Warehousing Company", "مخازن الخليج", "Transportation"),
    ("QNNS", "QSE", "Qatar", "QAR", "QNNS.QA", "QNNS", "QSE", "Qatar Navigation (Milaha)", "ملاحة", "Transportation"),
    ("GISS", "QSE", "Qatar", "QAR", "GISS.QA", "GISS", "QSE", "Gulf International Services", "الخليج الدولية", "Energy"),
    ("NLCS", "QSE", "Qatar", "QAR", "NLCS.QA", "NLCS", "QSE", "National Leasing (Alijarah)", "الإجارة القابضة", "Financial Services"),
    ("SIIS", "QSE", "Qatar", "QAR", "SIIS.QA", "SIIS", "QSE", "Salam International", "السلام العالمية", "Conglomerates"),
    ("IHGS", "QSE", "Qatar", "QAR", "IHGS.QA", "IHGS", "QSE", "Inma Holding", "إنماء القابضة", "Financial Services"),
    ("AKHI", "QSE", "Qatar", "QAR", "AKHI.QA", "AKHI", "QSE", "Al Khaleej Takaful", "الخليج التكافلي", "Insurance"),
    ("QGRI", "QSE", "Qatar", "QAR", "QGRI.QA", "QGRI", "QSE", "Qatar General Insurance", "القطرية العامة للتأمين", "Insurance"),
    ("QATI", "QSE", "Qatar", "QAR", "QATI.QA", "QATI", "QSE", "Qatar Insurance Company", "قطر للتأمين", "Insurance"),
    ("DOHI", "QSE", "Qatar", "QAR", "DOHI.QA", "DOHI", "QSE", "Doha Insurance Group", "مجموعة الدوحة للتأمين", "Insurance"),
    ("QLMI", "QSE", "Qatar", "QAR", "QLMI.QA", "QLMI", "QSE", "QLM Life & Medical Insurance", "كيو إل إم للتأمين", "Insurance"),
    ("BEEMA", "QSE", "Qatar", "QAR", "BEMA.QA", "BEMA", "QSE", "Damaan Islamic Insurance (Beema)", "بيمة للتأمين", "Insurance"),
    ("DBIS", "QSE", "Qatar", "QAR", "DBIS.QA", "DBIS", "QSE", "Dlala Brokerage", "دلالة للوساطة", "Financial Services"),
    ("ZHCD", "QSE", "Qatar", "QAR", "ZHCD.QA", "ZHCD", "QSE", "Zad Holding", "زاد القابضة", "Consumer"),
    ("WDAM", "QSE", "Qatar", "QAR", "WDAM.QA", "WDAM", "QSE", "Widam Food", "ودام الغذائية", "Consumer"),
    ("BLDN", "QSE", "Qatar", "QAR", "BLDN.QA", "BLDN", "QSE", "Baladna", "بلدنا", "Consumer"),
    ("MCCS", "QSE", "Qatar", "QAR", "MCCS.QA", "MCCS", "QSE", "Mannai Corporation", "مجمع شركات المناعي", "Technology"),
    ("QCFS", "QSE", "Qatar", "QAR", "QCFS.QA", "QCFS", "QSE", "Qatar Cinema & Film", "قطر للسينما", "Consumer"),
    ("QAMC", "QSE", "Qatar", "QAR", "QAMC.QA", "QAMC", "QSE", "Qatar Aluminium (Qamco)", "قامكو", "Materials"),
    ("QEWS", "QSE", "Qatar", "QAR", "QEWS.QA", "QEWS", "QSE", "Qatar Electricity & Water", "كهرباء وماء قطر", "Utilities"),
    ("AHCS", "QSE", "Qatar", "QAR", "AHCS.QA", "AHCS", "QSE", "Aamal Company", "أعمال", "Conglomerates"),
    ("QIGD", "QSE", "Qatar", "QAR", "QIGD.QA", "QIGD", "QSE", "Qatari Investors Group", "مجموعة المستثمرين القطريين", "Industrials"),
    ("QOIS", "QSE", "Qatar", "QAR", "QOIS.QA", "QOIS", "QSE", "Qatar Oman Investment", "قطر وعمان للاستثمار", "Financial Services"),
    ("QNCD", "QSE", "Qatar", "QAR", "QNCD.QA", "QNCD", "QSE", "Qatar National Cement", "قطر الوطنية لصناعة الأسمنت", "Materials"),
    ("MEZA", "QSE", "Qatar", "QAR", "MEZA.QA", "MEZA", "QSE", "Meeza QSTP", "ميزة", "Technology"),
    ("FALH", "QSE", "Qatar", "QAR", "FALH.QA", "FALH", "QSE", "Al Faleh Educational Holding", "الفالح التعليمية", "Consumer"),
    ("MKDM", "QSE", "Qatar", "QAR", "MKDM.QA", "MKDM", "QSE", "Mekdam Holding Group", "مقدام القابضة", "Technology"),
    ("QFLS", "QSE", "Qatar", "QAR", "QFLS.QA", "QFLS", "QSE", "Qatar Fuel (Woqod)", "وقود", "Energy"),
    ("QIMD", "QSE", "Qatar", "QAR", "QIMD.QA", "QIMD", "QSE", "Qatar Industrial Manufacturing", "التحويلية", "Industrials"),
]


def _get_saudi_supabase() -> Client:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(repo_root, ".env"))
    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Missing SAUDI_SUPABASE_URL / SAUDI_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def _clean_float(val: Any) -> Optional[float]:
    try:
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _clean_int(val: Any) -> int:
    num = _clean_float(val)
    if num is None or num < 0:
        return 0
    return int(round(num))


def _df_to_bars(df: pd.DataFrame, symbol: str, exchange: str, source: str) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    bars: List[Dict[str, Any]] = []
    col_map = {str(c).lower(): c for c in df.columns}
    c_close = col_map.get("close")
    c_open = col_map.get("open")
    c_high = col_map.get("high")
    c_low = col_map.get("low")
    c_vol = col_map.get("volume")
    if not c_close:
        return []

    seen_dates = set()
    for idx, row in df.iterrows():
        close = _clean_float(row.get(c_close))
        if close is None or close <= 0:
            continue
        date_val = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        if date_val in seen_dates or date_val < "2010-01-01":
            continue
        seen_dates.add(date_val)
        open_p = _clean_float(row.get(c_open)) if c_open else None
        high_p = _clean_float(row.get(c_high)) if c_high else None
        low_p = _clean_float(row.get(c_low)) if c_low else None
        open_p = open_p if (open_p and open_p > 0) else close
        high_p = max(high_p or close, close, open_p)
        low_p = min(low_p if (low_p and low_p > 0) else close, close, open_p)
        vol = _clean_int(row.get(c_vol)) if c_vol else 0
        bars.append({
            "symbol": symbol,
            "exchange": exchange,
            "date": date_val,
            "open": round(open_p, 4),
            "high": round(high_p, 4),
            "low": round(low_p, 4),
            "close": round(close, 4),
            "volume": float(vol),
            "source": source,
        })
    bars.sort(key=lambda b: b["date"])
    return bars


def _fetch_yahoo_bulk(
    items: List[InstrumentDef],
    period: str = "max",
) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    import yfinance as yf

    out: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    yf_items = [it for it in items if it[4]]
    chunk_size = 40
    for i in range(0, len(yf_items), chunk_size):
        chunk = yf_items[i : i + chunk_size]
        tickers = [it[4] for it in chunk if it[4]]
        try:
            df = yf.download(
                tickers=tickers if len(tickers) > 1 else tickers[0],
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if df is None or df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                lvl0 = set(df.columns.get_level_values(0))
                for it in chunk:
                    yt = it[4]
                    if yt and yt in lvl0:
                        bars = _df_to_bars(df[yt], it[0], it[1], "yahoo")
                        if bars:
                            out[(it[0], it[1])] = bars
            elif len(chunk) == 1:
                it = chunk[0]
                bars = _df_to_bars(df, it[0], it[1], "yahoo")
                if bars:
                    out[(it[0], it[1])] = bars
        except Exception as exc:
            print(f"[GCC-SYNC] Yahoo chunk {i} failed: {exc}")
    return out


def _fetch_tv_missing(
    items: List[InstrumentDef],
    n_bars: int = 5000,
    workers: int = 4,
) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    if not items:
        return {}
    try:
        from tvDatafeed import Interval, TvDatafeed  # type: ignore
    except Exception:
        return {}

    tl = threading.local()

    def _get_tv() -> TvDatafeed:
        tv = getattr(tl, "tv", None)
        if tv is None:
            tv = TvDatafeed()
            tl.tv = tv
        return tv

    def _fetch_one(it: InstrumentDef) -> Tuple[Tuple[str, str], List[Dict[str, Any]]]:
        sym, exch, _, _, _, tv_sym, tv_exch, _, _, _ = it
        for attempt in range(3):
            try:
                df = _get_tv().get_hist(symbol=tv_sym, exchange=tv_exch, interval=Interval.in_daily, n_bars=n_bars)
                if df is not None and not df.empty:
                    time.sleep(0.2)
                    return (sym, exch), _df_to_bars(df, sym, exch, "tradingview")
                tl.tv = TvDatafeed()
                time.sleep(0.6 * (attempt + 1))
            except Exception:
                tl.tv = TvDatafeed()
                time.sleep(0.8 * (attempt + 1))
        return (sym, exch), []

    out: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=1) as pool:
        futs = [pool.submit(_fetch_one, it) for it in items]
        for fut in as_completed(futs):
            k, bars = fut.result()
            if bars:
                out[k] = bars
    return out


def _upload_storage_json_gz(sb: Client, path: str, payload: Any) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=6)
    sb.storage.from_(STORAGE_BUCKET).upload(
        path,
        gz,
        {"content-type": "application/gzip", "upsert": "true"},
    )


def _upload_storage_json(sb: Client, path: str, payload: Any) -> None:
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    sb.storage.from_(STORAGE_BUCKET).upload(
        path,
        raw,
        {"content-type": "application/json", "upsert": "true"},
    )


def _merge_with_existing_storage_bars_checked(
    sb: Client,
    path: str,
    new_bars: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool]:
    merged: Dict[str, Dict[str, Any]] = {}
    old_map: Dict[str, Dict[str, Any]] = {}
    try:
        raw = sb.storage.from_(STORAGE_BUCKET).download(path)
        old_bars = json.loads(gzip.decompress(raw))
        if isinstance(old_bars, list):
            for b in old_bars:
                if isinstance(b, dict) and b.get("date"):
                    d_key = str(b["date"])[:10]
                    merged[d_key] = b
                    old_map[d_key] = b
    except Exception:
        pass

    changed = not bool(old_map)
    for b in new_bars:
        d_key = str(b["date"])[:10]
        rec = {
            "symbol": b["symbol"],
            "exchange": b["exchange"],
            "date": b["date"],
            "open": b["open"],
            "high": b["high"],
            "low": b["low"],
            "close": b["close"],
            "volume": b["volume"],
        }
        prev = old_map.get(d_key)
        if prev is None or (
            prev.get("close") != rec["close"]
            or prev.get("volume") != rec["volume"]
            or prev.get("high") != rec["high"]
            or prev.get("low") != rec["low"]
            or prev.get("open") != rec["open"]
        ):
            changed = True
        merged[d_key] = rec
    return [merged[d] for d in sorted(merged.keys())], changed


def _merge_with_existing_storage_bars(sb: Client, path: str, new_bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bars, _ = _merge_with_existing_storage_bars_checked(sb, path, new_bars)
    return bars


def _sync_recent_stock_prices(
    sb: Client,
    exchange: str,
    stock_id_map: Dict[Tuple[str, str], Any],
    bars_by_sym: Dict[str, List[Dict[str, Any]]],
    recent_limit: int = DB_RECENT_DAYS_LIMIT,
) -> int:
    rows: List[Dict[str, Any]] = []
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    for sym, bars in bars_by_sym.items():
        sid = stock_id_map.get((sym, exchange))
        if sid is None:
            continue
        for b in bars[-recent_limit:]:
            rows.append({
                "stock_id": sid,
                "symbol": sym,
                "exchange": exchange,
                "date": b["date"],
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "adjusted_close": b["close"],
                "volume": int(round(b["volume"])),
                "source": b.get("source", "yahoo"),
                "updated_at": now_iso,
            })
    if not rows:
        return 0

    for i in range(0, len(rows), 250):
        sb.table("stock_prices").upsert(
            rows[i : i + 250],
            on_conflict="stock_id,date,source",
        ).execute()
    return len(rows)


def _compute_and_upsert_indicators(
    sb: Client,
    exchange: str,
    bars_by_sym: Dict[str, List[Dict[str, Any]]],
) -> int:
    ind_rows: List[Dict[str, Any]] = []
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    for sym, bars in bars_by_sym.items():
        if len(bars) < 25:
            continue
        df = pd.DataFrame(bars)
        df["Date"] = pd.to_datetime(df["date"])
        df["Open"] = df["open"].astype(float)
        df["High"] = df["high"].astype(float)
        df["Low"] = df["low"].astype(float)
        df["Close"] = df["close"].astype(float)
        df["Volume"] = df["volume"].astype(float)
        try:
            ind_df = add_technical_indicators(df)
        except Exception:
            continue
        if ind_df is None or ind_df.empty:
            continue
        last = ind_df.iloc[-1]
        prev_close = float(ind_df.iloc[-2]["Close"]) if len(ind_df) >= 2 else float(last["Close"])
        cur_close = float(last["Close"])
        chg_pct = ((cur_close - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0

        def _f(col: str) -> Optional[float]:
            v = last.get(col)
            if v is None:
                return None
            try:
                fv = float(v)
                return None if (math.isnan(fv) or math.isinf(fv)) else round(fv, 4)
            except (TypeError, ValueError):
                return None

        vol_val = int(round(float(last.get("Volume") or 0)))
        vol_tail = df["Volume"].tail(20)
        vol_pos = vol_tail[vol_tail > 0]
        vol_sma_fallback = float(vol_pos.mean()) if len(vol_pos) > 0 else 0.0
        vol_sma_f = _f("Vol_SMA20") or _f("Volume_SMA_20") or vol_sma_fallback
        vol_sma = int(round(vol_sma_f))
        r_vol = round(vol_val / vol_sma, 2) if vol_sma > 0 else 1.0
        sma_20_val = _f("SMA_20") or _f("BB_Middle") or round(float(df["Close"].tail(20).mean()), 4)

        ind_rows.append({
            "symbol": sym,
            "exchange": exchange,
            "date": str(bars[-1]["date"])[:10],
            "close": round(cur_close, 4),
            "change_pct": round(chg_pct, 2),
            "volume": vol_val,
            "volume_sma_20": vol_sma,
            "vol_sma20": vol_sma,
            "r_vol": r_vol,
            "rsi_14": _f("RSI"),
            "rsi_9": _f("RSI_9"),
            "ema_20": _f("EMA_20"),
            "ema_50": _f("EMA_50"),
            "ema_200": _f("EMA_200"),
            "sma_20": sma_20_val,
            "sma_50": _f("SMA_50"),
            "sma_200": _f("SMA_200"),
            "macd": _f("MACD"),
            "macd_signal": _f("MACD_Signal"),
            "macd_histogram": _f("MACD_Histogram"),
            "bb_upper": _f("BB_Upper"),
            "bb_middle": _f("BB_Middle"),
            "bb_lower": _f("BB_Lower"),
            "adx_14": _f("ADX_14"),
            "plus_di": _f("Plus_DI"),
            "minus_di": _f("Minus_DI"),
            "atr_14": _f("ATR_14"),
            "stoch_k": _f("STOCH_K"),
            "stoch_d": _f("STOCH_D"),
            "cci_20": _f("CCI_20"),
            "vwap_20": _f("VWAP_20"),
            "momentum_10": _f("Momentum"),
            "roc_12": _f("ROC_12"),
            "cmf_20": _f("CMF_20"),
            "calculated_at": now_iso,
            "updated_at": now_iso,
        })

    for i in range(0, len(ind_rows), 100):
        sb.table("stock_technical_indicators").upsert(ind_rows[i : i + 100], on_conflict="symbol,exchange").execute()
    return len(ind_rows)


def _sync_market_index(
    sb: Client,
    exchange: str,
    bars_by_sym: Dict[str, List[Dict[str, Any]]],
    limit_days: int = DB_RECENT_DAYS_LIMIT,
) -> int:
    by_date: Dict[str, List[float]] = {}
    prev_by_sym: Dict[str, float] = {}
    all_dates = sorted({b["date"] for bars in bars_by_sym.values() for b in bars})
    recent_dates = all_dates[-limit_days:]
    sym_date_close = {
        sym: {b["date"]: float(b["close"]) for b in bars}
        for sym, bars in bars_by_sym.items()
    }
    if not recent_dates:
        return 0

    index_level = 1000.0
    rows: List[Dict[str, Any]] = []
    for d in recent_dates:
        rets: List[float] = []
        for sym, dmap in sym_date_close.items():
            c = dmap.get(d)
            if c is None or c <= 0:
                continue
            prev_c = prev_by_sym.get(sym)
            if prev_c and prev_c > 0:
                r = (c - prev_c) / prev_c
                if abs(r) <= 0.35:
                    rets.append(r)
            prev_by_sym[sym] = c
        avg_ret = float(np.mean(rets)) if rets else 0.0
        index_level = index_level * (1.0 + avg_ret)
        rows.append({
            "exchange": exchange,
            "date": d,
            "close": round(index_level, 2),
            "ret": round(avg_ret, 6),
            "source": "equal_weight",
        })

    for i in range(0, len(rows), 100):
        sb.table("market_index").upsert(rows[i : i + 100], on_conflict="exchange,date").execute()
    return len(rows)


def run_gcc_metals_sync(
    exchanges: Optional[List[str]] = None,
    daily_only: bool = False,
) -> Dict[str, Any]:
    sb = _get_saudi_supabase()
    target_exchanges = {e.upper() for e in exchanges} if exchanges else {"DFM", "ADX", "QSE", "COMMODITIES"}
    items = [it for it in GCC_AND_METALS_UNIVERSE if it[1] in target_exchanges]
    if not items:
        return {"ok": False, "error": "No matching exchanges"}

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    # 1. Upsert stocks registry
    stock_rows = [
        {
            "symbol": it[0],
            "exchange": it[1],
            "country": it[2],
            "currency": it[3],
            "name": it[7],
            "name_ar": it[8],
            "sector": it[9],
            "is_active": True,
            "updated_at": now_iso,
        }
        for it in items
    ]
    for i in range(0, len(stock_rows), 100):
        sb.table("stocks").upsert(stock_rows[i : i + 100], on_conflict="symbol,exchange").execute()

    # Fetch stock_id map
    st_res = (
        sb.table("stocks")
        .select("id,symbol,exchange")
        .in_("exchange", sorted(target_exchanges))
        .limit(1000)
        .execute()
    )
    stock_id_map = {(r["symbol"], r["exchange"]): r["id"] for r in (st_res.data or [])}

    # 2. Fetch OHLCV (Yahoo bulk + TradingView primary/fallback)
    yf_period = "30d" if daily_only else "max"
    tv_bars = 35 if daily_only else 5000

    bars_map = _fetch_yahoo_bulk(items, period=yf_period)
    missing_or_tv = [it for it in items if (it[0], it[1]) not in bars_map]
    if missing_or_tv:
        tv_map = _fetch_tv_missing(missing_or_tv, n_bars=tv_bars, workers=2)
        bars_map.update(tv_map)

    summary: Dict[str, Any] = {}
    recent_db_limit = 15 if daily_only else DB_RECENT_DAYS_LIMIT
    storage_tl = threading.local()

    def _get_worker_sb() -> Client:
        client = getattr(storage_tl, "sb", None)
        if client is None:
            client = _get_saudi_supabase()
            storage_tl.sb = client
        return client

    def _process_symbol(exch: str, it: InstrumentDef) -> Tuple[str, List[Dict[str, Any]], bool]:
        sym = it[0]
        bars = bars_map.get((sym, exch), [])
        if not bars:
            return sym, [], False
        worker_sb = _get_worker_sb()
        sym_path = f"prices/{exch}/symbols/{sym}.json.gz"
        if daily_only:
            full_sym_bars, changed = _merge_with_existing_storage_bars_checked(worker_sb, sym_path, bars)
            if changed:
                _upload_storage_json_gz(worker_sb, sym_path, full_sym_bars)
        else:
            full_sym_bars = [
                {
                    "symbol": sym,
                    "exchange": exch,
                    "date": b["date"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                }
                for b in bars
            ]
            _upload_storage_json_gz(worker_sb, sym_path, full_sym_bars)
            changed = True
        return sym, full_sym_bars, changed

    for exch in sorted(target_exchanges):
        exch_items = [it for it in items if it[1] == exch]
        exch_bars: Dict[str, List[Dict[str, Any]]] = {}
        all_archive_rows: List[Dict[str, Any]] = []
        symbol_files_uploaded = 0

        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = [pool.submit(_process_symbol, exch, it) for it in exch_items]
            for fut in as_completed(futs):
                sym, full_sym_bars, changed = fut.result()
                if not full_sym_bars:
                    continue
                if changed:
                    symbol_files_uploaded += 1
                exch_bars[sym] = full_sym_bars
                all_archive_rows.extend(full_sym_bars)

        if all_archive_rows and (symbol_files_uploaded > 0 or not daily_only):
            _upload_storage_json_gz(sb, f"prices/{exch}/stock_prices.json.gz", all_archive_rows)
            all_dates = [r["date"] for r in all_archive_rows]
            _upload_storage_json(
                sb,
                f"prices/{exch}/metadata.json",
                {
                    "exchange": exch,
                    "rows": len(all_archive_rows),
                    "symbols": len(exch_bars),
                    "first_date": min(all_dates),
                    "last_date": max(all_dates),
                    "published_at": now_iso,
                    "format": "json.gz",
                    "symbol_files": symbol_files_uploaded,
                },
            )

        db_price_rows = _sync_recent_stock_prices(sb, exch, stock_id_map, exch_bars, recent_limit=recent_db_limit)
        ind_count = _compute_and_upsert_indicators(sb, exch, exch_bars)
        idx_count = _sync_market_index(sb, exch, exch_bars)
        summary[exch] = {
            "symbols_synced": len(exch_bars),
            "storage_symbol_files": symbol_files_uploaded,
            "storage_total_rows": len(all_archive_rows),
            "db_recent_price_rows": db_price_rows,
            "indicators_upserted": ind_count,
            "index_rows": idx_count,
        }
        print(f"[GCC-SYNC] {exch}: {summary[exch]}")

    return {"ok": True, "summary": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync UAE (DFM/ADX), Qatar (QSE), and Gold/Silver to SAUDI_SUPABASE")
    parser.add_argument("--exchanges", nargs="+", help="Exchanges to sync (DFM ADX QSE COMMODITIES)")
    parser.add_argument("--daily", action="store_true", help="Incremental daily mode (last 30d merged into Storage)")
    args = parser.parse_args()
    res = run_gcc_metals_sync(exchanges=args.exchanges, daily_only=args.daily)
    print(json.dumps(res, ensure_ascii=False, indent=2))
