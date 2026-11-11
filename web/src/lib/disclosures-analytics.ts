/**
 * web/src/lib/disclosures-analytics.ts
 *
 * Core analytical engine for EGX Disclosures and Smart Money Intelligence:
 * 1. Computes Insider VWAP (Volume-Weighted Average Price) per symbol.
 * 2. Compares Current Market Price vs Insider Cost to calculate discount/premium.
 * 3. Builds Smart Money Liquidity Heatmap metrics (Net Flow EGP, volume, buy/sell streak).
 * 4. Extracts and groups Major Shareholders / Article 30 structures (Founders, 5%+ stakes, Free Float).
 */

export interface DisclosureItem {
  id: string;
  symbol: string | null;
  company_name: string;
  disclosure_type: string;
  disclosure_date: string;
  title: string;
  raw_content?: string | null;
  ai_summary: string;
  sentiment: "bullish" | "bearish" | "neutral" | string;
  action_type: string | null;
  shares_count: number | null;
  stake_before?: number | null;
  stake_after?: number | null;
  party_name: string | null;
  party_role: string | null;
  source_url: string | null;
  metadata?: {
    key_takeaway?: string;
    free_float_before?: number;
    free_float_after?: number;
    session?: string;
    execution_price?: number;
  };
}

export type DisclosureRecord = DisclosureItem;

interface _UnusedDisclosureRecord {
  id: string;
  symbol: string | null;
  company_name: string;
  disclosure_type: string;
  disclosure_date: string;
  title: string;
  raw_content?: string | null;
  ai_summary: string;
  sentiment: "bullish" | "bearish" | "neutral" | string;
  action_type: string | null;
  shares_count: number | null;
  stake_before?: number | null;
  stake_after?: number | null;
  party_name: string | null;
  party_role: string | null;
  source_url: string | null;
  metadata?: {
    key_takeaway?: string;
    free_float_before?: number;
    free_float_after?: number;
    session?: string;
    execution_price?: number;
  };
}

export interface SymbolPriceInfo {
  close: number;
  change_pct?: number;
  market_cap?: number;
  total_shares?: number;
}

export type TimeframePeriod = "all" | "today" | "yesterday" | "3d" | "7d" | "14d" | "30d" | "90d";

export interface SectorDefinition {
  id: string;
  label_ar: string;
  label_en: string;
  symbols: string[];
}

export const EGX_SECTORS: SectorDefinition[] = [
  {
    id: "all",
    label_ar: "جميع القطاعات",
    label_en: "All Sectors",
    symbols: [],
  },
  {
    id: "banking_finance",
    label_ar: "بنوك وخدمات مالية",
    label_en: "Banks & Financial Services",
    symbols: [
      "COMI", "HRHO", "PRMH", "NAHO", "CCAP", "CICH", "CIEB", "EGBE", "FAIT", "ADIB",
      "SAUD", "SAIB", "QNBE", "HDBK", "EXPA", "BTFH", "CNFN", "OFH", "EHDR", "GPIM",
      "ZMID", "AALR", "ICID", "DCRC", "SEIG", "PRDC", "TYCN", "VALU", "UNIT", "ADRI",
      "ACAP", "AIH", "AFDI", "ANFI", "ASPI", "ATLC", "BONY", "CANA", "COPR", "EALR",
      "EASB", "EMFD", "ELSH", "EIUD", "ELKA", "GPPL", "GRCA", "ICLE", "KRDI", "KWIN",
      "FIRE", "ARAB", "ODIN", "EBSC", "DEIN", "BINV", "AMIA", "AIDC", "FAITA", "VLMR",
      "SEIGA", "CPME", "TWSA", "DAPH"
    ],
  },
  {
    id: "real_estate",
    label_ar: "عقارات وتشييد ومقاولات",
    label_en: "Real Estate & Construction",
    symbols: [
      "TMGH", "PHDC", "DSCW", "ACRO", "SMCR", "SCCD", "AGIG", "AIND", "PHTV", "MHOT",
      "HELI", "ORHD", "AMER", "ROTO", "SDTI", "TALM", "IDRE", "MASR", "MAAL", "RTVC",
      "RREI", "UTOP", "EITP", "CIRA", "MENA", "NARE", "NCCW", "OBRI", "RMTV", "SPHT",
      "SMPP", "UBEE", "WKOL", "CAED", "CCRS", "GOCO", "GGCC", "GIHD", "ELWA", "MPRC",
      "TOUR", "ORAS", "HBCO", "OCDI", "EGSA"
    ],
  },
  {
    id: "chemicals_fertilizers",
    label_ar: "أسمدة وبتروكيماويات وكيماويات",
    label_en: "Fertilizers & Petrochemicals",
    symbols: [
      "MFPC", "ABUK", "FERC", "ICFC", "AMOC", "SKPC", "EFIC", "RKAZ", "EPPK", "BIDI",
      "MPCO", "AIVCB", "APSW", "EGCH", "NEDA", "PACH", "IFAP", "ISMA", "KZPC", "MOSC",
      "SCFM", "EPCO", "POUL", "ZEOT", "APPC", "MEPA", "WCDF", "UNIP", "MEGM", "SUGR",
      "MICH", "MILS", "NCGC", "RAKT", "SNFC", "SPIN", "UEFM", "WATP", "ACGC", "CEFM",
      "ELNA", "GTWL"
    ],
  },
  {
    id: "industrial_manufacturing",
    label_ar: "صناعة وتصنيع وموارد أساسية",
    label_en: "Industrial Goods & Materials",
    symbols: [
      "SWDY", "EEII", "MTIE", "ORWE", "ACAMD", "AMII", "IEEC", "EGAL", "IRON", "CERA",
      "FNAR", "TORA", "SUCE", "SVCE", "INEG", "ISMQ", "ALUM", "ENGC", "GDWA", "ALEX",
      "LCSW", "ARCC", "CRST", "ELEC", "RUBX", "ARVA", "ATQA", "AREH", "ASCM", "ECAP",
      "MCQE", "MBSC", "SMFR", "ESRS", "IRAX", "SCEM", "NDRL"
    ],
  },
  {
    id: "telecom_tech",
    label_ar: "اتصالات وتكنولوجيا ومدفوعات",
    label_en: "Telecom & Technology",
    symbols: ["ETEL", "FWRY", "RAYA", "EFIH", "FTNS", "AMPI", "VERT", "DGTZ", "GTHE", "OIH"],
  },
  {
    id: "healthcare_pharma",
    label_ar: "رعاية صحية وأدوية",
    label_en: "Healthcare & Pharma",
    symbols: [
      "ISPH", "ADCI", "AMES", "RMDA", "CLHO", "UPMS", "MIPH", "CPCI", "MPCI", "PHAR",
      "OCPH", "MCRO", "NIPH", "SIPC", "SPMD", "AXPH", "PHGC"
    ],
  },
  {
    id: "consumer_food",
    label_ar: "أغذية ومحاصيل واستهلاكي",
    label_en: "Consumer & Food",
    symbols: [
      "UFMH", "GTEX", "DOMT", "JUFO", "EAST", "EDFM", "IBCT", "BIGP", "CFGH", "BIOC",
      "INFI", "EFID", "KABO", "GOUR", "GSSC", "PRCL", "ADPC", "AJWA", "OLFI", "AFMC",
      "COSG", "MBEG"
    ],
  },
  {
    id: "energy_utilities",
    label_ar: "طاقة ومرافق ونقل",
    label_en: "Energy & Utilities",
    symbols: ["TAQA", "EGAS", "EGTS", "CSAG", "ETRS", "ALCN", "KORA"],
  },
];

export function getSymbolSector(symbol: string): { id: string; ar: string; en: string } {
  if (!symbol) return { id: "other", ar: "سوق عام", en: "General Market" };
  const upper = symbol.toUpperCase();
  for (const sec of EGX_SECTORS) {
    if (sec.id === "all") continue;
    if (sec.symbols.includes(upper)) {
      return { id: sec.id, ar: sec.label_ar, en: sec.label_en };
    }
  }
  return { id: "other", ar: "سوق عام", en: "General Market" };
}

export function filterDisclosuresByTimeframeAndSector(
  disclosures: DisclosureRecord[],
  timeframe: TimeframePeriod,
  sector: string,
  referenceDate?: string
): DisclosureRecord[] {
  let filtered = disclosures;

  // 1. Timeframe filter
  if (timeframe !== "all" && filtered.length > 0) {
    const latestDateStr =
      referenceDate ||
      filtered.reduce((max, d) => {
        return !max || (d.disclosure_date && d.disclosure_date > max)
          ? d.disclosure_date
          : max;
      }, "");

    if (latestDateStr) {
      // Find all unique dates descending to accurately determine "yesterday" (the previous trading session)
      const uniqueDates = Array.from(
        new Set(filtered.map((d) => d.disclosure_date).filter(Boolean))
      ).sort((a, b) => b.localeCompare(a));

      const yesterdayDateStr = uniqueDates.length > 1 ? uniqueDates[1] : null;
      const latestTime = new Date(latestDateStr).getTime();

      filtered = filtered.filter((d) => {
        if (!d.disclosure_date) return false;
        if (timeframe === "today") {
          return d.disclosure_date === latestDateStr;
        }
        if (timeframe === "yesterday") {
          return yesterdayDateStr ? d.disclosure_date === yesterdayDateStr : false;
        }
        const itemTime = new Date(d.disclosure_date).getTime();
        const diffDays = Math.max(0, (latestTime - itemTime) / (1000 * 60 * 60 * 24));

        if (timeframe === "3d") return diffDays <= 3;
        if (timeframe === "7d") return diffDays <= 7;
        if (timeframe === "14d") return diffDays <= 14;
        if (timeframe === "30d") return diffDays <= 30;
        if (timeframe === "90d") return diffDays <= 90;
        return true;
      });
    }
  }

  // 2. Sector filter
  if (sector && sector !== "all") {
    const secDef = EGX_SECTORS.find((s) => s.id === sector);
    if (secDef && secDef.symbols.length > 0) {
      const allowed = new Set(secDef.symbols.map((s) => s.toUpperCase()));
      filtered = filtered.filter((d) => {
        const sym = d.symbol ? d.symbol.toUpperCase() : null;
        return sym && allowed.has(sym);
      });
    }
  }

  return filtered;
}

export interface InsiderMetric {
  symbol: string;
  company_name: string;
  sector?: { id: string; ar: string; en: string };
  current_price: number;
  change_pct: number;
  market_cap?: number;
  total_shares?: number;
  insider_vwap: number;
  discount_pct: number; // Negative means trading below insider cost (undervalued vs insider)
  total_buy_shares: number;
  total_sell_shares: number;
  net_shares: number;
  total_buy_value_egp: number;
  total_sell_value_egp: number;
  net_value_egp: number;
  buy_count: number;
  sell_count: number;
  streak: number; // Positive for buy streak, negative for sell streak
  action_bias: "accumulating" | "distributing" | "neutral";
  last_action_date: string;
}

export interface HeatmapItem {
  symbol: string;
  company_name: string;
  sector?: { id: string; ar: string; en: string };
  net_value_egp: number;
  abs_value_egp: number;
  volume: number;
  action_bias: "accumulating" | "distributing" | "neutral";
  insider_vwap: number;
  current_price: number;
  discount_pct: number;
  buy_count: number;
  sell_count: number;
  weight: number; // 1 to 5 for relative box sizing
}

export interface CostComparisonItem {
  symbol: string;
  company_name: string;
  sector?: { id: string; ar: string; en: string };
  insider_vwap: number;
  current_price: number;
  discount_pct: number;
  shares_accumulated: number;
}

export interface FlowDistribution {
  total_buy_value_egp: number;
  total_sell_value_egp: number;
  net_value_egp: number;
  buy_ratio_pct: number;
  sell_ratio_pct: number;
  total_companies_tracked: number;
}

export interface MajorShareholderEntry {
  party_name: string;
  party_role: string;
  stake_before: number | null;
  stake_after: number | null;
  change_direction: "increase" | "decrease" | "unchanged";
  change_amount_pct: number;
  disclosure_date: string;
  source_url: string | null;
  title: string;
}

export interface CompanyOwnershipStructure {
  symbol: string;
  company_name: string;
  sector?: { id: string; ar: string; en: string };
  shareholders: MajorShareholderEntry[];
  free_float_pct?: number;
  total_shares?: number;
  free_float_shares?: number;
  free_float_market_cap_egp?: number;
  locked_shares?: number;
  locked_pct?: number;
  last_updated: string;
  source_url?: string | null;
}

export interface DisclosuresAnalyticsResult {
  symbolMetrics: Record<string, InsiderMetric>;
  heatmapItems: HeatmapItem[];
  costDiscountTop: CostComparisonItem[];
  flowDistribution: FlowDistribution;
  majorShareholders: CompanyOwnershipStructure[];
  executiveStats: {
    total_disclosures: number;
    total_accumulating_symbols: number;
    total_distributing_symbols: number;
    symbols_below_cost_count: number;
    net_insider_flow_egp: number;
  };
}

/**
 * Computes all analytics from raw disclosures and market prices.
 */
export function analyzeDisclosures(
  disclosures: DisclosureRecord[],
  priceMap: Record<string, SymbolPriceInfo>
): DisclosuresAnalyticsResult {
  const symbolMap: Record<
    string,
    {
      company_name: string;
      buys: { shares: number; price: number; date: string }[];
      sells: { shares: number; price: number; date: string }[];
      all_actions: { action: "buy" | "sell"; date: string }[];
    }
  > = {};

  const majorShareholderMap: Record<string, CompanyOwnershipStructure> = {};

  let totalDisclosuresCount = disclosures.length;

  for (const d of disclosures) {
    const sym = d.symbol ? d.symbol.toUpperCase() : null;
    const act = (d.action_type || "").toLowerCase();
    const dtype = (d.disclosure_type || "").toLowerCase();
    const shares = Math.abs(d.shares_count || 0);

    // 1. Process Major Shareholders / Article 30 structures
    if (sym && (dtype === "major_shareholders" || d.stake_after != null || d.stake_before != null)) {
      if (!majorShareholderMap[sym]) {
        majorShareholderMap[sym] = {
          symbol: sym,
          company_name: d.company_name || sym,
          sector: getSymbolSector(sym),
          shareholders: [],
          free_float_pct: d.metadata?.free_float_after,
          last_updated: d.disclosure_date || "",
          source_url: d.source_url,
        };
      }

      const before = d.stake_before != null ? Number(d.stake_before) : null;
      const after = d.stake_after != null ? Number(d.stake_after) : null;
      let changeDir: "increase" | "decrease" | "unchanged" = "unchanged";
      let diff = 0;

      if (before != null && after != null) {
        diff = Number((after - before).toFixed(3));
        if (diff > 0.001) changeDir = "increase";
        else if (diff < -0.001) changeDir = "decrease";
      }

      majorShareholderMap[sym].shareholders.push({
        party_name: d.party_name || "مساهم رئيسي",
        party_role: d.party_role || "مساهم رئيسي / مؤسس",
        stake_before: before,
        stake_after: after,
        change_direction: changeDir,
        change_amount_pct: Math.abs(diff),
        disclosure_date: d.disclosure_date,
        source_url: d.source_url,
        title: d.title || "",
      });

      if (d.metadata?.free_float_after != null) {
        majorShareholderMap[sym].free_float_pct = d.metadata.free_float_after;
      }
    }

    // 2. Process Insider Trading Operations (Buys & Sells)
    if (!sym || (act !== "buy" && act !== "sell")) {
      continue;
    }

    if (!symbolMap[sym]) {
      symbolMap[sym] = {
        company_name: d.company_name || sym,
        buys: [],
        sells: [],
        all_actions: [],
      };
    }

    const currentPriceInfo = priceMap[sym] || { close: 1.0, change_pct: 0 };
    // Estimate execution price: metadata > current price fallback
    const estimatedPrice = d.metadata?.execution_price && d.metadata.execution_price > 0
      ? d.metadata.execution_price
      : currentPriceInfo.close > 0
      ? currentPriceInfo.close
      : 1.0;

    if (act === "buy") {
      symbolMap[sym].buys.push({ shares, price: estimatedPrice, date: d.disclosure_date });
      symbolMap[sym].all_actions.push({ action: "buy", date: d.disclosure_date });
    } else if (act === "sell") {
      symbolMap[sym].sells.push({ shares, price: estimatedPrice, date: d.disclosure_date });
      symbolMap[sym].all_actions.push({ action: "sell", date: d.disclosure_date });
    }
  }

  // 3. Compute per-symbol metrics (VWAP, Net Volume, Net Value, Discount)
  const symbolMetrics: Record<string, InsiderMetric> = {};
  const heatmapItems: HeatmapItem[] = [];
  const costDiscountTop: CostComparisonItem[] = [];

  let grandTotalBuyValue = 0;
  let grandTotalSellValue = 0;
  let symbolsBelowCostCount = 0;
  let totalAccumulatingSymbols = 0;
  let totalDistributingSymbols = 0;

  for (const [sym, info] of Object.entries(symbolMap)) {
    const priceInfo = priceMap[sym] || { close: 0, change_pct: 0 };
    const curPrice = priceInfo.close;

    const totalBuyShares = info.buys.reduce((sum, b) => sum + b.shares, 0);
    const totalSellShares = info.sells.reduce((sum, s) => sum + s.shares, 0);

    const totalBuyValueEgp = info.buys.reduce((sum, b) => sum + b.shares * b.price, 0);
    const totalSellValueEgp = info.sells.reduce((sum, s) => sum + s.shares * s.price, 0);

    grandTotalBuyValue += totalBuyValueEgp;
    grandTotalSellValue += totalSellValueEgp;

    const netShares = totalBuyShares - totalSellShares;
    const netValueEgp = totalBuyValueEgp - totalSellValueEgp;

    // Insider VWAP (Weighted by buy volume)
    const insiderVWAP = totalBuyShares > 0
      ? totalBuyValueEgp / totalBuyShares
      : curPrice;

    // Discount percentage = (Current Price - VWAP) / VWAP * 100
    // If curPrice is 1.80 and VWAP is 2.00 -> discount is -10.0% (Opportunity!)
    let discountPct = 0;
    if (insiderVWAP > 0 && curPrice > 0) {
      discountPct = Number((((curPrice - insiderVWAP) / insiderVWAP) * 100).toFixed(1));
    }

    const sec = getSymbolSector(sym);

    // Netting condition: Insider must still maintain net accumulated shares (netShares > 0).
    // If a subsequent or concurrent sell cancelled out the buy (netShares <= 0), it is not an active accumulation opportunity!
    if (discountPct < -1.0 && netShares > 0) {
      symbolsBelowCostCount++;
      costDiscountTop.push({
        symbol: sym,
        company_name: info.company_name,
        sector: sec,
        insider_vwap: Number(insiderVWAP.toFixed(2)),
        current_price: Number(curPrice.toFixed(2)),
        discount_pct: Math.abs(discountPct),
        shares_accumulated: netShares, // الصافي الفعلي بعد خصم أي بيع
      });
    }

    // Determine Action Bias & Streak
    let actionBias: "accumulating" | "distributing" | "neutral" = "neutral";
    if (netShares > 0) {
      actionBias = "accumulating";
      totalAccumulatingSymbols++;
    } else if (netShares < 0) {
      actionBias = "distributing";
      totalDistributingSymbols++;
    }

    // Sort actions by date to calculate current streak
    const sortedActions = [...info.all_actions].sort((a, b) => b.date.localeCompare(a.date));
    let streak = 0;
    if (sortedActions.length > 0) {
      const firstAction = sortedActions[0].action;
      for (const actItem of sortedActions) {
        if (actItem.action === firstAction) {
          streak += firstAction === "buy" ? 1 : -1;
        } else {
          break;
        }
      }
    }

    const lastActionDate = sortedActions.length > 0 ? sortedActions[0].date : "";

    const metric: InsiderMetric = {
      symbol: sym,
      company_name: info.company_name,
      sector: sec,
      current_price: curPrice,
      change_pct: priceInfo.change_pct || 0,
      market_cap: priceInfo.market_cap,
      total_shares: priceInfo.total_shares,
      insider_vwap: Number(insiderVWAP.toFixed(2)),
      discount_pct: discountPct,
      total_buy_shares: totalBuyShares,
      total_sell_shares: totalSellShares,
      net_shares: netShares,
      total_buy_value_egp: totalBuyValueEgp,
      total_sell_value_egp: totalSellValueEgp,
      net_value_egp: netValueEgp,
      buy_count: info.buys.length,
      sell_count: info.sells.length,
      streak,
      action_bias: actionBias,
      last_action_date: lastActionDate,
    };

    symbolMetrics[sym] = metric;

    const absVal = Math.max(totalBuyValueEgp, totalSellValueEgp);
    heatmapItems.push({
      symbol: sym,
      company_name: info.company_name,
      sector: sec,
      net_value_egp: netValueEgp,
      abs_value_egp: absVal,
      volume: totalBuyShares + totalSellShares,
      action_bias: actionBias,
      insider_vwap: Number(insiderVWAP.toFixed(2)),
      current_price: Number(curPrice.toFixed(2)),
      discount_pct: discountPct,
      buy_count: info.buys.length,
      sell_count: info.sells.length,
      weight: 1, // Will assign below based on rank
    });
  }

  // Assign Heatmap weights (1 to 5) based on absolute EGP transaction volume
  heatmapItems.sort((a, b) => b.abs_value_egp - a.abs_value_egp);
  const totalHeat = heatmapItems.length;
  heatmapItems.forEach((item, idx) => {
    if (totalHeat <= 4) {
      item.weight = 3;
    } else if (idx < Math.ceil(totalHeat * 0.2)) {
      item.weight = 5; // Top 20%
    } else if (idx < Math.ceil(totalHeat * 0.45)) {
      item.weight = 4;
    } else if (idx < Math.ceil(totalHeat * 0.75)) {
      item.weight = 3;
    } else {
      item.weight = 2;
    }
  });

  // Sort cost discounts descending by discount magnitude
  costDiscountTop.sort((a, b) => b.discount_pct - a.discount_pct);

  // Flow Distribution summary
  const grandTotal = grandTotalBuyValue + grandTotalSellValue;
  const buyRatio = grandTotal > 0 ? Number(((grandTotalBuyValue / grandTotal) * 100).toFixed(1)) : 50;
  const sellRatio = grandTotal > 0 ? Number(((grandTotalSellValue / grandTotal) * 100).toFixed(1)) : 50;

  const flowDistribution: FlowDistribution = {
    total_buy_value_egp: grandTotalBuyValue,
    total_sell_value_egp: grandTotalSellValue,
    net_value_egp: grandTotalBuyValue - grandTotalSellValue,
    buy_ratio_pct: buyRatio,
    sell_ratio_pct: sellRatio,
    total_companies_tracked: Object.keys(symbolMap).length,
  };

  // Enrich majorShareholder structures with mathematical free float and shares count
  for (const [sym, comp] of Object.entries(majorShareholderMap)) {
    const curPrice = priceMap[sym]?.close || 0;
    let totalShares = comp.total_shares || priceMap[sym]?.total_shares || 0;

    if (!totalShares) {
      for (const d of disclosures) {
        if (
          d.symbol?.toUpperCase() === sym &&
          d.shares_count &&
          d.stake_after &&
          Number(d.stake_after) > 0
        ) {
          const derived = Math.round(Math.abs(d.shares_count) / (Number(d.stake_after) / 100));
          if (derived > totalShares) totalShares = derived;
        }
      }
    }

    if (totalShares > 0) {
      comp.total_shares = totalShares;
      const ffPct = comp.free_float_pct ?? 25;
      comp.free_float_shares = Math.round(totalShares * (ffPct / 100));
      comp.locked_shares = Math.max(0, totalShares - comp.free_float_shares);
      comp.locked_pct = Number((100 - ffPct).toFixed(1));
      if (curPrice > 0) {
        comp.free_float_market_cap_egp = comp.free_float_shares * curPrice;
      }
    }
  }

  const majorShareholders = Object.values(majorShareholderMap);

  return {
    symbolMetrics,
    heatmapItems,
    costDiscountTop,
    flowDistribution,
    majorShareholders,
    executiveStats: {
      total_disclosures: totalDisclosuresCount,
      total_accumulating_symbols: totalAccumulatingSymbols,
      total_distributing_symbols: totalDistributingSymbols,
      symbols_below_cost_count: symbolsBelowCostCount,
      net_insider_flow_egp: grandTotalBuyValue - grandTotalSellValue,
    },
  };
}

export interface GroupedStockDisclosure {
  key: string;
  symbol: string | null;
  company_name: string;
  sector?: { id: string; ar: string; en: string };
  latest_date: string;
  items: DisclosureRecord[];

  // Net insider trading metrics in the period:
  has_insider_trades: boolean;
  total_buy_shares: number;
  total_sell_shares: number;
  net_shares: number;
  total_buy_value_egp: number;
  total_sell_value_egp: number;
  net_value_egp: number;
  trade_summary: {
    status: "net_accumulation" | "net_distribution" | "offset" | "none";
    message_ar: string;
    message_en: string;
  };

  // Consolidated sentiment & status:
  overall_sentiment: "bullish" | "bearish" | "neutral" | "mixed";
  sentiment_badge_ar: string;
  sentiment_badge_en: string;
  badge_color: "green" | "red" | "yellow" | "blue";
}

export function groupDisclosuresByStock(
  disclosures: DisclosureRecord[],
  priceMap: Record<string, SymbolPriceInfo> = {}
): GroupedStockDisclosure[] {
  const groups: Map<string, GroupedStockDisclosure> = new Map();

  for (const item of disclosures) {
    const sym = item.symbol ? item.symbol.toUpperCase().trim() : null;
    const isGenericCompany =
      !item.company_name ||
      item.company_name.trim() === "البورصة المصرية" ||
      item.company_name.trim() === "EGX";
    const groupKey = sym || (!isGenericCompany ? item.company_name.trim() : item.id);

    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        key: groupKey,
        symbol: sym,
        company_name: item.company_name || sym || "إفصاح عام",
        sector: sym ? getSymbolSector(sym) : undefined,
        latest_date: item.disclosure_date,
        items: [],
        has_insider_trades: false,
        total_buy_shares: 0,
        total_sell_shares: 0,
        net_shares: 0,
        total_buy_value_egp: 0,
        total_sell_value_egp: 0,
        net_value_egp: 0,
        trade_summary: { status: "none", message_ar: "", message_en: "" },
        overall_sentiment: "neutral",
        sentiment_badge_ar: "محايد / إداري",
        sentiment_badge_en: "Neutral",
        badge_color: "yellow",
      });
    }

    const group = groups.get(groupKey)!;
    group.items.push(item);
    if (item.disclosure_date && item.disclosure_date > group.latest_date) {
      group.latest_date = item.disclosure_date;
    }

    // Accumulate trades if buy/sell
    const act = (item.action_type || "").toLowerCase();
    const shares = Math.abs(item.shares_count || 0);
    const priceInfo = sym && priceMap[sym] ? priceMap[sym] : { close: 1.0 };
    const execPrice = item.metadata?.execution_price && item.metadata.execution_price > 0
      ? item.metadata.execution_price
      : priceInfo.close > 0
      ? priceInfo.close
      : 1.0;

    if (act === "buy") {
      group.has_insider_trades = true;
      group.total_buy_shares += shares;
      group.total_buy_value_egp += shares * execPrice;
    } else if (act === "sell") {
      group.has_insider_trades = true;
      group.total_sell_shares += shares;
      group.total_sell_value_egp += shares * execPrice;
    }
  }

  // Finalize net metrics & sentiment per group
  for (const group of groups.values()) {
    group.net_shares = group.total_buy_shares - group.total_sell_shares;
    group.net_value_egp = group.total_buy_value_egp - group.total_sell_value_egp;

    // Check trade offset logic: "عشان نحدث اذا كان فيه بيع الغى شراء معين او العكس وهكذا"
    if (group.has_insider_trades) {
      if (group.total_buy_shares > 0 && group.total_sell_shares > 0 && group.net_shares === 0) {
        group.trade_summary = {
          status: "offset",
          message_ar: "عمليات البيع عادلت الشراء بالكامل (الصافي = 0 سهم)",
          message_en: "Selling fully cancelled out buying (Net = 0 shares)",
        };
      } else if (group.net_shares > 0) {
        const offsetNote = group.total_sell_shares > 0
          ? ` (بعد خصم مبيعات ${group.total_sell_shares.toLocaleString()} سهم)`
          : "";
        group.trade_summary = {
          status: "net_accumulation",
          message_ar: `صافي تجميع إيجابي: +${group.net_shares.toLocaleString()} سهم${offsetNote}`,
          message_en: `Net Accumulation: +${group.net_shares.toLocaleString()} shares`,
        };
      } else if (group.net_shares < 0) {
        const offsetNote = group.total_buy_shares > 0
          ? ` (بعد خصم مشتريات ${group.total_buy_shares.toLocaleString()} سهم)`
          : "";
        group.trade_summary = {
          status: "net_distribution",
          message_ar: `صافي تخارج وتسييل: ${group.net_shares.toLocaleString()} سهم${offsetNote}`,
          message_en: `Net Distribution: ${group.net_shares.toLocaleString()} shares`,
        };
      }
    }

    // Determine overall sentiment
    const sentiments = group.items.map((it) => (it.sentiment || "neutral").toLowerCase());
    const hasBullish = sentiments.includes("bullish") || group.net_shares > 0;
    const hasBearish = sentiments.includes("bearish") || group.net_shares < 0;

    if (hasBullish && hasBearish) {
      // Mixed: e.g. EGCH had 1 neutral/bullish operational event and 1 bearish lawsuit
      group.overall_sentiment = "mixed";
      group.sentiment_badge_ar = "مختلط / أحداث متعددة";
      group.sentiment_badge_en = "Mixed Events";
      group.badge_color = "yellow";
    } else if (hasBullish) {
      group.overall_sentiment = "bullish";
      group.sentiment_badge_ar = "إيجابي / تجميع ومحفز";
      group.sentiment_badge_en = "Bullish / Accumulation";
      group.badge_color = "green";
    } else if (hasBearish) {
      group.overall_sentiment = "bearish";
      group.sentiment_badge_ar = "سلبي / تسييل وتخارج";
      group.sentiment_badge_en = "Bearish / Liquidation";
      group.badge_color = "red";
    } else {
      group.overall_sentiment = "neutral";
      group.sentiment_badge_ar = "محايد / إداري";
      group.sentiment_badge_en = "Neutral / Admin";
      group.badge_color = "yellow";
    }
  }

  // Return groups sorted by latest date descending
  return Array.from(groups.values()).sort((a, b) => b.latest_date.localeCompare(a.latest_date));
}
