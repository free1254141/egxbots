"""
Sharia-compliant stock screening definitions for EGX, Saudi TASI, UAE (DFM/ADX), and Qatar (QSE).
Aligned with the official EGX 33 Shariah Index approved by the Financial Regulatory Authority (FRA)
and GCC AAOIFI / Sharia screening lists.
"""
from typing import Set, Optional, List

from api.saudi_stock_aliases import is_saudi_symbol

SHARIA_COMPLIANT_EGX_SYMBOLS: List[str] = [
    "ISPH", "AMOC", "ICFC", "IFAP", "OCDI", "RMDA", "ACGC", "ARCC", "CIRA",
    "ETRS", "ETEL", "MPCO", "ORWE", "MTIE", "ORAS", "ORHD", "EFIH", "EFID",
    "PHDC", "SAUD", "FAITA", "FAIT", "JUFO", "RACC", "SKPC", "OLFI", "EGAS",
    "LCSW", "TMGH", "MASR", "ATQA", "MCQE", "EGAL", "ADIB", "SWDY", "ABUK", "MFPC"
]

SHARIA_COMPLIANT_TASI_SYMBOLS: List[str] = [
    "1120", "1150", "1140", "1020", "2222", "7010", "2010", "2020", "2280",
    "4013", "1211", "2082", "2083", "4190", "4200", "7020", "7202", "7203",
    "7200", "4001", "4002", "4003", "4004", "4005", "4009", "2270", "2223",
    "2290", "2310", "2330", "3010", "3020", "3030", "3050", "4300", "4090",
    "4100", "4250", "5110", "1322", "1830", "4030", "4260", "4261",
]

SHARIA_COMPLIANT_UAE_SYMBOLS: List[str] = [
    "ADIB", "DIB", "SIB", "AJMANBANK", "GFH", "SALAMA", "SUKOON", "AMLAK",
    "EMAAR", "EMAARDEV", "ALDAR", "ADNOCGAS", "ADNOCDIST", "ADNOCDRILL",
    "ADNOCLS", "ADPORTS", "DEWA", "SALIK", "PARKIN", "TALABAT", "AIRARABIA",
    "ARMX", "DU", "EAND", "TAQA", "EMPOWER", "TABREED", "TECOM", "DEYAAR",
    "UPP", "RAKPROP", "MODON", "ESHRAQ", "ESG", "BOROUGE", "FERTIGLBE",
    "RAKCER", "DANA", "NMDC", "NMDCENR", "ASM", "DSI", "DTC", "BURJEEL",
    "PUREHEALTH", "AMANAT", "AGTHIA", "LULU", "SPINNEYS", "TAALEEM", "DRIVE",
    "PALMS", "ERC", "PHOENIX", "PRESIGHT", "SPACE42", "YAHSAT", "IHC",
    "ALPHADHABI", "MULTIPLY", "DIC", "ALANSARI", "AMCREIT",
]

SHARIA_COMPLIANT_QATAR_SYMBOLS: List[str] = [
    "QIBK", "MARK", "QIIK", "DUBK", "QFBQ", "AKHI", "BEEMA", "NLCS", "IHGS",
    "DBIS", "IQCD", "QGTS", "ORDS", "VFQS", "QEWS", "QFLS", "BRES", "ERES",
    "UDCD", "MRDS", "MPHC", "QAMC", "QNCD", "QNNS", "GWCS", "GISS", "QIGD",
    "QIMD", "BLDN", "MERS", "WDAM", "ZHCD", "FALH", "MCGS", "QGMD", "MCCS",
    "MEZA", "MKDM", "AHCS", "SIIS", "QOIS",
]

SHARIA_SET: Set[str] = {s.upper() for s in SHARIA_COMPLIANT_EGX_SYMBOLS}
SHARIA_TASI_SET: Set[str] = {s.upper() for s in SHARIA_COMPLIANT_TASI_SYMBOLS}
SHARIA_UAE_SET: Set[str] = {s.upper() for s in SHARIA_COMPLIANT_UAE_SYMBOLS}
SHARIA_QATAR_SET: Set[str] = {s.upper() for s in SHARIA_COMPLIANT_QATAR_SYMBOLS}


def is_sharia_compliant(symbol: Optional[str], market: Optional[str] = None) -> bool:
    """Return True if the symbol is in the EGX 33, TASI, UAE, or Qatar Sharia-compliant list."""
    if not symbol:
        return False
    base = symbol.strip().upper().split(".")[0]
    resolved = (market or "").strip().lower()
    if resolved in ("tasi", "tadawul", "sa"):
        return base in SHARIA_TASI_SET
    if resolved in ("uae", "ae", "dfm", "adx"):
        return base in SHARIA_UAE_SET
    if resolved in ("qatar", "qa", "qse"):
        return base in SHARIA_QATAR_SET
    if resolved == "egx":
        return base in SHARIA_SET
    if is_saudi_symbol(symbol):
        return base in SHARIA_TASI_SET
    if base in SHARIA_SET:
        return True
    if base in SHARIA_UAE_SET:
        return True
    return base in SHARIA_QATAR_SET


def get_sharia_compliant_count(market: Optional[str] = "egx") -> int:
    """Return the total number of tracked Sharia-compliant symbols for a market."""
    resolved = (market or "egx").strip().lower()
    if resolved in ("tasi", "tadawul", "sa"):
        return len(SHARIA_TASI_SET)
    if resolved in ("uae", "ae", "dfm", "adx"):
        return len(SHARIA_UAE_SET)
    if resolved in ("qatar", "qa", "qse"):
        return len(SHARIA_QATAR_SET)
    return len(SHARIA_SET)
