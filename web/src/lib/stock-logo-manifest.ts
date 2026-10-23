/**
 * Symbols that have a file in public/logos/<SYMBOL>.svg.
 * StockLogo only requests /logos/*.svg for these; every other symbol used to
 * request a missing file first (hundreds of 404s per day) before falling back.
 *
 * Regenerate after adding/removing files in public/logos:
 *   node -e "console.log(require('fs').readdirSync('public/logos').filter(f=>f.endsWith('.svg')).map(f=>f.slice(0,-4).toUpperCase()).sort().join(' '))"
 */
const LOCAL_LOGO_SYMBOLS: ReadonlySet<string> = new Set([
  "AALR", "ABUK", "ACAMD", "ACAP", "ACGC", "ACRO", "ACTF", "ADCI", "ADIB", "ADPC", "AFDI", "AFMC", "AJWA",
  "ALEX", "ALUM", "AMES", "AMOC", "ANFI", "APSW", "ARCC", "AREH", "ARVA", "ASCM", "ASPI", "ATLC", "ATQA",
  "AXPH", "BINV", "BIOC", "BTFH", "CAED", "CANA", "CCAP", "CCRS", "CEFM", "CERA", "CFGH", "CICH", "CIEB",
  "CLHO", "CNFN", "COMI", "COPR", "COSG", "CSAG", "DAPH", "DEIN", "DOMT", "DSCW", "DTPP", "EASB", "EAST",
  "EBSC", "ECAP", "EDFM", "EEII", "EFIC", "EFID", "EFIH", "EGAL", "EGAS", "EGBE", "EGCH", "EGREF", "EGTS",
  "EHDR", "EIUD", "ELEC", "ELKA", "ELNA", "ELSH", "EMFD", "ENGC", "EPCO", "ETEL", "ETRS", "EXPA", "FAIT",
  "FAITA", "GTWL", "HDBK", "HELI", "HRHO", "ICID", "ICLE", "IDRE", "IFAP", "ISMA", "JUFO", "KWIN", "KZPC",
  "MASR", "MBSC", "MFPC", "MFSC", "NINH", "OBRI", "OCDI", "OCPH", "ODIN", "OFH", "OIH", "ORAS",
]);

export function hasLocalStockLogo(symbol: string): boolean {
  return LOCAL_LOGO_SYMBOLS.has((symbol || "").toUpperCase());
}
