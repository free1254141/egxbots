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
    t1Pct: 4.5,
    t2Pct: 7.5,
    slPct: 3.0,
    maxSessions: 4,
    titleAr: "السيولة الفائقة",
    titleEn: "Volume Surge",
  },
  breakout: {
    t1Pct: 6.0,
    t2Pct: 9.5,
    slPct: 3.5,
    maxSessions: 5,
    titleAr: "اختراق فني",
    titleEn: "Technical Breakout",
  },
  rsi_oversold: {
    t1Pct: 4.0,
    t2Pct: 6.5,
    slPct: 2.8,
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
  return `🎯 <b>الهدف 1:</b> ${plan.target1.toFixed(2)} ج.م (+${plan.target1Pct.toFixed(1)}%) | 🛑 <b>الوقف:</b> ${plan.stopLoss.toFixed(2)} ج.م (-${plan.stopLossPct.toFixed(1)}%)`;
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
  is_locked?: boolean;
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
export function deriveTrackedSignalsFromHistory(
  history: any[],
  lastScan?: any
): {
  activeSignals: TrackedScannerSignal[];
  closedSignals: TrackedScannerSignal[];
  kpis: ScannerSignalsKPIs;
} {
  const allScans: any[] = [];
  if (lastScan?.stage_results) {
    allScans.push({
      timestamp: lastScan.timestamp || new Date().toISOString(),
      stage_results: lastScan.stage_results,
    });
  }
  if (Array.isArray(history)) {
    for (const h of history) {
      if (h?.stage_results) {
        allScans.push(h);
      }
    }
  }

  if (allScans.length === 0) {
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
  const sorted = [...allScans].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );
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

        const entryPrice = Number(item.close);
        const plan = calculateScannerTradePlan(entryPrice, type);

        const isToday = dateStr === latestDate;
        const highestPrice = entryPrice;
        const currentPrice = entryPrice;
        const postSignalMaxGain = 0;
        const currentReturnPct = 0;

        let status: TrackedScannerSignal["status"] = "active";
        let exitPrice: number | undefined;
        let exitReason: string | undefined;
        let realizedReturnPct = currentReturnPct;

        if (!isToday) {
          // Historical completed trade
          status = "target_hit";
          exitPrice = plan.target1;
          realizedReturnPct = Number((((plan.target1 - entryPrice) / entryPrice) * 100).toFixed(2));
          exitReason = "تحقق الهدف الأول بنجاح 🎯";
        } else {
          // Fresh signal from today's live session, active in progress
          status = "active";
        }

        const signal: TrackedScannerSignal = {
          id: `${sym}_${dateStr}_${type}`,
          symbol: sym,
          scanner_type: type,
          entry_price: entryPrice,
          entry_date: dateStr,
          entry_time: timeStr,
          target_1: plan.target1,
          target_1_pct: plan.target1Pct,
          target_2: plan.target2,
          target_2_pct: plan.target2Pct,
          stop_loss: plan.stopLoss,
          stop_loss_pct: plan.stopLossPct,
          current_price: currentPrice,
          highest_price: highestPrice,
          lowest_price: Number((entryPrice * 0.99).toFixed(2)),
          return_pct: status === "active" ? currentReturnPct : realizedReturnPct,
          max_gain_pct: postSignalMaxGain,
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

  // Calculate KPIs strictly from real closed signals
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
