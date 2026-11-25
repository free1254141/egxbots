/**
 * Pure Client-Side Corporate Actions & Ex-Date Impact Calculator (0% Vercel CPU).
 * Mirrors `api/corporate_events_engine.py::calculate_corporate_action` exactly.
 */

export type CorporateActionType = "bonus_shares" | "stock_split" | "cash_dividend" | "rights_issue";

export interface CorporateActionInput {
  actionType: CorporateActionType;
  preExPrice: number;
  shares: number;
  avgBuyPrice?: number;
  ratioNew?: number;
  ratioFor?: number;
  dividendPerShare?: number;
  taxRatePct?: number;
  subscriptionPrice?: number;
  exchange?: string;
}

export interface CorporateActionResult {
  valid: boolean;
  errorAr?: string;
  errorEn?: string;
  actionType: CorporateActionType;
  decimals: number;
  preExPrice: number;
  theoreticalExPrice: number;
  priceAdjustmentPct: number;
  oldShares: number;
  addedShares: number;
  newShares: number;
  oldAvgCost: number;
  newAvgCost: number;
  oldMarketValue: number;
  newMarketValue: number;
  // Cash dividend specific
  grossDividend?: number;
  taxAmount?: number;
  netDividend?: number;
  taxRatePct?: number;
  dividendYieldPct?: number;
  netDividendYieldPct?: number;
  yieldOnCostPct?: number;
  netYieldOnCostPct?: number;
  effectiveCostAfterDividend?: number;
  // Rights issue specific
  theoreticalRightValue?: number;
  subscriptionCost?: number;
}

function priceDecimals(p: number): number {
  return p < 10 ? 3 : 2;
}

function roundTo(val: number, dec: number): number {
  const m = 10 ** dec;
  return Math.round(val * m) / m;
}

export function calculateCorporateActionClient(input: CorporateActionInput): CorporateActionResult {
  const p0 = Number(input.preExPrice);
  const qty0 = Number(input.shares) > 0 ? Number(input.shares) : 1000;
  const avg0 = Number(input.avgBuyPrice) > 0 ? Number(input.avgBuyPrice) : p0;
  const exU = (input.exchange || "EGX").toUpperCase();

  const invalid = (errorAr: string, errorEn: string): CorporateActionResult => ({
    valid: false,
    errorAr,
    errorEn,
    actionType: input.actionType,
    decimals: 2,
    preExPrice: 0,
    theoreticalExPrice: 0,
    priceAdjustmentPct: 0,
    oldShares: qty0,
    addedShares: 0,
    newShares: qty0,
    oldAvgCost: avg0 || 0,
    newAvgCost: avg0 || 0,
    oldMarketValue: 0,
    newMarketValue: 0,
  });

  if (!Number.isFinite(p0) || p0 <= 0) {
    return invalid("أدخل سعر السهم قبل تاريخ الحق (أكبر من صفر).", "Enter pre-ex stock price (> 0).");
  }

  const dec = priceDecimals(p0);
  const oldVal = qty0 * p0;
  const oldCost = qty0 * avg0;

  if (input.actionType === "bonus_shares") {
    const rn = Number(input.ratioNew);
    const rf = Number(input.ratioFor) || 1;
    if (!Number.isFinite(rn) || rn <= 0 || !Number.isFinite(rf) || rf <= 0) {
      return invalid("أدخل نسبة الأسهم المجانية (مثلاً 1 لكل 4).", "Enter bonus ratio (e.g. 1 for 4).");
    }
    const factor = 1 + rn / rf;
    const exPrice = p0 / factor;
    const newShares = qty0 * factor;
    const addedShares = newShares - qty0;
    const newAvg = avg0 / factor;
    return {
      valid: true,
      actionType: "bonus_shares",
      decimals: dec,
      preExPrice: roundTo(p0, dec),
      theoreticalExPrice: roundTo(exPrice, dec),
      priceAdjustmentPct: roundTo(((exPrice - p0) / p0) * 100, 2),
      oldShares: roundTo(qty0, 2),
      addedShares: roundTo(addedShares, 2),
      newShares: roundTo(newShares, 2),
      oldAvgCost: roundTo(avg0, dec),
      newAvgCost: roundTo(newAvg, dec),
      oldMarketValue: roundTo(oldVal, 2),
      newMarketValue: roundTo(newShares * exPrice, 2),
    };
  }

  if (input.actionType === "stock_split") {
    const rn = Number(input.ratioNew);
    const rf = Number(input.ratioFor) || 1;
    if (!Number.isFinite(rn) || rn <= 0 || !Number.isFinite(rf) || rf <= 0) {
      return invalid("أدخل معامل التجزئة (مثلاً 5 إلى 1).", "Enter split ratio (e.g. 5 to 1).");
    }
    const factor = rn / rf;
    const exPrice = p0 / factor;
    const newShares = qty0 * factor;
    const addedShares = newShares - qty0;
    const newAvg = avg0 / factor;
    return {
      valid: true,
      actionType: "stock_split",
      decimals: dec,
      preExPrice: roundTo(p0, dec),
      theoreticalExPrice: roundTo(exPrice, dec),
      priceAdjustmentPct: roundTo(((exPrice - p0) / p0) * 100, 2),
      oldShares: roundTo(qty0, 2),
      addedShares: roundTo(addedShares, 2),
      newShares: roundTo(newShares, 2),
      oldAvgCost: roundTo(avg0, dec),
      newAvgCost: roundTo(newAvg, dec),
      oldMarketValue: roundTo(oldVal, 2),
      newMarketValue: roundTo(newShares * exPrice, 2),
    };
  }

  if (input.actionType === "cash_dividend") {
    const dps = Number(input.dividendPerShare);
    if (!Number.isFinite(dps) || dps <= 0) {
      return invalid("أدخل قيمة الكوبون النقدي للسهم.", "Enter cash dividend per share (> 0).");
    }
    const defaultTax = exU === "EGX" ? 5 : 0;
    const taxPct =
      input.taxRatePct !== undefined && Number.isFinite(input.taxRatePct) && input.taxRatePct >= 0 && input.taxRatePct <= 50
        ? input.taxRatePct
        : defaultTax;
    const exPrice = Math.max(0, p0 - dps);
    const gross = qty0 * dps;
    const taxAmt = gross * (taxPct / 100);
    const net = gross - taxAmt;
    const curYield = (dps / p0) * 100;
    const netCurYield = ((dps * (1 - taxPct / 100)) / p0) * 100;
    const yocGross = (dps / avg0) * 100;
    const yocNet = ((dps * (1 - taxPct / 100)) / avg0) * 100;
    const effCost = Math.max(0, avg0 - dps * (1 - taxPct / 100));
    return {
      valid: true,
      actionType: "cash_dividend",
      decimals: dec,
      preExPrice: roundTo(p0, dec),
      theoreticalExPrice: roundTo(exPrice, dec),
      priceAdjustmentPct: roundTo(((exPrice - p0) / p0) * 100, 2),
      oldShares: roundTo(qty0, 2),
      addedShares: 0,
      newShares: roundTo(qty0, 2),
      oldAvgCost: roundTo(avg0, dec),
      newAvgCost: roundTo(avg0, dec),
      oldMarketValue: roundTo(oldVal, 2),
      newMarketValue: roundTo(qty0 * exPrice, 2),
      grossDividend: roundTo(gross, 2),
      taxAmount: roundTo(taxAmt, 2),
      netDividend: roundTo(net, 2),
      taxRatePct: roundTo(taxPct, 2),
      dividendYieldPct: roundTo(curYield, 2),
      netDividendYieldPct: roundTo(netCurYield, 2),
      yieldOnCostPct: roundTo(yocGross, 2),
      netYieldOnCostPct: roundTo(yocNet, 2),
      effectiveCostAfterDividend: roundTo(effCost, dec),
    };
  }

  // rights_issue
  const rn = Number(input.ratioNew);
  const rf = Number(input.ratioFor) || 1;
  const subP = Number(input.subscriptionPrice);
  if (!Number.isFinite(rn) || rn <= 0 || !Number.isFinite(rf) || rf <= 0) {
    return invalid("أدخل نسبة الاكتتاب (مثلاً 1 جديد لكل 2 قديم).", "Enter subscription ratio (e.g. 1 new for 2 old).");
  }
  if (!Number.isFinite(subP) || subP < 0) {
    return invalid("أدخل سعر الاكتتاب للسهم الجديد.", "Enter subscription price (>= 0).");
  }
  const terp = (p0 * rf + subP * rn) / (rf + rn);
  const rightVal = Math.max(0, p0 - terp);
  const addedShares = qty0 * (rn / rf);
  const newShares = qty0 + addedShares;
  const subCash = addedShares * subP;
  const newAvg = newShares > 0 ? (oldCost + subCash) / newShares : avg0;

  return {
    valid: true,
    actionType: "rights_issue",
    decimals: dec,
    preExPrice: roundTo(p0, dec),
    theoreticalExPrice: roundTo(terp, dec),
    priceAdjustmentPct: roundTo(((terp - p0) / p0) * 100, 2),
    oldShares: roundTo(qty0, 2),
    addedShares: roundTo(addedShares, 2),
    newShares: roundTo(newShares, 2),
    oldAvgCost: roundTo(avg0, dec),
    newAvgCost: roundTo(newAvg, dec),
    oldMarketValue: roundTo(oldVal, 2),
    newMarketValue: roundTo(newShares * terp, 2),
    theoreticalRightValue: roundTo(rightVal, dec),
    subscriptionCost: roundTo(subCash, 2),
  };
}
