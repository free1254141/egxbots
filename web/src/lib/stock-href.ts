const CROSS_LISTED_GCC_SYMBOLS: Record<string, string> = {
  ADIB: "ADX",
  TAQA: "ADX",
};

const EXPLICIT_EXCHANGE_SUFFIX_RE = /\.(dfm|adx|qse|commodities)$/i;
const SAUDI_SUFFIX_RE = /\.(sr|sa|tadawul)$/i;

/** Resolves a canonical /stocks/[symbol] href, disambiguating GCC/EGX cross-listed tickers. */
export function getStockHref(
  symbol: string,
  options?: { market?: string | null; exchange?: string | null },
): string {
  const raw = String(symbol || "").trim();
  if (!raw) return "/stocks";
  const lower = raw.toLowerCase();
  if (lower === "null" || lower === "undefined") return "/stocks";
  if (EXPLICIT_EXCHANGE_SUFFIX_RE.test(lower)) {
    return `/stocks/${lower}`;
  }

  const cleanUpper = raw.toUpperCase().replace(SAUDI_SUFFIX_RE, "");
  const cleanLower = cleanUpper.toLowerCase();
  const exUpper = String(options?.exchange || "").trim().toUpperCase();
  const mLower = String(options?.market || "").trim().toLowerCase();

  const isGccContext =
    exUpper === "DFM" ||
    exUpper === "ADX" ||
    exUpper === "QSE" ||
    exUpper === "COMMODITIES" ||
    mLower === "uae" ||
    mLower === "qatar";

  const fallbackExchange = CROSS_LISTED_GCC_SYMBOLS[cleanUpper];
  if (isGccContext && fallbackExchange) {
    const suffixEx =
      exUpper === "DFM" || exUpper === "ADX" || exUpper === "QSE" || exUpper === "COMMODITIES"
        ? exUpper
        : fallbackExchange;
    return `/stocks/${cleanLower}.${suffixEx.toLowerCase()}`;
  }

  return `/stocks/${cleanLower}`;
}
