import {
  computeFairValueReport,
  computeSingleStockFairValue,
} from "../market/fair-value";
import { getCachedFairValueReport } from "../market/fair-value-server";
import { isShariaCompliant } from "../shariaStocks";
import { getCanonicalStockName } from "./stock-names";

const SECTOR_PURIFICATION_RATES: Record<string, number> = {
  اتصالات: 2.8,
  "تكنولوجيا مالية": 2.2,
  "تكنولوجيا ومدفوعات رقمية": 2.2,
  عقارات: 3.5,
  "عقارات وإنشاءات": 3.5,
  "كيماويات وأسمدة": 2.4,
  "أسمدة وكيماويات": 2.4,
  "صناعي وهندسي": 2.9,
  "صناعات هندسية وكهربائية": 2.9,
  "رعاية صحية وأدوية": 1.8,
  "أغذية ومشروبات": 2.1,
  "أغذية ودواجن": 1.9,
  "طاقة وبترول": 2.6,
};

export async function executeFairValueTool(args: any, db: any): Promise<any> {
  try {
    const symbols: string[] = Array.isArray(args.symbols)
      ? args.symbols.map((s: string) =>
          String(s).trim().toUpperCase().replace(/\.CA$/i, "")
        )
      : [];
    const shariaOnly = Boolean(args.sharia_only);
    const mode =
      args.mode || (symbols.length > 0 ? "specific_stocks" : "screen_undervalued");
    const limit =
      Number.isInteger(args.limit) && args.limit > 0 && args.limit <= 20
        ? args.limit
        : 10;

    if (symbols.length > 0 || mode === "specific_stocks") {
      const [fundRes, indRes] = await Promise.all([
        db
          .from("stock_fundamentals")
          .select("symbol, name, name_ar, data")
          .eq("exchange", "EGX")
          .in("symbol", symbols)
          .limit(10),
        db
          .from("stock_technical_indicators")
          .select(
            "symbol, date, close, change_pct, volume, ema_50, ema_200, sma_200, vwap_20, rsi_14"
          )
          .eq("exchange", "EGX")
          .in("symbol", symbols)
          .order("date", { ascending: false })
          .limit(20),
      ]);

      const indMap = new Map<string, any>();
      for (const r of indRes.data || []) {
        if (!indMap.has(r.symbol)) indMap.set(r.symbol, r);
      }
      const fundMap = new Map<string, any>();
      for (const r of fundRes.data || []) {
        if (!fundMap.has(r.symbol)) fundMap.set(r.symbol, r);
      }

      const results = symbols.map((sym) => {
        const ind = indMap.get(sym);
        const fund = fundMap.get(sym);
        const close = Number(ind?.close || 0);
        if (!close || close <= 0) {
          return {
            symbol: sym,
            availability: "missing",
            message: `لا تتوفر أسعار مؤرخة لحساب السعر العادل للسهم ${sym}`,
          };
        }
        const val = computeSingleStockFairValue({
          symbol: sym,
          close,
          fundRow: fund,
          fundData: fund?.data,
          latestTech: ind,
        });
        return {
          symbol: sym,
          name_ar: val.nameAr,
          sector_ar: val.sectorAr,
          date: val.date,
          close: val.currentPrice,
          fair_value: val.fairValue,
          upside_pct: val.upsidePct,
          status: val.status,
          status_ar:
            val.status === "undervalued"
              ? "أقل من السعر العادل (رخيص) 🟢"
              : val.status === "overvalued"
              ? "أعلى من السعر العادل (متضخم) 🔴"
              : "في النطاق العادل ⚖️",
          model_type: val.modelType,
          model_label_ar: val.modelLabelAr,
          formula_ar: val.formulaSubstitutionAr,
          calculation_steps_ar: val.formulaStepsAr,
          eps: val.eps,
          bvps: val.bvps,
          pe_ratio: val.peRatio,
          pb_ratio: val.pbRatio,
          is_sharia_compliant: val.isSharia,
          sharia_index: val.isSharia ? "EGX33" : null,
        };
      });

      return {
        status: "success",
        mode: "specific_stocks",
        count: results.length,
        stocks: results,
      };
    }

    let report;
    try {
      report = await getCachedFairValueReport();
    } catch {
      const [fundRes, indRes] = await Promise.all([
        db
          .from("stock_fundamentals")
          .select("symbol, name, name_ar, data")
          .eq("exchange", "EGX")
          .limit(400),
        db
          .from("stock_technical_indicators")
          .select(
            "symbol, date, close, change_pct, volume, ema_50, ema_200, sma_200, vwap_20, rsi_14"
          )
          .eq("exchange", "EGX")
          .order("date", { ascending: false })
          .limit(400),
      ]);
      report = computeFairValueReport(fundRes.data || [], indRes.data || []);
    }

    let candidates = report.stocks || [];
    if (shariaOnly) {
      candidates = candidates.filter((s: any) => s.isSharia);
    }

    if (mode === "screen_overvalued") {
      candidates.sort((a: any, b: any) => a.upsidePct - b.upsidePct);
    } else {
      candidates.sort((a: any, b: any) => b.upsidePct - a.upsidePct);
    }

    const top = candidates.slice(0, limit).map((s: any) => ({
      symbol: s.symbol,
      name_ar: s.nameAr,
      sector_ar: s.sectorAr,
      date: s.date,
      close: s.currentPrice,
      fair_value: s.fairValue,
      upside_pct: s.upsidePct,
      status: s.status,
      status_ar:
        s.status === "undervalued"
          ? "أقل من السعر العادل (رخيص) 🟢"
          : s.status === "overvalued"
          ? "أعلى من السعر العادل (متضخم) 🔴"
          : "في النطاق العادل ⚖️",
      model_type: s.modelType,
      model_label_ar: s.modelLabelAr,
      formula_ar: s.formulaSubstitutionAr,
      calculation_steps_ar: s.formulaStepsAr,
      eps: s.eps,
      bvps: s.bvps,
      pe_ratio: s.peRatio,
      pb_ratio: s.pbRatio,
      is_sharia_compliant: s.isSharia,
      sharia_index: s.isSharia ? "EGX33" : null,
    }));

    return {
      status: "success",
      mode,
      sharia_only: shariaOnly,
      total_evaluated: report.summary.totalEvaluated,
      undervalued_count: report.summary.undervaluedCount,
      fair_count: report.summary.fairCount,
      overvalued_count: report.summary.overvaluedCount,
      count: top.length,
      stocks: top,
    };
  } catch (e: any) {
    return { status: "error", message: e.message || "تعذر فحص السعر العادل" };
  }
}

export async function executeShariaCleanserTool(
  args: any,
  db: any
): Promise<any> {
  const symbol = String(args.symbol || args.symbols?.[0] || "")
    .trim()
    .toUpperCase()
    .replace(/\.CA$/i, "");
  if (!symbol)
    return { status: "error", message: "رمز السهم مطلوب للفحص الشرعي" };

  const canonical = getCanonicalStockName(symbol);
  const compliant = isShariaCompliant(symbol);

  if (!compliant) {
    return {
      status: "success",
      symbol,
      name_ar: canonical.name_ar,
      is_sharia_compliant: false,
      sharia_index: null,
      verdict_ar: "غير متوافق مع معايير الشريعة الإسلامية ❌",
      message: `السهم ${symbol} (${canonical.name_ar}) غير مدرج ضمن قائمة الأسهم المتوافقة مع الشريعة الإسلامية ومؤشر EGX 33 الشريعي المعتمد من الرقابة المالية نظراً لتجاوز نسب المديونية أو الفوائد أو طبيعة النشاط المالي التقليدي. لا تجوز المضاربة أو الاستثمار فيه لمن يتحرى الضوابط الشرعية.`,
    };
  }

  const sector = canonical.sector || "قطاعات متنوعة";
  const defaultPurification = SECTOR_PURIFICATION_RATES[sector] || 2.5;
  const purificationRatePct = Number(
    args.purification_rate_pct ?? defaultPurification
  );
  const sharesCount = Number(args.shares_count ?? 1000);
  const coupon = Number(args.coupon_per_share ?? 1.0);

  const totalDividend = Number((sharesCount * coupon).toFixed(2));
  const purificationAmount = Number(
    (totalDividend * (purificationRatePct / 100)).toFixed(2)
  );
  const netHalalDividend = Number(
    (totalDividend - purificationAmount).toFixed(2)
  );

  const { data: indRows } = await db
    .from("stock_technical_indicators")
    .select("close, date")
    .eq("exchange", "EGX")
    .eq("symbol", symbol)
    .order("date", { ascending: false })
    .limit(1);
  const close = Number(indRows?.[0]?.close || 0);
  const marketValue =
    close > 0 ? Number((sharesCount * close).toFixed(2)) : null;
  const zakatTradingEgp = marketValue
    ? Number((marketValue * 0.025).toFixed(2))
    : null;

  return {
    status: "success",
    symbol,
    name_ar: canonical.name_ar,
    sector_ar: sector,
    is_sharia_compliant: true,
    sharia_index: "EGX33",
    verdict_ar: "متوافق مع الشريعة الإسلامية ومؤشر EGX 33 ✅",
    purification_rate_pct: purificationRatePct,
    purification_basis_ar: `نسبة تطهير تقديرية (${purificationRatePct}%) لتطهير عوائد الفوائد البنكية وأذون الخزانة غير التشغيلية لقطاع ${sector}.`,
    dividend_purification: {
      shares_count: sharesCount,
      coupon_per_share_egp: coupon,
      total_dividend_egp: totalDividend,
      purification_amount_egp: purificationAmount,
      net_halal_dividend_egp: netHalalDividend,
      formula_ar: `${sharesCount} سهم × ${coupon} ج.م = ${totalDividend} ج.م | نسبة التطهير (${purificationRatePct}%) = ${purificationAmount} ج.م تخرج صدقة دون احتسابها زكاة.`,
    },
    ...(zakatTradingEgp
      ? {
          zakat_calculation: {
            shares_count: sharesCount,
            current_price_egp: close,
            total_market_value_egp: marketValue,
            zakat_due_egp: zakatTradingEgp,
            formula_ar: `زكاة أسهم المضاربة والتجارة (2.5% على القيمة السوقية إذا دار عليها الحول وبلغت النصاب): ${marketValue} ج.م × 2.5% = ${zakatTradingEgp} ج.م.`,
          },
        }
      : {}),
  };
}

export async function executePriceTrapsTool(
  args: any,
  db: any,
  isPro: boolean
): Promise<any> {
  try {
    const trapType = args.trap_type || "all";
    const { data: cacheRow } = await db
      .from("market_cache")
      .select("payload, updated_at")
      .eq("cache_key", "scanner_traps_EGX")
      .limit(1)
      .maybeSingle();

    const payload = cacheRow?.payload || {};
    const bearTraps = Array.isArray(payload.bearTraps) ? payload.bearTraps : [];
    const bullTraps = Array.isArray(payload.bullTraps) ? payload.bullTraps : [];

    const totalBear = payload.totalBearTraps ?? bearTraps.length;
    const totalBull = payload.totalBullTraps ?? bullTraps.length;

    // Free user: MASK & ENCRYPT SYMBOLS
    if (!isPro) {
      const maskTrap = (row: any) => ({
        symbol: "🔒 [سهم محمي لمشتركي PRO]",
        name_ar: "🔒 [اشترك في PRO لإظهار كود السهم]",
        trap_type: row.trapType,
        trap_label:
          row.trapType === "BEAR_TRAP"
            ? "كسر وهمي ارتدادي (Wyckoff Spring 🟢)"
            : "اختراق كاذب للتصريف (Upthrust 🔴)",
        wick_rebound_pct: row.wickPct,
        conviction_score: row.conviction,
        is_locked: true,
      });

      return {
        status: "success",
        is_pro: false,
        access_tier: "free",
        as_of: payload.asOf || "أحدث جلسة إغلاق",
        total_bear_traps: totalBear,
        total_bull_traps: totalBull,
        bear_traps: (trapType === "BULL_TRAP" ? [] : bearTraps).map(maskTrap),
        bull_traps: (trapType === "BEAR_TRAP" ? [] : bullTraps).map(maskTrap),
        upgrade_message: `تم رصد ${totalBear} مصيدة دببة ارتدادية (Spring) و${totalBull} مصيدة ثيران وهمية (Upthrust) لإغلاق الجلسة. تفاصيل الأكواد والأسعار مشفرة لحسابات Free ومتاحة حصرياً لمشتركي Pro. يمكنك الترقية لباقة Pro لفك التشفير اللحظي في الشات والمنصة.`,
      };
    }

    // Pro user: return full unmasked symbols
    const filterTraps = (list: any[]) =>
      list.map((r) => ({
        symbol: r.symbol,
        name_ar: r.nameAr,
        trap_type: r.trapType,
        trap_label:
          r.trapType === "BEAR_TRAP"
            ? "كسر وهمي ارتدادي (Wyckoff Spring 🟢)"
            : "اختراق كاذب للتصريف (Upthrust 🔴)",
        close: r.close,
        key_level: r.keyLevel,
        wick_rebound_pct: r.wickPct,
        conviction_score: r.conviction,
        is_locked: false,
      }));

    return {
      status: "success",
      is_pro: true,
      access_tier: "pro",
      as_of: payload.asOf || "أحدث جلسة إغلاق",
      total_bear_traps: totalBear,
      total_bull_traps: totalBull,
      bear_traps: trapType === "BULL_TRAP" ? [] : filterTraps(bearTraps),
      bull_traps: trapType === "BEAR_TRAP" ? [] : filterTraps(bullTraps),
      note: "إشارات المصائد اليومية متاحة بالكامل لحساب Pro مع مستويات الدعم والمقاومة ونسب الارتداد وقوة الإشارة.",
    };
  } catch (e: any) {
    return {
      status: "error",
      message: e.message || "تعذر قراءة مصائد الأسعار",
    };
  }
}

export async function executeRebalancePortfolioTool(
  args: any,
  db: any,
  userId: string
): Promise<any> {
  if (!userId) {
    return {
      status: "unauthenticated",
      message: "يلزم تسجيل الدخول لفحص محفظتك وإعادة توازنها.",
    };
  }

  const { data: posRows } = await db
    .from("positions")
    .select("symbol, quantity, entry_price")
    .eq("user_id", userId)
    .eq("status", "open")
    .limit(20);

  const positions = posRows || [];
  if (positions.length === 0) {
    return {
      status: "success",
      empty: true,
      message:
        "لا توجد مراكز مفتوحة مسجلة في محفظتك حالياً. يمكنك تسجيل أسهمك أولاً عبر الشات أو من صفحة المحفظة لتشخيص رأس المال الميت.",
    };
  }

  const symbols = positions.map((p: any) => p.symbol);
  const [indRes, wyckoffRes, fundRes] = await Promise.all([
    db
      .from("stock_technical_indicators")
      .select(
        "symbol, date, close, change_pct, ema_50, ema_200, rsi_14, r_vol"
      )
      .eq("exchange", "EGX")
      .in("symbol", symbols)
      .order("date", { ascending: false })
      .limit(symbols.length * 2),
    db
      .from("stock_scans_summary")
      .select("symbol, acc_score, dist_score, consecutive_dist_days")
      .in("symbol", symbols)
      .order("scan_date", { ascending: false })
      .limit(symbols.length * 2),
    db
      .from("stock_fundamentals")
      .select("symbol, data")
      .eq("exchange", "EGX")
      .in("symbol", symbols)
      .limit(symbols.length),
  ]);

  const indMap = new Map();
  for (const r of indRes.data || []) {
    if (!indMap.has(r.symbol)) indMap.set(r.symbol, r);
  }
  const wyckoffMap = new Map();
  for (const r of wyckoffRes.data || []) {
    if (!wyckoffMap.has(r.symbol)) wyckoffMap.set(r.symbol, r);
  }
  const fundMap = new Map();
  for (const r of fundRes.data || []) {
    if (!fundMap.has(r.symbol)) fundMap.set(r.symbol, r);
  }

  const deadCapital: any[] = [];
  const healthy: any[] = [];

  for (const p of positions) {
    const ind = indMap.get(p.symbol);
    const wyckoff = wyckoffMap.get(p.symbol) || {};
    const fund = fundMap.get(p.symbol);
    const close = Number(ind?.close || p.entry_price || 0);

    const val = computeSingleStockFairValue({
      symbol: p.symbol,
      close,
      fundRow: fund,
      fundData: fund?.data,
      latestTech: ind,
    });

    const entry = Number(p.entry_price || 0);
    const plPct =
      entry > 0 && close > 0
        ? Number((((close - entry) / entry) * 100).toFixed(1))
        : null;
    const distScore = Number(wyckoff.dist_score || 0);
    const isDistributing =
      distScore >= 60 || Number(wyckoff.consecutive_dist_days || 0) >= 3;
    const belowAverages =
      ind?.ema_50 && ind?.ema_200 && close < ind.ema_50 && close < ind.ema_200;
    const isOvervalued = val.upsidePct < -15;

    const isDeadCapital =
      isDistributing || (belowAverages && (plPct === null || plPct < -8)) || isOvervalued;

    const item = {
      symbol: p.symbol,
      name_ar: val.nameAr,
      quantity: p.quantity,
      entry_price: entry,
      current_price: close,
      profit_loss_pct: plPct,
      fair_value: val.fairValue,
      upside_pct: val.upsidePct,
      diagnosis: isDeadCapital
        ? "رأس مال ميت / ضغط بيعي وتصريف ⚠️"
        : "مركز سليم للمتابعة ✅",
      reason: isDistributing
        ? `السهم في مسار تصريف (ضغط بيعي ${distScore}%)`
        : isOvervalued
        ? `السهم متضخم سعرياً ويتداول بعلاوة ${Math.abs(val.upsidePct)}% فوق قيمته العادلة`
        : belowAverages
        ? "السهم يتداول تحت متوسطات 50 و200 يوم"
        : "السهم في نطاق فني وتوازني سليم",
    };

    if (isDeadCapital) deadCapital.push(item);
    else healthy.push(item);
  }

  let report;
  try {
    report = await getCachedFairValueReport();
  } catch {
    const [fundAll, indAll] = await Promise.all([
      db
        .from("stock_fundamentals")
        .select("symbol, name, name_ar, data")
        .eq("exchange", "EGX")
        .limit(400),
      db
        .from("stock_technical_indicators")
        .select(
          "symbol, date, close, change_pct, volume, ema_50, ema_200, sma_200, vwap_20, rsi_14"
        )
        .eq("exchange", "EGX")
        .order("date", { ascending: false })
        .limit(400),
    ]);
    report = computeFairValueReport(fundAll.data || [], indAll.data || []);
  }

  const currentSyms = new Set(symbols);
  const replacements = (report.stocks || [])
    .filter(
      (s: any) =>
        !currentSyms.has(s.symbol) &&
        s.upsidePct >= 20 &&
        (!args.sharia_only || s.isSharia)
    )
    .slice(0, 3)
    .map((s: any) => ({
      symbol: s.symbol,
      name_ar: s.nameAr,
      sector_ar: s.sectorAr,
      current_price: s.currentPrice,
      fair_value: s.fairValue,
      upside_pct: s.upsidePct,
      model_label_ar: s.modelLabelAr,
      is_sharia: s.isSharia,
    }));

  return {
    status: "success",
    total_positions_evaluated: positions.length,
    dead_capital_count: deadCapital.length,
    healthy_count: healthy.length,
    dead_capital_positions: deadCapital,
    healthy_positions: healthy,
    recommended_replacements: replacements,
    quota_notice:
      "تم تشخيص المحفظة وخصم رسالة واحدة من كوتا الذكاء الاصطناعي بنجاح.",
  };
}
