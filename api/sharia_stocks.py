"""
Sharia-compliant stock screening definitions for EGX.
Aligned with the official EGX 33 Shariah Index approved by the Financial Regulatory Authority (FRA).
"""
from typing import Set, Optional, List

SHARIA_COMPLIANT_EGX_SYMBOLS: List[str] = [
    "ISPH", "AMOC", "ICFC", "IFAP", "OCDI", "RMDA", "ACGC", "ARCC", "CIRA",
    "ETRS", "ETEL", "MPCO", "ORWE", "MTIE", "ORAS", "ORHD", "EFIH", "EFID",
    "PHDC", "SAUD", "FAITA", "FAIT", "JUFO", "RACC", "SKPC", "OLFI", "EGAS",
    "LCSW", "TMGH", "MASR", "ATQA", "MCQE", "EGAL", "ADIB", "SWDY", "ABUK", "MFPC"
]

SHARIA_SET: Set[str] = {s.upper() for s in SHARIA_COMPLIANT_EGX_SYMBOLS}


def is_sharia_compliant(symbol: Optional[str]) -> bool:
    """Return True if the symbol is in the EGX 33 Shariah Index compliant list."""
    if not symbol:
        return False
    base = symbol.strip().upper().split(".")[0]
    return base in SHARIA_SET


def get_sharia_compliant_count() -> int:
    """Return the total number of tracked Sharia-compliant EGX symbols."""
    return len(SHARIA_SET)
