"use client";

import React, { useMemo, useState } from "react";
import { Calculator, Gift, Scissors, Coins, Landmark, Info } from "lucide-react";
import {
  calculateCorporateActionClient,
  type CorporateActionType,
} from "@/lib/market/corporate-actions";

interface QuickStockOption {
  symbol: string;
  name_ar?: string | null;
  amount: number;
  last_price?: number | null;
}

interface CorporateActionsCalculatorProps {
  isAr: boolean;
  market: "egx" | "tasi" | "qatar" | "uae";
  currencyAr: string;
  currencyEn: string;
  quickOptions?: QuickStockOption[];
}

export default function CorporateActionsCalculator({
  isAr,
  market,
  currencyAr,
  currencyEn,
  quickOptions = [],
}: CorporateActionsCalculatorProps) {
  const curLabel = isAr ? currencyAr : currencyEn;
  const exchange = market === "tasi" ? "TASI" : market === "qatar" ? "QSE" : market === "uae" ? "DFM" : "EGX";

  const [tab, setTab] = useState<CorporateActionType>("bonus_shares");
  const [prePrice, setPrePrice] = useState<string>("10.00");
  const [shares, setShares] = useState<string>("1000");
  const [avgBuy, setAvgBuy] = useState<string>("8.50");
  const [ratioNew, setRatioNew] = useState<string>("1");
  const [ratioFor, setRatioFor] = useState<string>("4");
  const [dividendPerShare, setDividendPerShare] = useState<string>("1.00");
  const [taxRate, setTaxRate] = useState<string>(market === "egx" ? "5" : "0");
  const [subPrice, setSubPrice] = useState<string>("1.00");

  const handleSelectQuickStock = (sym: string) => {
    const found = quickOptions.find((o) => o.symbol === sym);
    if (!found) return;
    if (found.last_price && found.last_price > 0) {
      setPrePrice(String(found.last_price));
      setAvgBuy(String(found.last_price));
    }
    if (found.amount > 0) {
      setDividendPerShare(String(found.amount));
    }
  };

  const result = useMemo(
    () =>
      calculateCorporateActionClient({
        actionType: tab,
        preExPrice: Number(prePrice),
        shares: Number(shares),
        avgBuyPrice: Number(avgBuy) || Number(prePrice),
        ratioNew: Number(ratioNew),
        ratioFor: Number(ratioFor),
        dividendPerShare: Number(dividendPerShare),
        taxRatePct: Number(taxRate),
        subscriptionPrice: Number(subPrice),
        exchange,
      }),
    [tab, prePrice, shares, avgBuy, ratioNew, ratioFor, dividendPerShare, taxRate, subPrice, exchange]
  );

  const tabs: { id: CorporateActionType; labelAr: string; labelEn: string; icon: React.ReactNode }[] = [
    { id: "bonus_shares", labelAr: "أسهم مجانية", labelEn: "Bonus Shares", icon: <Gift className="w-3.5 h-3.5" /> },
    { id: "stock_split", labelAr: "تجزئة السهم", labelEn: "Stock Split", icon: <Scissors className="w-3.5 h-3.5" /> },
    { id: "cash_dividend", labelAr: "كوبون نقدي", labelEn: "Cash Dividend", icon: <Coins className="w-3.5 h-3.5" /> },
    { id: "rights_issue", labelAr: "حق اكتتاب", labelEn: "Rights Issue", icon: <Landmark className="w-3.5 h-3.5" /> },
  ];

  const handleSwitchTab = (next: CorporateActionType) => {
    setTab(next);
    if (next === "stock_split") {
      setRatioNew("5");
      setRatioFor("1");
    } else if (next === "bonus_shares") {
      setRatioNew("1");
      setRatioFor("4");
    } else if (next === "rights_issue") {
      setRatioNew("1");
      setRatioFor("2");
    }
  };

  return (
    <section
      aria-label={isAr ? "حاسبة الكوبونات والأسهم المجانية والتجزئة وحقوق الاكتتاب" : "Corporate Actions Calculator"}
      className="border-2 border-black dark:border-zinc-700 bg-white dark:bg-zinc-950 p-4 sm:p-5 shadow-[4px_4px_0_0_#000] dark:shadow-[4px_4px_0_0_#27272a] space-y-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-[#FFE600] text-black border-2 border-black">
            <Calculator className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm sm:text-base font-black text-zinc-950 dark:text-white">
              {isAr
                ? "حاسبة أثر التوزيعات والتجزئة وحقوق الاكتتاب (يوم الحق Ex-Date)"
                : "Ex-Date Corporate Actions & Cost-Basis Calculator"}
            </h2>
            <p className="text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
              {isAr
                ? "احسب السعر النظري بعد الحق، عدد أسهمك الجديد، ومتوسط الشراء المعدّل فورياً في المتصفح."
                : "Instantly compute theoretical ex-price, adjusted shares, new average cost, and Yield on Cost."}
            </p>
          </div>
        </div>

        {quickOptions.length > 0 && (
          <select
            aria-label={isAr ? "اختر سهم لملء البيانات تلقائياً" : "Auto-fill from stock"}
            onChange={(e) => handleSelectQuickStock(e.target.value)}
            defaultValue=""
            className="text-xs font-bold px-2.5 py-1.5 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-900 dark:text-white"
          >
            <option value="">{isAr ? "⚡ ملء سريع من الجدول..." : "⚡ Quick-fill from table..."}</option>
            {quickOptions.slice(0, 25).map((opt) => (
              <option key={opt.symbol} value={opt.symbol}>
                {opt.symbol} {opt.name_ar ? `— ${opt.name_ar}` : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Action Type Tabs */}
      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => handleSwitchTab(t.id)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 border-black dark:border-zinc-700 transition-colors cursor-pointer ${
              tab === t.id
                ? "bg-[#FFE600] text-black shadow-[2px_2px_0_0_#000]"
                : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-800"
            }`}
          >
            {t.icon}
            <span>{isAr ? t.labelAr : t.labelEn}</span>
          </button>
        ))}
      </div>

      {/* Inputs Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
          <span>{isAr ? `السعر قبل الحق (${curLabel})` : `Pre-Ex Price (${curLabel})`}</span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={prePrice}
            onChange={(e) => setPrePrice(e.target.value)}
            className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
          />
        </label>

        <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
          <span>{isAr ? "عدد أسهمك" : "Your Shares"}</span>
          <input
            type="number"
            min="1"
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
          />
        </label>

        <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
          <span>{isAr ? `متوسط شرائك (${curLabel})` : `Avg Cost (${curLabel})`}</span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={avgBuy}
            onChange={(e) => setAvgBuy(e.target.value)}
            className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
          />
        </label>

        {(tab === "bonus_shares" || tab === "stock_split" || tab === "rights_issue") && (
          <>
            <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
              <span>
                {tab === "bonus_shares"
                  ? isAr ? "أسهم مجانية" : "Bonus Shares"
                  : tab === "stock_split"
                  ? isAr ? "الأسهم بعد التجزئة" : "New Shares"
                  : isAr ? "أسهم الاكتتاب الجديدة" : "New Rights Shares"}
              </span>
              <input
                type="number"
                step="0.1"
                min="0"
                value={ratioNew}
                onChange={(e) => setRatioNew(e.target.value)}
                className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
              <span>{isAr ? "لكل (أسهم قديمة)" : "For Every (Old)"}</span>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={ratioFor}
                onChange={(e) => setRatioFor(e.target.value)}
                className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
              />
            </label>
          </>
        )}

        {tab === "cash_dividend" && (
          <>
            <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
              <span>{isAr ? `الكوبون للسهم (${curLabel})` : `Dividend / Share`}</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={dividendPerShare}
                onChange={(e) => setDividendPerShare(e.target.value)}
                className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
              <span>{isAr ? "ضريبة التوزيعات %" : "Tax Rate %"}</span>
              <input
                type="number"
                step="0.5"
                min="0"
                max="50"
                value={taxRate}
                onChange={(e) => setTaxRate(e.target.value)}
                className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
              />
            </label>
          </>
        )}

        {tab === "rights_issue" && (
          <label className="flex flex-col gap-1 text-[11px] font-black text-zinc-700 dark:text-zinc-300">
            <span>{isAr ? `سعر الاكتتاب (${curLabel})` : `Sub Price (${curLabel})`}</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={subPrice}
              onChange={(e) => setSubPrice(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-mono font-black bg-white dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 text-zinc-950 dark:text-white"
            />
          </label>
        )}
      </div>

      {/* Live Output Cards */}
      {!result.valid ? (
        <div className="p-3 bg-amber-50 dark:bg-amber-950/30 border-2 border-amber-500 text-xs font-bold text-amber-800 dark:text-amber-200">
          {isAr ? result.errorAr : result.errorEn}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700">
            <div className="text-[10px] font-black text-zinc-500 dark:text-zinc-400">
              {tab === "rights_issue"
                ? isAr ? "السعر النظري بعد الحق (TERP)" : "Theoretical Ex-Rights (TERP)"
                : isAr ? "السعر النظري بعد الحق" : "Theoretical Ex-Price"}
            </div>
            <div className="text-base sm:text-lg font-mono font-black text-zinc-950 dark:text-white mt-0.5">
              {result.theoreticalExPrice.toFixed(result.decimals)} {curLabel}
            </div>
            <div className="text-[10px] font-mono font-bold text-amber-600 dark:text-amber-400">
              {result.priceAdjustmentPct > 0 ? "+" : ""}
              {result.priceAdjustmentPct.toFixed(2)}%
            </div>
          </div>

          {tab === "cash_dividend" ? (
            <>
              <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 border-2 border-emerald-600">
                <div className="text-[10px] font-black text-emerald-700 dark:text-emerald-300">
                  {isAr ? "صافي الكوبون بعد الضريبة" : "Net Cash Payout"}
                </div>
                <div className="text-base sm:text-lg font-mono font-black text-emerald-700 dark:text-emerald-400 mt-0.5">
                  {(result.netDividend ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} {curLabel}
                </div>
                <div className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400">
                  {isAr ? "إجمالي:" : "Gross:"} {(result.grossDividend ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </div>
              </div>

              <div className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700">
                <div className="text-[10px] font-black text-zinc-500 dark:text-zinc-400">
                  {isAr ? "العائد الصافي على متوسطك (YoC)" : "Net Yield on Cost"}
                </div>
                <div className="text-base sm:text-lg font-mono font-black text-indigo-700 dark:text-indigo-400 mt-0.5">
                  {(result.netYieldOnCostPct ?? 0).toFixed(2)}%
                </div>
                <div className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400">
                  {isAr ? "على السعر الحالي:" : "Current:"} {(result.netDividendYieldPct ?? 0).toFixed(2)}%
                </div>
              </div>

              <div className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700">
                <div className="text-[10px] font-black text-zinc-500 dark:text-zinc-400">
                  {isAr ? "تكلفتك الفعلية بعد الكوبون" : "Effective Cost Post-Div"}
                </div>
                <div className="text-base sm:text-lg font-mono font-black text-zinc-950 dark:text-white mt-0.5">
                  {(result.effectiveCostAfterDividend ?? result.oldAvgCost).toFixed(result.decimals)} {curLabel}
                </div>
                <div className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400">
                  {isAr ? "متوسطك قبل:" : "Before:"} {result.oldAvgCost.toFixed(result.decimals)}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 border-2 border-emerald-600">
                <div className="text-[10px] font-black text-emerald-700 dark:text-emerald-300">
                  {isAr ? "عدد أسهمك الجديد" : "New Total Shares"}
                </div>
                <div className="text-base sm:text-lg font-mono font-black text-emerald-700 dark:text-emerald-400 mt-0.5">
                  {result.newShares.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </div>
                <div className="text-[10px] font-mono text-zinc-600 dark:text-zinc-400">
                  {result.addedShares >= 0 ? "+" : ""}
                  {result.addedShares.toLocaleString(undefined, { maximumFractionDigits: 2 })} {isAr ? "سهم" : "sh"}
                </div>
              </div>

              <div className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700">
                <div className="text-[10px] font-black text-zinc-500 dark:text-zinc-400">
                  {isAr ? "متوسط الشراء المعدّل" : "Adjusted Avg Cost"}
                </div>
                <div className="text-base sm:text-lg font-mono font-black text-indigo-700 dark:text-indigo-400 mt-0.5">
                  {result.newAvgCost.toFixed(result.decimals)} {curLabel}
                </div>
                <div className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400">
                  {isAr ? "قبل التعديل:" : "Before:"} {result.oldAvgCost.toFixed(result.decimals)}
                </div>
              </div>

              <div className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700">
                <div className="text-[10px] font-black text-zinc-500 dark:text-zinc-400">
                  {tab === "rights_issue"
                    ? isAr ? "تكلفة الاكتتاب / قيمة الحق" : "Sub Cost / Right Value"
                    : isAr ? "القيمة السوقية الإجمالية" : "Total Market Value"}
                </div>
                {tab === "rights_issue" ? (
                  <>
                    <div className="text-base sm:text-lg font-mono font-black text-zinc-950 dark:text-white mt-0.5">
                      {(result.subscriptionCost ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} {curLabel}
                    </div>
                    <div className="text-[10px] font-mono font-bold text-emerald-700 dark:text-emerald-400">
                      {isAr ? "قيمة الحق النظري:" : "Right:"} {(result.theoreticalRightValue ?? 0).toFixed(result.decimals)} {curLabel}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-base sm:text-lg font-mono font-black text-zinc-950 dark:text-white mt-0.5">
                      {result.newMarketValue.toLocaleString(undefined, { maximumFractionDigits: 2 })} {curLabel}
                    </div>
                    <div className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400">
                      {isAr ? "ثابتة بدون خسارة فنية" : "Unchanged value"}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <div className="flex items-start gap-1.5 text-[11px] font-bold text-zinc-500 dark:text-zinc-400">
        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        <span>
          {isAr
            ? "الحسابات فنية ونظرية لأغراض التخطيط الشخصي قبل يوم الحق (Ex-Date)، وقد يختلف سعر الافتتاح الفعلي وفق العرض والطلب."
            : "Theoretical pre-market Ex-Date adjustments for personal planning; actual opening price depends on supply and demand."}
        </span>
      </div>
    </section>
  );
}
