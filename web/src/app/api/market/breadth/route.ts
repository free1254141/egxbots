import { NextRequest, NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import {
  resolveRequestMarket,
  getMarketExchange,
  getMarketSupabaseClient,
  type MarketMode,
} from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const PUBLIC_CACHE_HEADERS = dailyCacheHeaders(DAILY_CACHE_TAGS.market);
const PRIVATE_NO_STORE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vercel-Cache-Tag": DAILY_CACHE_TAGS.market,
};

function classifyMarketSector(rawSector: string, rawIndustry: string): { sector: string; sector_ar: string } {
  const ind = String(rawIndustry || "").toLowerCase();
  const sec = String(rawSector || "").toLowerCase();
  const combined = `${ind} ${sec}`;
  if (combined.includes("reit") || combined.includes("صناديق عقارية") || combined.includes("ريت")) {
    return { sector: "REITs", sector_ar: "الصناديق العقارية المتداولة (ريت)" };
  }
  if (combined.includes("real estate") || ind.includes("homebuilding") || combined.includes("عقار")) {
    return { sector: "Real Estate", sector_ar: "العقارات والتطوير العقاري" };
  }
  if ((combined.includes("bank") && !ind.includes("investment") && !ind.includes("broker")) || combined.includes("بنوك") || combined.includes("مصارف")) {
    return { sector: "Banks", sector_ar: "البنوك" };
  }
  if (
    sec.includes("finance") ||
    combined.includes("financial") ||
    ind.includes("investment") ||
    combined.includes("insurance") ||
    combined.includes("تأمين") ||
    combined.includes("مالية")
  ) {
    return { sector: "Financial Services", sector_ar: "الخدمات المالية والتأمين" };
  }
  if (combined.includes("chemical") || combined.includes("fertilizer") || combined.includes("petrochemical") || combined.includes("كيماويات") || combined.includes("أسمدة")) {
    return { sector: "Chemicals & Fertilizers", sector_ar: "الكيماويات والأسمدة والبتروكيماويات" };
  }
  if (combined.includes("construction") || combined.includes("engineering") || combined.includes("contracting") || combined.includes("cement") || combined.includes("building") || combined.includes("مقاولات") || combined.includes("بناء") || combined.includes("تشييد")) {
    return { sector: "Construction & Building Materials", sector_ar: "التشييد ومواد البناء" };
  }
  if (combined.includes("steel") || combined.includes("mining") || combined.includes("metal") || combined.includes("non-energy minerals") || combined.includes("حديد") || combined.includes("تعدين") || combined.includes("material") || combined.includes("مواد أساسية")) {
    return { sector: "Materials & Basic Resources", sector_ar: "المواد الأساسية والتعدين" };
  }
  if (combined.includes("food") || combined.includes("beverage") || combined.includes("milling") || combined.includes("poultry") || combined.includes("agricultural") || combined.includes("consumer non-durables") || combined.includes("أغذية") || combined.includes("مشروبات")) {
    return { sector: "Food & Beverages", sector_ar: "الأغذية والمشروبات والزراعة" };
  }
  if (combined.includes("pharma") || combined.includes("health") || combined.includes("medical") || combined.includes("hospital") || combined.includes("أدوية") || combined.includes("صحية")) {
    return { sector: "Healthcare & Pharmaceuticals", sector_ar: "الرعاية الصحية والأدوية" };
  }
  if (combined.includes("telecom") || combined.includes("technology") || combined.includes("communications") || combined.includes("software") || combined.includes("electronic") || combined.includes("media") || combined.includes("اتصالات") || combined.includes("تقنية")) {
    return { sector: "Telecom & Technology", sector_ar: "الاتصالات وتكنولوجيا المعلومات" };
  }
  if (combined.includes("energy") || combined.includes("oil") || combined.includes("gas") || combined.includes("طاقة")) {
    return { sector: "Energy", sector_ar: "الطاقة" };
  }
  if (combined.includes("utilities") || combined.includes("utility") || combined.includes("مرافق")) {
    return { sector: "Utilities", sector_ar: "المرافق العامة" };
  }
  if (combined.includes("transport") || combined.includes("shipping") || combined.includes("logistics") || combined.includes("container") || combined.includes("نقل")) {
    return { sector: "Transportation & Shipping", sector_ar: "النقل والشحن والخدمات اللوجستية" };
  }
  if (combined.includes("tourism") || combined.includes("hotel") || combined.includes("resort") || combined.includes("سياحة")) {
    return { sector: "Tourism & Leisure", sector_ar: "السياحة والترفيه" };
  }
  if (combined.includes("retail") || combined.includes("consumer") || combined.includes("apparel") || combined.includes("durables") || combined.includes("تجزئة") || combined.includes("استهلاك")) {
    return { sector: "Retail & Consumer Services", sector_ar: "التجزئة والخدمات الاستهلاكية" };
  }
  if (combined.includes("industrial") || combined.includes("capital goods") || combined.includes("commercial") || combined.includes("manufacturing") || combined.includes("paper") || combined.includes("صناعات") || combined.includes("رأسمالية")) {
    return { sector: "Industrial Goods", sector_ar: "الصناعات التحويلية والسلع الرأسمالية" };
  }
  return { sector: "Other Sectors", sector_ar: "قطاعات متنوعة أخرى" };
}

async function fetchBreadthIndicators(supabase: any, exchange: string, latestDate: string) {
  const attempts = [
    "symbol, close, volume, ema_50, ema_200, rsi_14, vol_sma20, r_vol, cmf_20, change_pct",
    "symbol, close, volume, ema_50, ema_200, rsi_14, vol_sma20, r_vol, change_pct",
    "symbol, close, volume, ema_50, ema_200, rsi_14, volume_sma_20, r_vol, cmf_20, change_pct",
    "symbol, close, volume, ema_50, ema_200, rsi_14, volume_sma_20, r_vol, change_pct",
    "symbol, close, volume, ema_50, ema_200, rsi_14, volume_sma_20, change_pct",
    "symbol, close, volume, change_pct",
  ];
  let lastError: any = null;
  for (const selectFields of attempts) {
    const res = await supabase
      .from("stock_technical_indicators")
      .select(selectFields)
      .eq("exchange", exchange)
      .eq("date", latestDate)
      .limit(500);
    if (!res.error) return res;
    lastError = res.error;
  }
  return { data: null, error: lastError };
}

async function fetchFundamentalsSafe(supabase: any, exchange: string): Promise<any[]> {
  const attempts = [
    "symbol, name, name_ar, data",
    "symbol, name, data",
    "symbol, data",
  ];
  for (const selectFields of attempts) {
    try {
      const { data, error } = await supabase
        .from("stock_fundamentals")
        .select(selectFields)
        .eq("exchange", exchange)
        .limit(500);
      if (!error) return data || [];
    } catch {
      // Try next projection
    }
  }
  return [];
}

async function fetchScanSummarySafe(supabase: any, latestDate: string): Promise<any[]> {
  try {
    const { data, error } = await supabase
      .from("stock_scans_summary")
      .select("symbol, scan_date, acc_score, dist_score, wyckoff_phase")
      .eq("scan_date", latestDate)
      .order("acc_score", { ascending: false })
      .limit(500);
    if (!error && Array.isArray(data)) return data;
  } catch {
    // Non-fatal: stock_scans_summary is optional (e.g., on SAUDI_SUPABASE)
  }
  return [];
}

async function fetchSaudiStocksMetaSafe(supabase: any, exchange: string): Promise<any[]> {
  const attempts = [
    "symbol, name, name_ar, sector",
    "symbol, name, sector",
  ];
  for (const selectFields of attempts) {
    try {
      const { data, error } = await supabase
        .from("stocks")
        .select(selectFields)
        .eq("exchange", exchange)
        .eq("is_active", true)
        .limit(500);
      if (!error) return data || [];
    } catch {
      // Non-fatal
    }
  }
  return [];
}

async function loadMarketBreadth(market: MarketMode) {
  const supabase = getMarketSupabaseClient(market);
  const exchange = getMarketExchange(market);
  const currency = market === "tasi" ? "SAR" : "EGP";
  const currencyLabelAr = market === "tasi" ? "ر.س" : "ج.م";

  // 1. Get the latest available date for the active market
  const { data: dateRows, error: dateError } = await supabase
    .from("stock_technical_indicators")
    .select("date")
    .eq("exchange", exchange)
    .order("date", { ascending: false })
    .limit(1);

  if (dateError || !dateRows || dateRows.length === 0) {
    console.error(`Failed to fetch latest technical indicator date (${exchange}):`, dateError);
    return null;
  }

  const latestDate = dateRows[0].date;

  // 2. Fetch indicators, fundamentals, optional scan summary, and Saudi stocks metadata in parallel
  const [indRes, fundRows, scanRows, saudiStocks] = await Promise.all([
    fetchBreadthIndicators(supabase, exchange, latestDate),
    fetchFundamentalsSafe(supabase, exchange),
    fetchScanSummarySafe(supabase, latestDate),
    market === "tasi" ? fetchSaudiStocksMetaSafe(supabase, exchange) : Promise.resolve([]),
  ]);

  const { data: indicators, error: indError } = indRes;
  if (indError || !indicators || indicators.length === 0) {
    console.error(`Failed to fetch indicators for date ${latestDate} (${exchange}):`, indError);
    return null;
  }

  const nameMap = new Map<string, string>();
  const sectorMap = new Map<string, { sector: string; sector_ar: string }>();

  for (const s of saudiStocks as any[]) {
    const sym = String(s?.symbol || "").toUpperCase();
    if (!sym) continue;
    const label = s?.name_ar || s?.name || "";
    if (label) nameMap.set(sym, String(label));
    if (s?.sector) sectorMap.set(sym, classifyMarketSector(s.sector, ""));
  }

  if (fundRows) {
    for (const row of fundRows as any[]) {
      const sym = String(row.symbol || "").toUpperCase();
      if (!sym) continue;
      const payload = row.data || {};
      const name = row.name_ar || payload.name_ar || (market === "tasi" ? nameMap.get(sym) : "") || row.name || payload.name || payload.Name || "";
      const rawSector = payload.sector || payload.Sector || "";
      const rawIndustry = payload.industry || payload.Industry || "";
      if (name && !nameMap.has(sym)) {
        nameMap.set(sym, String(name));
      } else if (row.name_ar) {
        nameMap.set(sym, String(row.name_ar));
      }
      if (rawSector || rawIndustry || !sectorMap.has(sym)) {
        sectorMap.set(sym, classifyMarketSector(rawSector, rawIndustry));
      }
    }
  }

  let accumulationCount = 0;
  let strongAccumulationCount = 0;
  let distributionCount = 0;
  let strongDistributionCount = 0;
  if (scanRows) {
    for (const sRow of scanRows as any[]) {
      const accScore = Number(sRow.acc_score || 0);
      const distScore = Number(sRow.dist_score || 0);
      if (accScore >= 50) accumulationCount++;
      if (accScore >= 70) strongAccumulationCount++;
      if (distScore >= 50) distributionCount++;
      if (distScore >= 70) strongDistributionCount++;
    }
  }

  // 4. Calculate Breadth & Market-Wide Liquidity Metrics
  let advancing = 0;
  let declining = 0;
  let unchanged = 0;
  let aboveEma50 = 0;
  let aboveEma200 = 0;
  let rsiSum = 0;
  let rsiCount = 0;
  let volRatioSum = 0;
  let volRatioCount = 0;

  let totalTurnoverValue = 0;
  let avg20dTurnoverValue = 0;
  let advancingTurnoverValue = 0;
  let decliningTurnoverValue = 0;
  let unchangedTurnoverValue = 0;
  let unusualVolumeSurgeCount = 0;
  let positiveCmfCount = 0;
  let negativeCmfCount = 0;

  const sectorBuckets = new Map<string, {
    sector: string;
    sector_ar: string;
    turnover_value: number;
    weighted_change_num: number;
    weighted_cmf_num: number;
    stocks_count: number;
    advancing: number;
    declining: number;
    top_stock_symbol: string;
    top_stock_name: string;
    top_stock_turnover_value: number;
    top_stock_change_pct: number;
  }>();

  const validStocks: any[] = [];

  for (const ind of indicators as any[]) {
    const sym = String(ind.symbol || "").toUpperCase();
    const close = Number(ind.close || 0);
    if (!close) continue;

    const changePct = Number(ind.change_pct || 0);
    if (changePct > 0) advancing++;
    else if (changePct < 0) declining++;
    else unchanged++;

    const ema50 = Number(ind.ema_50 || 0);
    const ema200 = Number(ind.ema_200 || 0);
    if (ema50 && close > ema50) aboveEma50++;
    if (ema200 && close > ema200) aboveEma200++;

    const rsi = Number(ind.rsi_14);
    if (!isNaN(rsi)) {
      rsiSum += rsi;
      rsiCount++;
    }

    const vol = Number(ind.volume || 0);
    const volSma = Number(ind.vol_sma20 ?? ind.volume_sma_20 ?? 0);
    const rVol = ind.r_vol != null ? Number(ind.r_vol) : (vol && volSma ? vol / volSma : 0);
    const cmf20 = ind.cmf_20 != null ? Number(ind.cmf_20) : 0;

    if (vol && volSma) {
      volRatioSum += vol / volSma;
      volRatioCount++;
    }
    if (rVol >= 2.0) unusualVolumeSurgeCount++;
    if (cmf20 > 0.05) positiveCmfCount++;
    else if (cmf20 < -0.05) negativeCmfCount++;

    const turnoverValue = close * Math.max(0, vol);
    const avgStockTurnover20d = close * Math.max(0, volSma);
    totalTurnoverValue += turnoverValue;
    avg20dTurnoverValue += avgStockTurnover20d;

    if (changePct > 0) advancingTurnoverValue += turnoverValue;
    else if (changePct < 0) decliningTurnoverValue += turnoverValue;
    else unchangedTurnoverValue += turnoverValue;

    const stockName = nameMap.get(sym) || sym;
    const sectorInfo = sectorMap.get(sym) || { sector: "Other Sectors", sector_ar: "قطاعات متنوعة أخرى" };
    const sector = sectorInfo.sector;
    const sectorAr = sectorInfo.sector_ar;

    if (turnoverValue > 0) {
      if (!sectorBuckets.has(sector)) {
        sectorBuckets.set(sector, {
          sector,
          sector_ar: sectorAr,
          turnover_value: 0,
          weighted_change_num: 0,
          weighted_cmf_num: 0,
          stocks_count: 0,
          advancing: 0,
          declining: 0,
          top_stock_symbol: sym,
          top_stock_name: stockName,
          top_stock_turnover_value: turnoverValue,
          top_stock_change_pct: changePct,
        });
      }
      const b = sectorBuckets.get(sector)!;
      b.turnover_value += turnoverValue;
      b.weighted_change_num += changePct * turnoverValue;
      b.weighted_cmf_num += cmf20 * turnoverValue;
      b.stocks_count += 1;
      if (changePct > 0) b.advancing += 1;
      else if (changePct < 0) b.declining += 1;
      if (turnoverValue > b.top_stock_turnover_value) {
        b.top_stock_symbol = sym;
        b.top_stock_name = stockName;
        b.top_stock_turnover_value = turnoverValue;
        b.top_stock_change_pct = changePct;
      }
    }

    validStocks.push({
      symbol: sym,
      name: stockName,
      sector,
      sector_ar: sectorAr,
      change_pct: changePct,
      close: close,
      volume: vol,
      turnover_egp: turnoverValue,
      r_vol: Number(rVol.toFixed(2)),
      cmf_20: Number(cmf20.toFixed(3)),
      rsi_14: !isNaN(rsi) ? rsi : 50,
    });
  }

  const totalStocks = validStocks.length || 1;
  const pctAboveEma50 = (aboveEma50 / totalStocks) * 100;
  const pctAboveEma200 = (aboveEma200 / totalStocks) * 100;
  const avgRsi = rsiCount > 0 ? rsiSum / rsiCount : 50;
  const avgVolRatio = volRatioCount > 0 ? volRatioSum / volRatioCount : 1.0;

  // Calculate Health Score
  const adRatio = (advancing + declining) > 0 ? advancing / (advancing + declining) : 0.5;
  const adScore = adRatio * 100;
  const ema50Score = pctAboveEma50;
  const ema200Score = pctAboveEma200;

  let rsiScore = 50;
  if (avgRsi >= 30 && avgRsi <= 70) {
    rsiScore = 100 - Math.abs(avgRsi - 50) * 2.5;
  } else if (avgRsi < 30) {
    rsiScore = Math.max(10, avgRsi * 1.6);
  } else {
    rsiScore = Math.max(10, (100 - avgRsi) * 1.6);
  }

  const volScore = Math.min(100, (avgVolRatio / 2.0) * 100);

  const healthScore = Math.round(
    adScore * 0.3 +
    ema50Score * 0.2 +
    ema200Score * 0.2 +
    rsiScore * 0.15 +
    volScore * 0.15
  );

  let healthLabel = "moderate";
  if (healthScore >= 70) healthLabel = "strong";
  else if (healthScore < 45) healthLabel = "weak";

  // Top Gainers and Losers
  const sortedMovers = [...validStocks].sort((a, b) => b.change_pct - a.change_pct);
  const topGainers = sortedMovers.slice(0, 5);
  const topLosers = [...sortedMovers].reverse().slice(0, 5);

  // Market-Wide Liquidity Aggregations
  const stocksByTurnover = [...validStocks].sort((a, b) => b.turnover_egp - a.turnover_egp);
  const top5TurnoverSum = stocksByTurnover.slice(0, 5).reduce((s, r) => s + r.turnover_egp, 0);
  const top10TurnoverSum = stocksByTurnover.slice(0, 10).reduce((s, r) => s + r.turnover_egp, 0);

  const totalTurnoverMillion = Number((totalTurnoverValue / 1_000_000).toFixed(2));
  const totalTurnoverBillion = Number((totalTurnoverValue / 1_000_000_000).toFixed(3));
  const avg20dTurnoverMillion = Number((avg20dTurnoverValue / 1_000_000).toFixed(2));
  const turnoverVs20dRatio = avg20dTurnoverValue > 0 ? Number((totalTurnoverValue / avg20dTurnoverValue).toFixed(2)) : 1;
  const turnoverVs20dPct = avg20dTurnoverValue > 0 ? Number(((totalTurnoverValue / avg20dTurnoverValue) * 100).toFixed(2)) : 100;

  const advancingTurnoverMillion = Number((advancingTurnoverValue / 1_000_000).toFixed(2));
  const decliningTurnoverMillion = Number((decliningTurnoverValue / 1_000_000).toFixed(2));
  const unchangedTurnoverMillion = Number((unchangedTurnoverValue / 1_000_000).toFixed(2));
  const advancingTurnoverPct = totalTurnoverValue > 0 ? Number(((advancingTurnoverValue / totalTurnoverValue) * 100).toFixed(2)) : 0;
  const decliningTurnoverPct = totalTurnoverValue > 0 ? Number(((decliningTurnoverValue / totalTurnoverValue) * 100).toFixed(2)) : 0;
  const unchangedTurnoverPct = totalTurnoverValue > 0 ? Number(((unchangedTurnoverValue / totalTurnoverValue) * 100).toFixed(2)) : 0;

  const top5ConcentrationPct = totalTurnoverValue > 0 ? Number(((top5TurnoverSum / totalTurnoverValue) * 100).toFixed(2)) : 0;
  const top10ConcentrationPct = totalTurnoverValue > 0 ? Number(((top10TurnoverSum / totalTurnoverValue) * 100).toFixed(2)) : 0;

  const topSectors = Array.from(sectorBuckets.values())
    .sort((a, b) => b.turnover_value - a.turnover_value)
    .slice(0, 6)
    .map((b) => ({
      sector: b.sector,
      sector_ar: b.sector_ar,
      turnover_million_egp: Number((b.turnover_value / 1_000_000).toFixed(2)),
      market_share_pct: totalTurnoverValue > 0 ? Number(((b.turnover_value / totalTurnoverValue) * 100).toFixed(2)) : 0,
      weighted_change_pct: b.turnover_value > 0 ? Number((b.weighted_change_num / b.turnover_value).toFixed(2)) : 0,
      weighted_cmf_20: b.turnover_value > 0 ? Number((b.weighted_cmf_num / b.turnover_value).toFixed(3)) : 0,
      stocks_count: b.stocks_count,
      advancing: b.advancing,
      declining: b.declining,
      top_stock_symbol: b.top_stock_symbol,
      top_stock_name: b.top_stock_name,
      top_stock_turnover_million_egp: Number((b.top_stock_turnover_value / 1_000_000).toFixed(2)),
      top_stock_change_pct: Number(b.top_stock_change_pct.toFixed(2)),
    }));

  const topLiquidityStocks = stocksByTurnover.slice(0, 8).map((s) => ({
    symbol: s.symbol,
    name: s.name,
    sector: s.sector,
    sector_ar: s.sector_ar,
    close: Number(s.close.toFixed(2)),
    change_pct: Number(s.change_pct.toFixed(2)),
    turnover_million_egp: Number((s.turnover_egp / 1_000_000).toFixed(2)),
    market_share_pct: totalTurnoverValue > 0 ? Number(((s.turnover_egp / totalTurnoverValue) * 100).toFixed(2)) : 0,
    r_vol: s.r_vol,
    cmf_20: s.cmf_20,
    rsi_14: Number(s.rsi_14.toFixed(0)),
  }));

  const flowVerdict: "inflow" | "outflow" | "balanced" =
    advancingTurnoverPct >= 58
      ? "inflow"
      : decliningTurnoverPct >= 58
        ? "outflow"
        : "balanced";

  const flowVerdictAr =
    flowVerdict === "inflow"
      ? "دخول سيولة شرائية وتجميع"
      : flowVerdict === "outflow"
        ? "ضغط بيعي وتصريف سيولة"
        : "توازن وتدوير سيولة انتقائي";

  const flowVerdictEn =
    flowVerdict === "inflow"
      ? "Net Liquidity Inflow & Accumulation"
      : flowVerdict === "outflow"
        ? "Selling Pressure & Liquidity Outflow"
        : "Balanced & Selective Rotation";

  const leadSector = topSectors[0];
  const leadStock = topLiquidityStocks[0];
  const dailySummaryAr = `بلغ إجمالي السيولة المتداولة في السوق ${totalTurnoverBillion.toFixed(2)} مليار ${currencyLabelAr} (${totalTurnoverMillion.toLocaleString("en-US")} مليون ${currencyLabelAr}) بنسبة ${turnoverVs20dPct.toFixed(1)}% من متوسط 20 جلسة (${avg20dTurnoverMillion.toLocaleString("en-US")} مليون ${currencyLabelAr}). استحوذت الأسهم الصاعدة على ${advancingTurnoverPct.toFixed(1)}% من السيولة مقابل ${decliningTurnoverPct.toFixed(1)}% للأسهم الهابطة${leadSector ? `، وتصدر قطاع «${leadSector.sector_ar}» التداولات بحصة ${leadSector.market_share_pct.toFixed(1)}%` : ""}${leadStock ? ` بقيادة سهم ${leadStock.symbol} (${leadStock.turnover_million_egp.toFixed(1)} مليون ${currencyLabelAr})` : ""}.`;
  const dailySummaryEn = `Total market turnover reached ${totalTurnoverBillion.toFixed(2)}B ${currency} (${totalTurnoverMillion.toLocaleString("en-US")}M ${currency}), at ${turnoverVs20dPct.toFixed(1)}% of the 20-day average (${avg20dTurnoverMillion.toLocaleString("en-US")}M ${currency}). Advancing stocks captured ${advancingTurnoverPct.toFixed(1)}% of liquidity vs ${decliningTurnoverPct.toFixed(1)}% in declining stocks${leadSector ? `, led by ${leadSector.sector} (${leadSector.market_share_pct.toFixed(1)}% share)` : ""}${leadStock ? ` and top stock ${leadStock.symbol} (${leadStock.turnover_million_egp.toFixed(1)}M ${currency})` : ""}.`;

  return {
    market,
    exchange,
    currency,
    health_score: healthScore,
    health_label: healthLabel,
    advancing,
    declining,
    unchanged,
    pct_above_ema50: pctAboveEma50,
    pct_above_ema200: pctAboveEma200,
    avg_rsi: avgRsi,
    volume_ratio: avgVolRatio,
    top_gainers: topGainers,
    top_losers: topLosers,
    date: latestDate,
    total_stocks: totalStocks,
    liquidity: {
      market,
      exchange,
      currency,
      date: latestDate,
      total_turnover_egp: Math.round(totalTurnoverValue),
      total_turnover_million_egp: totalTurnoverMillion,
      total_turnover_billion_egp: totalTurnoverBillion,
      avg_20d_turnover_million_egp: avg20dTurnoverMillion,
      turnover_vs_20d_ratio: turnoverVs20dRatio,
      turnover_vs_20d_pct: turnoverVs20dPct,
      advancing_turnover_million_egp: advancingTurnoverMillion,
      advancing_turnover_pct: advancingTurnoverPct,
      declining_turnover_million_egp: decliningTurnoverMillion,
      declining_turnover_pct: decliningTurnoverPct,
      unchanged_turnover_million_egp: unchangedTurnoverMillion,
      unchanged_turnover_pct: unchangedTurnoverPct,
      top5_concentration_pct: top5ConcentrationPct,
      top10_concentration_pct: top10ConcentrationPct,
      unusual_volume_surge_count: unusualVolumeSurgeCount,
      positive_cmf_count: positiveCmfCount,
      negative_cmf_count: negativeCmfCount,
      accumulation_count: accumulationCount,
      strong_accumulation_count: strongAccumulationCount,
      distribution_count: distributionCount,
      strong_distribution_count: strongDistributionCount,
      flow_verdict: flowVerdict,
      flow_verdict_ar: flowVerdictAr,
      flow_verdict_en: flowVerdictEn,
      daily_summary_ar: dailySummaryAr,
      daily_summary_en: dailySummaryEn,
      top_sectors: topSectors,
      top_liquidity_stocks: topLiquidityStocks,
    },
  };
}

const computeEgxMarketBreadth = unstable_cache(
  async () => loadMarketBreadth("egx"),
  ["market-breadth-egx-v1"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

const computeTasiMarketBreadth = unstable_cache(
  async () => loadMarketBreadth("tasi"),
  ["market-breadth-tasi-v1"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const market = resolveRequestMarket(req);
    const explicitMarketParam =
      url.searchParams.has("market") ||
      url.searchParams.has("country") ||
      url.searchParams.has("exchange");
    const headers = explicitMarketParam ? PUBLIC_CACHE_HEADERS : PRIVATE_NO_STORE_HEADERS;

    const payload =
      market === "tasi"
        ? await computeTasiMarketBreadth()
        : await computeEgxMarketBreadth();
    if (!payload) {
      return NextResponse.json(
        { error: "Failed to fetch indicators" },
        { status: 500, headers: PRIVATE_NO_STORE_HEADERS },
      );
    }
    return NextResponse.json(payload, { headers });
  } catch (error) {
    console.error("Breadth API error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500, headers: PRIVATE_NO_STORE_HEADERS },
    );
  }
}
