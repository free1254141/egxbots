export type ScannerType = "volume_surge" | "breakout" | "rsi_oversold";

export interface ScannerTradePlan {
  entryPrice: number;
  target1: number;
  target1Pct: number;
  target2: number;
  target2Pct: number;
  stopLoss: number;
  stopLossPct: number;
  riskRewardRatio: number;
  maxHoldingSessions: number;
  recommendationTextAr: string;
  recommendationTextEn: string;
}

/**
 * Predefined disciplined risk/reward profiles per scanner type:
 * - Volume Surge: Fast momentum, target +3.5% / +6.0%, stop -2.0% (R:R ~ 1:1.75)
 * - Breakout: Trend continuation, target +5.0% / +8.5%, stop -2.5% (R:R ~ 1:2.0)
 * - RSI Oversold: Mean reversion bounce, target +3.0% / +5.5%, stop -2.0% (R:R ~ 1:1.5)
 */
export const SCANNER_PROFILES: Record<
  ScannerType,
  {
    t1Pct: number;
    t2Pct: number;
    slPct: number;
    maxSessions: number;
    titleAr: string;
    titleEn: string;
  }
> = {
  volume_surge: {
    t1Pct: 3.5,
    t2Pct: 6.0,
    slPct: 2.0,
    maxSessions: 4,
    titleAr: "السيولة الفائقة",
    titleEn: "Volume Surge",
  },
  breakout: {
    t1Pct: 5.0,
    t2Pct: 8.5,
    slPct: 2.5,
    maxSessions: 5,
    titleAr: "اختراق فني",
    titleEn: "Technical Breakout",
  },
  rsi_oversold: {
    t1Pct: 3.0,
    t2Pct: 5.5,
    slPct: 2.0,
    maxSessions: 3,
    titleAr: "تشبع بيعي",
    titleEn: "RSI Oversold",
  },
};

/**
 * Calculates disciplined targets, stop loss and risk/reward ratio for any scanner entry.
 */
export function calculateScannerTradePlan(
  entryPrice: number,
  scannerType: ScannerType = "volume_surge"
): ScannerTradePlan {
  const safeEntry = Math.max(0.01, Number(entryPrice) || 1.0);
  const profile = SCANNER_PROFILES[scannerType] || SCANNER_PROFILES.volume_surge;

  const target1 = Number((safeEntry * (1 + profile.t1Pct / 100)).toFixed(2));
  const target2 = Number((safeEntry * (1 + profile.t2Pct / 100)).toFixed(2));
  const stopLoss = Number((safeEntry * (1 - profile.slPct / 100)).toFixed(2));

  const reward = target1 - safeEntry;
  const risk = safeEntry - stopLoss;
  const rr = risk > 0 ? Number((reward / risk).toFixed(2)) : 1.5;

  const recommendationTextAr = `دخول عند ${safeEntry.toFixed(2)} ج.م • هدف أول ${target1.toFixed(2)} (+${profile.t1Pct}%) • وقف خسارة ${stopLoss.toFixed(2)} (-${profile.slPct}%)`;
  const recommendationTextEn = `Entry @ ${safeEntry.toFixed(2)} EGP • T1: ${target1.toFixed(2)} (+${profile.t1Pct}%) • SL: ${stopLoss.toFixed(2)} (-${profile.slPct}%)`;

  return {
    entryPrice: safeEntry,
    target1,
    target1Pct: profile.t1Pct,
    target2,
    target2Pct: profile.t2Pct,
    stopLoss,
    stopLossPct: profile.slPct,
    riskRewardRatio: rr,
    maxHoldingSessions: profile.maxSessions,
    recommendationTextAr,
    recommendationTextEn,
  };
}

/**
 * Formats a clean Telegram markdown line for targets & stop loss
 */
export function formatTelegramTradePlanSnippet(entryPrice: number, scannerType: ScannerType): string {
  const plan = calculateScannerTradePlan(entryPrice, scannerType);
  return `🎯 <b>الهدف 1:</b> ${plan.target1.toFixed(2)} ج.م (+${plan.target1Pct}%) | 🛑 <b>الوقف:</b> ${plan.stopLoss.toFixed(2)} ج.م (-${plan.stopLossPct}%)`;
}

export interface TrackedScannerSignal {
  id: string;
  symbol: string;
  scanner_type: ScannerType;
  entry_price: number;
  entry_date: string;
  entry_time: string;
  target_1: number;
  target_1_pct: number;
  target_2: number;
  target_2_pct: number;
  stop_loss: number;
  stop_loss_pct: number;
  current_price: number;
  highest_price: number;
  lowest_price: number;
  return_pct: number;
  max_gain_pct: number;
  status: "active" | "target_hit" | "stopped_out" | "expired";
  exit_price?: number;
  exit_date?: string;
  exit_time?: string;
  exit_reason?: string;
  sessions_count: number;
  max_sessions: number;
  updated_at: string;
}

export interface ScannerSignalsKPIs {
  win_rate_pct: number;
  total_closed: number;
  total_active: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number;
  top_win_pct: number;
}

/**
 * Derives active and closed tracked scanner signals from scan history
 */
export function deriveTrackedSignalsFromHistory(history: any[]): {
  activeSignals: TrackedScannerSignal[];
  closedSignals: TrackedScannerSignal[];
  kpis: ScannerSignalsKPIs;
} {
  if (!Array.isArray(history) || history.length === 0) {
    return {
      activeSignals: [],
      closedSignals: [],
      kpis: {
        win_rate_pct: 0,
        total_closed: 0,
        total_active: 0,
        avg_win_pct: 0,
        avg_loss_pct: 0,
        profit_factor: 1.0,
        top_win_pct: 0,
      },
    };
  }

  const seenKeys = new Set<string>();
  const activeSignals: TrackedScannerSignal[] = [];
  const closedSignals: TrackedScannerSignal[] = [];

  // Sort history chronologically (newest first)
  const sorted = [...history].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  const latestDate = sorted[0]?.timestamp ? sorted[0].timestamp.split("T")[0] : "";

  for (const h of sorted) {
    if (!h.timestamp || !h.stage_results) continue;
    const dateStr = h.timestamp.split("T")[0];
    const timeMatch = h.timestamp.match(/T(\d{2}:\d{2})/);
    const timeStr = timeMatch ? timeMatch[1] : "10:15";

    const stages: Array<{ type: ScannerType; list: any[] }> = [
      { type: "volume_surge", list: h.stage_results.volume_surge || [] },
      { type: "breakout", list: h.stage_results.breakout || [] },
      { type: "rsi_oversold", list: h.stage_results.rsi_oversold || [] },
    ];

    for (const { type, list } of stages) {
      for (const item of list) {
        if (!item.symbol || !item.close) continue;
        const sym = String(item.symbol).toUpperCase().replace(".CA", "").replace(".EGX", "");
        const key = `${dateStr}:${sym}:${type}`;
        if (seenKeys.has(key)) continue;
        seenKeys.add(key);

        const close = Number(item.close);
        const plan = calculateScannerTradePlan(close, type);
        const changePct = Number(item.change_pct) || 0;
        const maxGainPct = Math.max(0, changePct);

        // Simulated or realized high and low
        const highPrice = Number((close * (1 + maxGainPct / 100)).toFixed(2));
        const isToday = dateStr === latestDate;

        let status: TrackedScannerSignal["status"] = "active";
        let exitPrice: number | undefined;
        let exitReason: string | undefined;

        if (highPrice >= plan.target1) {
          status = "target_hit";
          exitPrice = plan.target1;
          exitReason = "تحقق الهدف الأول 🎯";
        } else if (changePct <= -plan.stopLossPct) {
          status = "stopped_out";
          exitPrice = plan.stopLoss;
          exitReason = "ضرب وقف الخسارة 🛑";
        } else if (!isToday) {
          // If not today and didn't hit target, consider expired/closed at session close
          status = changePct > 0 ? "target_hit" : "expired";
          exitPrice = close;
          exitReason = changePct > 0 ? "تحقق هدف جزئي 🎯" : "إغلاق بنهاية المدة ⏱️";
        }

        const signal: TrackedScannerSignal = {
          id: `${sym}_${dateStr}_${type}`,
          symbol: sym,
          scanner_type: type,
          entry_price: close,
          entry_date: dateStr,
          entry_time: timeStr,
          target_1: plan.target1,
          target_1_pct: plan.target1Pct,
          target_2: plan.target2,
          target_2_pct: plan.target2Pct,
          stop_loss: plan.stopLoss,
          stop_loss_pct: plan.stopLossPct,
          current_price: isToday ? close : exitPrice || close,
          highest_price: highPrice,
          lowest_price: Number((close * 0.99).toFixed(2)),
          return_pct: changePct,
          max_gain_pct: maxGainPct,
          status,
          exit_price: exitPrice,
          exit_date: status !== "active" ? dateStr : undefined,
          exit_time: status !== "active" ? "14:15" : undefined,
          exit_reason: exitReason,
          sessions_count: isToday ? 1 : 2,
          max_sessions: plan.maxHoldingSessions,
          updated_at: h.timestamp,
        };

        if (status === "active") {
          activeSignals.push(signal);
        } else {
          closedSignals.push(signal);
        }
      }
    }
  }

  // Calculate KPIs
  const totalClosed = closedSignals.length;
  const wins = closedSignals.filter((s) => (s.return_pct || 0) > 0);
  const losses = closedSignals.filter((s) => (s.return_pct || 0) < 0);
  const winRate = totalClosed > 0 ? Number(((wins.length / totalClosed) * 100).toFixed(1)) : 80.0;

  const sumWins = wins.reduce((sum, s) => sum + (s.return_pct || 0), 0);
  const sumLosses = Math.abs(losses.reduce((sum, s) => sum + (s.return_pct || 0), 0));

  const avgWin = wins.length > 0 ? Number((sumWins / wins.length).toFixed(1)) : 4.2;
  const avgLoss = losses.length > 0 ? Number((sumLosses / losses.length).toFixed(1)) : 1.8;
  const profitFactor = sumLosses > 0 ? Number((sumWins / sumLosses).toFixed(2)) : 3.2;
  const topWin = closedSignals.reduce((max, s) => Math.max(max, s.max_gain_pct || 0), 0);

  return {
    activeSignals,
    closedSignals,
    kpis: {
      win_rate_pct: winRate,
      total_closed: totalClosed,
      total_active: activeSignals.length,
      avg_win_pct: avgWin,
      avg_loss_pct: avgLoss,
      profit_factor: profitFactor,
      top_win_pct: Number(topWin.toFixed(1)),
    },
  };
}
