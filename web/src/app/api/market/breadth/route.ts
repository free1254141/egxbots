import { NextResponse } from "next/server";
import { unstable_cache } from "next/cache";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { DAILY_CACHE_TAGS, dailyCacheHeaders } from "@/lib/cache/daily";

export const runtime = "nodejs";
export const revalidate = 86400;
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

const PUBLIC_CACHE_HEADERS = dailyCacheHeaders(DAILY_CACHE_TAGS.market);

function classifyEgxSector(rawSector: string, rawIndustry: string): { sector: string; sector_ar: string } {
  const ind = String(rawIndustry || "").toLowerCase();
  const sec = String(rawSector || "").toLowerCase();
  const combined = `${ind} ${sec}`;
  if (ind.includes("real estate") || ind.includes("homebuilding") || combined.includes("عقار")) {
    return { sector: "Real Estate", sector_ar: "العقارات والتطوير العقاري" };
  }
  if ((ind.includes("bank") && !ind.includes("investment") && !ind.includes("broker")) || combined.includes("بنوك")) {
    return { sector: "Banks", sector_ar: "البنوك" };
  }
  if (sec.includes("finance") || ind.includes("financial") || ind.includes("investment") || ind.includes("insurance") || combined.includes("مالية")) {
    return { sector: "Financial Services", sector_ar: "الخدمات المالية غير المصرفية" };
  }
  if (combined.includes("chemical") || combined.includes("fertilizer") || combined.includes("petrochemical") || combined.includes("كيماويات") || combined.includes("أسمدة")) {
    return { sector: "Chemicals & Fertilizers", sector_ar: "الكيماويات والأسمدة والبتروكيماويات" };
  }
  if (combined.includes("construction") || combined.includes("engineering") || combined.includes("contracting") || combined.includes("cement") || combined.includes("building") || combined.includes("مقاولات") || combined.includes("بناء") || combined.includes("تشييد")) {
    return { sector: "Construction & Building Materials", sector_ar: "التشييد ومواد البناء" };
  }
  if (combined.includes("steel") || combined.includes("mining") || combined.includes("metal") || combined.includes("non-energy minerals") || combined.includes("حديد") || combined.includes("تعدين") || combined.includes("material")) {
    return { sector: "Basic Resources & Metals", sector_ar: "الموارد الأساسية والمعادن" };
  }
  if (combined.includes("food") || combined.includes("beverage") || combined.includes("milling") || combined.includes("poultry") || combined.includes("agricultural") || combined.includes("consumer non-durables") || combined.includes("أغذية") || combined.includes("مشروبات")) {
    return { sector: "Food & Beverages", sector_ar: "الأغذية والمشروبات والزراعة" };
  }
  if (combined.includes("pharma") || combined.includes("health") || combined.includes("medical") || combined.includes("hospital") || combined.includes("أدوية")) {
    return { sector: "Healthcare & Pharmaceuticals", sector_ar: "الرعاية الصحية والأدوية" };
  }
  if (combined.includes("telecom") || combined.includes("technology") || combined.includes("communications") || combined.includes("software") || combined.includes("electronic") || combined.includes("اتصالات")) {
    return { sector: "Telecom & Technology", sector_ar: "الاتصالات وتكنولوجيا المعلومات" };
  }
  if (combined.includes("energy") || combined.includes("oil") || combined.includes("gas") || combined.includes("utilities") || combined.includes("طاقة") || combined.includes("مرافق")) {
    return { sector: "Energy & Utilities", sector_ar: "الطاقة والمرافق" };
  }
  if (combined.includes("transport") || combined.includes("shipping") || combined.includes("logistics") || combined.includes("container")) {
    return { sector: "Transportation & Shipping", sector_ar: "النقل والشحن والخدمات اللوجستية" };
  }
  if (combined.includes("tourism") || combined.includes("hotel") || combined.includes("resort") || combined.includes("consumer services")) {
    return { sector: "Tourism & Leisure", sector_ar: "السياحة والترفيه" };
  }
  if (combined.includes("industrial") || combined.includes("manufacturing") || combined.includes("paper") || combined.includes("صناعات")) {
    return { sector: "Industrial Goods", sector_ar: "الصناعات التحويلية والسلع الصناعية" };
  }
  return { sector: "Other Sectors", sector_ar: "قطاعات متنوعة أخرى" };
}

const computeMarketBreadth = unstable_cache(
  async () => {
    const supabase = getSupabaseClient();

    // 1. Get the latest available date for EGX
    const { data: dateRows, error: dateError } = await supabase
      .from("stock_technical_indicators")
      .select("date")
      .eq("exchange", "EGX")
      .order("date", { ascending: false })
      .limit(1);

    if (dateError || !dateRows || dateRows.length === 0) {
      console.error("Failed to fetch latest technical indicator date:", dateError);
      return null;
    }

    const latestDate = dateRows[0].date;

    // 2. Fetch indicators, fundamentals, and latest scan scores in parallel with strict column projection & limits
    const [
      { data: indicators, error: indError },
      { data: fundRows },
      { data: scanRows },
    ] = await Promise.all([
      supabase
        .from("stock_technical_indicators")
        .select("symbol, close, volume, ema_50, ema_200, rsi_14, vol_sma20, r_vol, cmf_20, change_pct")
        .eq("exchange", "EGX")
        .eq("date", latestDate)
        .limit(500),
      supabase
        .from("stock_fundamentals")
        .select("symbol, name, name_ar, data")
        .eq("exchange", "EGX")
        .limit(500),
      supabase
        .from("stock_scans_summary")
        .select("symbol, scan_date, acc_score, dist_score, wyckoff_phase")
        .eq("scan_date", latestDate)
        .order("acc_score", { ascending: false })
        .limit(500),
    ]);

    if (indError || !indicators || indicators.length === 0) {
      console.error("Failed to fetch indicators for date:", latestDate, indError);
      return null;
    }

    const nameMap = new Map<string, string>();
    const sectorMap = new Map<string, { sector: string; sector_ar: string }>();
    if (fundRows) {
      for (const row of fundRows as any[]) {
        const sym = String(row.symbol || "").toUpperCase();
        const payload = row.data || {};
        const name = row.name_ar || row.name || payload.name_ar || payload.name || payload.Name || "";
        const rawSector = payload.sector || payload.Sector || "";
        const rawIndustry = payload.industry || payload.Industry || "";
        if (name) {
          nameMap.set(sym, name);
        }
        sectorMap.set(sym, classifyEgxSector(rawSector, rawIndustry));
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

    let totalTurnoverEgp = 0;
    let avg20dTurnoverEgp = 0;
    let advancingTurnoverEgp = 0;
    let decliningTurnoverEgp = 0;
    let unchangedTurnoverEgp = 0;
    let unusualVolumeSurgeCount = 0;
    let positiveCmfCount = 0;
    let negativeCmfCount = 0;

    const sectorBuckets = new Map<string, {
      sector: string;
      sector_ar: string;
      turnover_egp: number;
      weighted_change_num: number;
      weighted_cmf_num: number;
      stocks_count: number;
      advancing: number;
      declining: number;
      top_stock_symbol: string;
      top_stock_name: string;
      top_stock_turnover_egp: number;
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
      const volSma = Number(ind.vol_sma20 || 0);
      const rVol = ind.r_vol != null ? Number(ind.r_vol) : (vol && volSma ? vol / volSma : 0);
      const cmf20 = ind.cmf_20 != null ? Number(ind.cmf_20) : 0;

      if (vol && volSma) {
        volRatioSum += vol / volSma;
        volRatioCount++;
      }
      if (rVol >= 2.0) unusualVolumeSurgeCount++;
      if (cmf20 > 0.05) positiveCmfCount++;
      else if (cmf20 < -0.05) negativeCmfCount++;

      const turnoverEgp = close * Math.max(0, vol);
      const avgStockTurnover20d = close * Math.max(0, volSma);
      totalTurnoverEgp += turnoverEgp;
      avg20dTurnoverEgp += avgStockTurnover20d;

      if (changePct > 0) advancingTurnoverEgp += turnoverEgp;
      else if (changePct < 0) decliningTurnoverEgp += turnoverEgp;
      else unchangedTurnoverEgp += turnoverEgp;

      const stockName = nameMap.get(sym) || sym;
      const sectorInfo = sectorMap.get(sym) || { sector: "Other Sectors", sector_ar: "قطاعات متنوعة أخرى" };
      const sector = sectorInfo.sector;
      const sectorAr = sectorInfo.sector_ar;

      if (turnoverEgp > 0) {
        if (!sectorBuckets.has(sector)) {
          sectorBuckets.set(sector, {
            sector,
            sector_ar: sectorAr,
            turnover_egp: 0,
            weighted_change_num: 0,
            weighted_cmf_num: 0,
            stocks_count: 0,
            advancing: 0,
            declining: 0,
            top_stock_symbol: sym,
            top_stock_name: stockName,
            top_stock_turnover_egp: turnoverEgp,
            top_stock_change_pct: changePct,
          });
        }
        const b = sectorBuckets.get(sector)!;
        b.turnover_egp += turnoverEgp;
        b.weighted_change_num += changePct * turnoverEgp;
        b.weighted_cmf_num += cmf20 * turnoverEgp;
        b.stocks_count += 1;
        if (changePct > 0) b.advancing += 1;
        else if (changePct < 0) b.declining += 1;
        if (turnoverEgp > b.top_stock_turnover_egp) {
          b.top_stock_symbol = sym;
          b.top_stock_name = stockName;
          b.top_stock_turnover_egp = turnoverEgp;
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
        turnover_egp: turnoverEgp,
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

    const totalTurnoverMillion = Number((totalTurnoverEgp / 1_000_000).toFixed(2));
    const totalTurnoverBillion = Number((totalTurnoverEgp / 1_000_000_000).toFixed(3));
    const avg20dTurnoverMillion = Number((avg20dTurnoverEgp / 1_000_000).toFixed(2));
    const turnoverVs20dRatio = avg20dTurnoverEgp > 0 ? Number((totalTurnoverEgp / avg20dTurnoverEgp).toFixed(2)) : 1;
    const turnoverVs20dPct = avg20dTurnoverEgp > 0 ? Number(((totalTurnoverEgp / avg20dTurnoverEgp) * 100).toFixed(2)) : 100;

    const advancingTurnoverMillion = Number((advancingTurnoverEgp / 1_000_000).toFixed(2));
    const decliningTurnoverMillion = Number((decliningTurnoverEgp / 1_000_000).toFixed(2));
    const unchangedTurnoverMillion = Number((unchangedTurnoverEgp / 1_000_000).toFixed(2));
    const advancingTurnoverPct = totalTurnoverEgp > 0 ? Number(((advancingTurnoverEgp / totalTurnoverEgp) * 100).toFixed(2)) : 0;
    const decliningTurnoverPct = totalTurnoverEgp > 0 ? Number(((decliningTurnoverEgp / totalTurnoverEgp) * 100).toFixed(2)) : 0;
    const unchangedTurnoverPct = totalTurnoverEgp > 0 ? Number(((unchangedTurnoverEgp / totalTurnoverEgp) * 100).toFixed(2)) : 0;

    const top5ConcentrationPct = totalTurnoverEgp > 0 ? Number(((top5TurnoverSum / totalTurnoverEgp) * 100).toFixed(2)) : 0;
    const top10ConcentrationPct = totalTurnoverEgp > 0 ? Number(((top10TurnoverSum / totalTurnoverEgp) * 100).toFixed(2)) : 0;

    const topSectors = Array.from(sectorBuckets.values())
      .sort((a, b) => b.turnover_egp - a.turnover_egp)
      .slice(0, 6)
      .map((b) => ({
        sector: b.sector,
        sector_ar: b.sector_ar,
        turnover_million_egp: Number((b.turnover_egp / 1_000_000).toFixed(2)),
        market_share_pct: totalTurnoverEgp > 0 ? Number(((b.turnover_egp / totalTurnoverEgp) * 100).toFixed(2)) : 0,
        weighted_change_pct: b.turnover_egp > 0 ? Number((b.weighted_change_num / b.turnover_egp).toFixed(2)) : 0,
        weighted_cmf_20: b.turnover_egp > 0 ? Number((b.weighted_cmf_num / b.turnover_egp).toFixed(3)) : 0,
        stocks_count: b.stocks_count,
        advancing: b.advancing,
        declining: b.declining,
        top_stock_symbol: b.top_stock_symbol,
        top_stock_name: b.top_stock_name,
        top_stock_turnover_million_egp: Number((b.top_stock_turnover_egp / 1_000_000).toFixed(2)),
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
      market_share_pct: totalTurnoverEgp > 0 ? Number(((s.turnover_egp / totalTurnoverEgp) * 100).toFixed(2)) : 0,
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
    const dailySummaryAr = `بلغ إجمالي السيولة المتداولة في السوق ${totalTurnoverBillion.toFixed(2)} مليار ج.م (${totalTurnoverMillion.toLocaleString("en-US")} مليون ج.م) بنسبة ${turnoverVs20dPct.toFixed(1)}% من متوسط 20 جلسة (${avg20dTurnoverMillion.toLocaleString("en-US")} مليون ج.م). استحوذت الأسهم الصاعدة على ${advancingTurnoverPct.toFixed(1)}% من السيولة مقابل ${decliningTurnoverPct.toFixed(1)}% للأسهم الهابطة${leadSector ? `، وتصدر قطاع «${leadSector.sector_ar}» التداولات بحصة ${leadSector.market_share_pct.toFixed(1)}%` : ""}${leadStock ? ` بقيادة سهم ${leadStock.symbol} (${leadStock.turnover_million_egp.toFixed(1)} مليون ج.م)` : ""}.`;
    const dailySummaryEn = `Total market turnover reached ${totalTurnoverBillion.toFixed(2)}B EGP (${totalTurnoverMillion.toLocaleString("en-US")}M EGP), at ${turnoverVs20dPct.toFixed(1)}% of the 20-day average (${avg20dTurnoverMillion.toLocaleString("en-US")}M EGP). Advancing stocks captured ${advancingTurnoverPct.toFixed(1)}% of liquidity vs ${decliningTurnoverPct.toFixed(1)}% in declining stocks${leadSector ? `, led by ${leadSector.sector} (${leadSector.market_share_pct.toFixed(1)}% share)` : ""}${leadStock ? ` and top stock ${leadStock.symbol} (${leadStock.turnover_million_egp.toFixed(1)}M EGP)` : ""}.`;

    return {
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
        date: latestDate,
        total_turnover_egp: Math.round(totalTurnoverEgp),
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
  },
  ["market-breadth-egx-daily"],
  { revalidate: 86400, tags: [DAILY_CACHE_TAGS.market] }
);

export async function GET() {
  try {
    const payload = await computeMarketBreadth();
    if (!payload) {
      return NextResponse.json({ error: "Failed to fetch indicators" }, { status: 500 });
    }
    return NextResponse.json(payload, { headers: PUBLIC_CACHE_HEADERS });
  } catch (error) {
    console.error("Breadth API error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
