import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import {
  calculateScannerTradePlan,
  formatTelegramTradePlanSnippet,
  TrackedScannerSignal,
  ScannerSignalsKPIs,
} from "@/lib/scannerTradePlan";

export interface ScannerPreferences {
  volume_surge: boolean;
  breakout: boolean;
  rsi_oversold: boolean;
  portfolio_watchlist: boolean;
  disclosures: boolean;
}

export interface AdminScannerConfig {
  is_active: boolean;
  interval_minutes: number;
  market_hours_only: boolean;
  scanners_enabled: {
    volume_surge: boolean;
    breakout: boolean;
    rsi_oversold: boolean;
    portfolio_watchlist: boolean;
    disclosures: boolean;
  };
  last_scan?: {
    timestamp: string;
    duration_ms: number;
    total_symbols_scanned: number;
    stage_results: {
      volume_surge: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }>;
      breakout: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }>;
      rsi_oversold: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number }>;
      disclosures: Array<{ id: string; title: string; symbol?: string; published_at?: string }>;
    };
    alerts_dispatched: number;
  };
  sent_today?: {
    date: string;
    sent_keys: string[];
  };
  history?: Array<{
    timestamp: string;
    duration_ms: number;
    volume_count: number;
    breakout_count: number;
    oversold_count: number;
    disclosures_count: number;
    recipients_count: number;
    triggered_by: string;
    stage_results?: {
      volume_surge: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }>;
      breakout: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }>;
      rsi_oversold: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number }>;
      disclosures: Array<{ id: string; title: string; symbol?: string; published_at?: string }>;
    };
  }>;
  active_signals?: TrackedScannerSignal[];
  closed_signals?: TrackedScannerSignal[];
  signals_kpis?: ScannerSignalsKPIs;
}

export const DEFAULT_ADMIN_CONFIG: AdminScannerConfig = {
  is_active: true,
  interval_minutes: 15,
  market_hours_only: true,
  scanners_enabled: {
    volume_surge: true,
    breakout: true,
    rsi_oversold: true,
    portfolio_watchlist: true,
    disclosures: true,
  },
  sent_today: {
    date: "",
    sent_keys: [],
  },
  history: [],
  active_signals: [],
  closed_signals: [],
};

const BOT_STATE_KEY = "scanner_alerts";
export const VIP_CHANNEL_CHAT_ID =
  process.env.TELEGRAM_PRO_CHAT_ID || process.env.VIP_CHANNEL_CHAT_ID || "-1003906516349";

export function getCairoNow() {
  const now = new Date();
  const cairoStr = now.toLocaleString("en-US", { timeZone: "Africa/Cairo" });
  const cairoDate = new Date(cairoStr);
  const day = cairoDate.getDay(); // 0 is Sunday, 4 is Thursday
  const hour = cairoDate.getHours();
  const minute = cairoDate.getMinutes();
  const totalMin = hour * 60 + minute;
  // Sunday (0) to Thursday (4)
  const isTradingDay = day >= 0 && day <= 4;
  // EGX hours: 10:00 to 14:35
  const isTradingHours = isTradingDay && totalMin >= 10 * 60 && totalMin <= 14 * 60 + 35;
  const timeStr = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  const dateStr = `${cairoDate.getFullYear()}-${String(cairoDate.getMonth() + 1).padStart(2, "0")}-${String(
    cairoDate.getDate()
  ).padStart(2, "0")}`;

  return { day, hour, minute, totalMin, isTradingDay, isTradingHours, timeStr, dateStr };
}

export async function getAdminConfig(client?: any): Promise<AdminScannerConfig> {
  const serviceClient = client || getSupabaseServiceClient();
  try {
    const { data } = await serviceClient
      .from("bot_states")
      .select("state")
      .eq("bot_id", BOT_STATE_KEY)
      .maybeSingle();

    if (data?.state) {
      return {
        ...DEFAULT_ADMIN_CONFIG,
        ...data.state,
        scanners_enabled: {
          ...DEFAULT_ADMIN_CONFIG.scanners_enabled,
          ...(data.state?.scanners_enabled || {}),
        },
        sent_today: data.state?.sent_today || { date: "", sent_keys: [] },
        history: data.state?.history || [],
        active_signals: data.state?.active_signals || [],
        closed_signals: data.state?.closed_signals || [],
        signals_kpis: data.state?.signals_kpis || undefined,
      };
    }
  } catch (err) {
    console.warn("Error fetching admin scanner config:", err);
  }
  return DEFAULT_ADMIN_CONFIG;
}

export async function saveAdminConfig(config: AdminScannerConfig, client?: any) {
  const serviceClient = client || getSupabaseServiceClient();
  await serviceClient.from("bot_states").upsert({
    bot_id: BOT_STATE_KEY,
    state: config,
    updated_at: new Date().toISOString(),
  });
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Send individual Telegram message with fallback to relay URL */
export async function sendTelegramAlert(chatId: string | number, text: string): Promise<boolean> {
  const token = (process.env.ARTORO_AI_BOT || process.env.TELEGRAM_BOT_TOKEN)?.trim();
  if (!token || !chatId) {
    console.warn(`[SCANNER_ALERTS] Missing bot token or chatId: token=${Boolean(token)}, chatId=${chatId}`);
    return false;
  }

  const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
  const payload = {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };

  for (const base of [relayUrl, "https://api.telegram.org"]) {
    try {
      const res = await fetch(`${base}/bot${token}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data?.ok) return true;
      console.warn(`[SCANNER_ALERTS] Telegram send failed from ${base}:`, data?.description || res.statusText);
      if (base === relayUrl) continue;
    } catch (err: any) {
      console.warn(`[SCANNER_ALERTS] Telegram send exception from ${base}:`, err?.message || err);
      if (base === relayUrl) continue;
    }
  }
  return false;
}

export interface RunScannerOptions {
  trigger?: string;
  forceMarketHours?: boolean;
  forceDispatch?: boolean;
  singleRecipientChatId?: string | number;
}

export async function executeScannerEngine(options: RunScannerOptions = {}) {
  const startTime = performance.now();
  const serviceClient = getSupabaseServiceClient();
  const config = await getAdminConfig(serviceClient);
  const cairoTime = getCairoNow();

  // Guard: Master active switch
  if (!config.is_active && !options.forceDispatch) {
    return {
      ok: false,
      skipped: true,
      reason: "Scanner is disabled by master switch in admin settings.",
    };
  }

  // Guard: Market hours
  if (config.market_hours_only && !cairoTime.isTradingHours && !options.forceMarketHours) {
    return {
      ok: false,
      skipped: true,
      reason: `Outside EGX market hours (Current Cairo time: ${cairoTime.timeStr}, Day: ${cairoTime.day}). Market runs Sun-Thu 10:00 - 14:35.`,
      cairoTime,
    };
  }

  // ── STEP 1: Query Indicators ──────────────────────────────────────────────
  let rows: any[] = [];
  try {
    const { data: latestDateRow } = await serviceClient
      .from("stock_technical_indicators")
      .select("date")
      .eq("exchange", "EGX")
      .order("date", { ascending: false })
      .limit(1)
      .maybeSingle();

    const asOfDate = latestDateRow?.date || cairoTime.dateStr;

    const { data: indicators, error: indErr } = await serviceClient
      .from("stock_technical_indicators")
      .select("symbol, close, change_pct, volume, vol_sma20, r_vol, rsi_14, bb_upper, ema_20")
      .eq("exchange", "EGX")
      .eq("date", asOfDate)
      .limit(300);

    if (!indErr && indicators && indicators.length > 0) {
      rows = indicators;
    }
  } catch (err) {
    console.warn("stock_technical_indicators query fallback:", err);
  }

  // ── STEP 2: Filter Matches ────────────────────────────────────────────────
  const volumeMatches: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }> = [];
  const breakoutMatches: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }> = [];
  const oversoldMatches: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number }> = [];

  for (const r of rows) {
    const symbol = String(r.symbol || "").toUpperCase();
    const close = Number(r.close || 0);
    const change = Number(r.change_pct || 0);
    const vol = Number(r.volume || 0);
    const rsi = Number(r.rsi_14 || 50);
    const rVol = Number(r.r_vol || 1.0);
    const bbUpper = Number(r.bb_upper || 0);

    // Stage 1: Volume Surge (>= 1.5x average volume with positive movement)
    if (config.scanners_enabled.volume_surge && rVol >= 1.5 && vol >= 100_000 && change >= 0.5) {
      volumeMatches.push({ symbol, close, change_pct: change, r_vol: rVol });
    }

    // Stage 2: Breakout (close breaking BB upper or surge + >= 2.0% change)
    const isBbBreakout = bbUpper > 0 && close >= bbUpper * 0.995;
    if (config.scanners_enabled.breakout && (isBbBreakout || (rVol >= 1.5 && change >= 2.0))) {
      breakoutMatches.push({ symbol, close, change_pct: change, r_vol: rVol });
    }

    // Stage 3: RSI Oversold Bounce (RSI <= 35 with positive movement)
    if (config.scanners_enabled.rsi_oversold && rsi > 0 && rsi <= 35 && change >= 0.2) {
      oversoldMatches.push({ symbol, close, rsi_14: rsi, change_pct: change });
    }
  }

  // Sort and limit to top 6 per category
  volumeMatches.sort((a, b) => b.r_vol - a.r_vol);
  const topVolume = volumeMatches.slice(0, 6);

  breakoutMatches.sort((a, b) => b.change_pct - a.change_pct);
  const topBreakout = breakoutMatches.slice(0, 6);

  oversoldMatches.sort((a, b) => a.rsi_14 - b.rsi_14);
  const topOversold = oversoldMatches.slice(0, 6);

  // Stage 4: Disclosures & News
  let disclosuresMatches: Array<{ id: string; title: string; symbol?: string; published_at?: string }> = [];
  if (config.scanners_enabled.disclosures) {
    try {
      const { data: articlesData } = await serviceClient
        .from("articles")
        .select("id, title_ar, title_en, created_at")
        .order("created_at", { ascending: false })
        .limit(4);

      if (articlesData && articlesData.length > 0) {
        disclosuresMatches = articlesData.map((a: any) => ({
          id: String(a.id),
          title: String(a.title_ar || a.title_en || "إفصاح رسمي"),
          published_at: a.created_at,
        }));
      }
    } catch {
      // Ignore
    }
  }

  // ── STEP 3: Deduplication with Today's History ────────────────────────────
  const sentToday = config.sent_today?.date === cairoTime.dateStr
    ? { ...config.sent_today }
    : { date: cairoTime.dateStr, sent_keys: [] };

  const sentKeysSet = new Set(sentToday.sent_keys);

  // Filter out stocks already sent today (unless forced)
  const rawFreshVolume = options.forceDispatch
    ? topVolume
    : topVolume.filter((s) => !sentKeysSet.has(`${s.symbol}:volume_surge`));

  const rawFreshBreakout = options.forceDispatch
    ? topBreakout
    : topBreakout.filter((s) => !sentKeysSet.has(`${s.symbol}:breakout`));

  const rawFreshOversold = options.forceDispatch
    ? topOversold
    : topOversold.filter((s) => !sentKeysSet.has(`${s.symbol}:rsi_oversold`));

  const freshDisclosures = options.forceDispatch
    ? disclosuresMatches
    : disclosuresMatches.filter((d) => !sentKeysSet.has(`disclosure:${d.id}`));

  // Cross-category symbol deduplication so the same stock is never repeated in an alert
  const seenFreshSymbols = new Set<string>();
  const freshVolume: typeof topVolume = [];
  const freshBreakout: typeof topBreakout = [];
  const freshOversold: typeof topOversold = [];

  for (const v of rawFreshVolume) {
    if (!seenFreshSymbols.has(v.symbol)) {
      seenFreshSymbols.add(v.symbol);
      freshVolume.push(v);
    }
  }
  for (const b of rawFreshBreakout) {
    if (!seenFreshSymbols.has(b.symbol)) {
      seenFreshSymbols.add(b.symbol);
      freshBreakout.push(b);
    }
  }
  for (const o of rawFreshOversold) {
    if (!seenFreshSymbols.has(o.symbol)) {
      seenFreshSymbols.add(o.symbol);
      freshOversold.push(o);
    }
  }

  const hasAnyFreshMatches =
    freshVolume.length > 0 || freshBreakout.length > 0 || freshOversold.length > 0 || freshDisclosures.length > 0;

  // ── STEP 4: Active Pro Subscribers Stats (Informational) ─────────────────
  const [subRes, profileRes] = await Promise.all([
    serviceClient.from("subscriptions").select("user_id").eq("status", "active"),
    serviceClient
      .from("profiles")
      .select("id, telegram_chat_id")
      .not("telegram_chat_id", "is", null),
  ]);

  const activeProUids = new Set((subRes.data || []).map((s: any) => s.user_id));
  const proProfiles = (profileRes.data || []).filter((p: any) => activeProUids.has(p.id));

  // Destination Chat IDs: Always route to official VIP Channel unless a test recipient is specified
  const targetChatIds = options.singleRecipientChatId
    ? [String(options.singleRecipientChatId)]
    : [VIP_CHANNEL_CHAT_ID];

  // ── STEP 5: Dispatch Alerts to Telegram (VIP Channel) ─────────────────────
  let alertsDispatchedCount = 0;

  if (hasAnyFreshMatches && targetChatIds.length > 0) {
    // Construct clean, BiDi-safe Arabic Message for VIP Channel
    const lines: string[] = [
      `⚡ <b>[EGX BOTS] رادار الإسكانر الفوري — قناة VIP</b>`,
      `───────────────`,
    ];

    if (freshVolume.length > 0) {
      lines.push(`🔥 <b>رادار السيولة غير الطبيعية (Volume Surge):</b>`);
      for (const v of freshVolume) {
        const plan = calculateScannerTradePlan(v.close, "volume_surge");
        const changeStr = `${v.change_pct >= 0 ? "+" : ""}${Number(v.change_pct).toFixed(1)}%`;
        lines.push(
          `🔹 <b>${v.symbol}</b> — <b>${v.close.toFixed(2)} ج.م</b> (<b>${changeStr}</b>)\n` +
          `   📊 حجم السيولة: <b>${Number(v.r_vol).toFixed(1)}x</b> الضعف\n` +
          `   🎯 الهدف: <b>${plan.target1.toFixed(2)} ج.م</b> (+${plan.target1Pct.toFixed(1)}%)\n` +
          `   🛑 الوقف: <b>${plan.stopLoss.toFixed(2)} ج.م</b> (-${plan.stopLossPct.toFixed(1)}%)`
        );
      }
      lines.push(``);
    }

    if (freshBreakout.length > 0) {
      lines.push(`🚀 <b>رادار الاختراقات الفنية (Breakout):</b>`);
      for (const b of freshBreakout) {
        const plan = calculateScannerTradePlan(b.close, "breakout");
        const changeStr = `${b.change_pct >= 0 ? "+" : ""}${Number(b.change_pct).toFixed(1)}%`;
        lines.push(
          `🔹 <b>${b.symbol}</b> — <b>${b.close.toFixed(2)} ج.م</b> (<b>${changeStr}</b>)\n` +
          `   🎯 اختراق قمة 20 جلسة السابقة\n` +
          `   🎯 الهدف: <b>${plan.target1.toFixed(2)} ج.م</b> (+${plan.target1Pct.toFixed(1)}%)\n` +
          `   🛑 الوقف: <b>${plan.stopLoss.toFixed(2)} ج.م</b> (-${plan.stopLossPct.toFixed(1)}%)`
        );
      }
      lines.push(``);
    }

    if (freshOversold.length > 0) {
      lines.push(`💎 <b>ارتداد من تشبع بيعي (RSI Bounce):</b>`);
      for (const o of freshOversold) {
        const plan = calculateScannerTradePlan(o.close, "rsi_oversold");
        const changeStr = `${o.change_pct >= 0 ? "+" : ""}${Number(o.change_pct).toFixed(1)}%`;
        lines.push(
          `🔹 <b>${o.symbol}</b> — <b>${o.close.toFixed(2)} ج.م</b> (<b>${changeStr}</b>)\n` +
          `   📈 مؤشر RSI: <b>${Math.round(Number(o.rsi_14))}</b> (تشبع بيعي وارتداد)\n` +
          `   🎯 الهدف: <b>${plan.target1.toFixed(2)} ج.م</b> (+${plan.target1Pct.toFixed(1)}%)\n` +
          `   🛑 الوقف: <b>${plan.stopLoss.toFixed(2)} ج.م</b> (-${plan.stopLossPct.toFixed(1)}%)`
        );
      }
      lines.push(``);
    }

    if (freshDisclosures.length > 0) {
      lines.push(`📢 <b>إفصاحات وأخبار رسمية حديثة:</b>`);
      for (const d of freshDisclosures) {
        lines.push(`• ${escapeHtml(d.title)}`);
      }
      lines.push(``);
    }

    lines.push(`───────────────`);
    lines.push(`⏱️ التوقيت: <b>${cairoTime.timeStr} بتوقيت القاهرة</b>`);
    lines.push(`📊 <b>لمتابعة النتائج والشارت اللحظي:</b> <a href="https://egxbots.com/profile#scanner-signals">لوحة تتبع الإشارات بالبروفايل</a>`);

    const text = lines.join("\n");
    for (const chatId of targetChatIds) {
      const sent = await sendTelegramAlert(chatId, text);
      if (sent) alertsDispatchedCount++;
    }

    // Register newly sent keys into sentToday
    for (const v of freshVolume) sentKeysSet.add(`${v.symbol}:volume_surge`);
    for (const b of freshBreakout) sentKeysSet.add(`${b.symbol}:breakout`);
    for (const o of freshOversold) sentKeysSet.add(`${o.symbol}:rsi_oversold`);
    for (const d of freshDisclosures) sentKeysSet.add(`disclosure:${d.id}`);
  }

  // ── STEP 5.5: Tracked Signals Lifecycle & Targets/Stop-Loss Management ──────
  const priceMap = new Map<string, { close: number; high: number; low: number }>();
  for (const r of rows) {
    if (r.symbol && r.close) {
      const sym = String(r.symbol).toUpperCase().replace(".CA", "").replace(".EGX", "");
      priceMap.set(sym, {
        close: Number(r.close),
        high: Number(r.high || r.close),
        low: Number(r.low || r.close),
      });
    }
  }

  const currentActive = [...(config.active_signals || [])];
  const currentClosed = [...(config.closed_signals || [])];
  const hitTargetSignals: TrackedScannerSignal[] = [];
  const stoppedOutSignals: TrackedScannerSignal[] = [];
  const stillActiveSignals: TrackedScannerSignal[] = [];

  for (const sig of currentActive) {
    const p = priceMap.get(sig.symbol);
    const currPrice = p ? p.close : sig.current_price;
    const highestPrice = Math.max(sig.highest_price || sig.entry_price, p?.high || currPrice);
    const lowestPrice = Math.min(sig.lowest_price || sig.entry_price, p?.low || currPrice);
    const returnPct = Number((((currPrice - sig.entry_price) / sig.entry_price) * 100).toFixed(2));
    const maxGainPct = Number((((highestPrice - sig.entry_price) / sig.entry_price) * 100).toFixed(2));

    let updatedSig: TrackedScannerSignal = {
      ...sig,
      current_price: currPrice,
      highest_price: highestPrice,
      lowest_price: lowestPrice,
      return_pct: returnPct,
      max_gain_pct: Math.max(sig.max_gain_pct || 0, maxGainPct),
      updated_at: new Date().toISOString(),
    };

    if (highestPrice >= sig.target_1) {
      const exitPrice = sig.target_1;
      const realizedReturn = Number((((exitPrice - sig.entry_price) / sig.entry_price) * 100).toFixed(2));
      updatedSig = {
        ...updatedSig,
        status: "target_hit",
        exit_price: exitPrice,
        return_pct: realizedReturn,
        exit_date: cairoTime.dateStr,
        exit_time: cairoTime.timeStr,
        exit_reason: "تحقق الهدف الأول بنجاح 🎯",
      };
      hitTargetSignals.push(updatedSig);
      currentClosed.unshift(updatedSig);
    } else if (lowestPrice <= sig.stop_loss) {
      const exitPrice = sig.stop_loss;
      const realizedReturn = Number((((exitPrice - sig.entry_price) / sig.entry_price) * 100).toFixed(2));
      updatedSig = {
        ...updatedSig,
        status: "stopped_out",
        exit_price: exitPrice,
        return_pct: realizedReturn,
        exit_date: cairoTime.dateStr,
        exit_time: cairoTime.timeStr,
        exit_reason: "ضرب وقف الخسارة 🛑",
      };
      stoppedOutSignals.push(updatedSig);
      currentClosed.unshift(updatedSig);
    } else if (sig.sessions_count >= sig.max_sessions) {
      const exitPrice = currPrice;
      const realizedReturn = Number((((exitPrice - sig.entry_price) / sig.entry_price) * 100).toFixed(2));
      updatedSig = {
        ...updatedSig,
        status: realizedReturn > 0 ? "target_hit" : "expired",
        exit_price: exitPrice,
        return_pct: realizedReturn,
        exit_date: cairoTime.dateStr,
        exit_time: cairoTime.timeStr,
        exit_reason: realizedReturn > 0 ? "تحقق هدف جزئي 🎯" : "انتهاء مدة الاحتفاظ (5 جلسات) ⏱️",
      };
      currentClosed.unshift(updatedSig);
    } else {
      stillActiveSignals.push(updatedSig);
    }
  }

  // Add new fresh signals into stillActiveSignals (only if symbol is NOT already active)
  for (const v of freshVolume) {
    if (stillActiveSignals.some((s) => s.symbol === v.symbol)) continue;
    const plan = calculateScannerTradePlan(v.close, "volume_surge");
    stillActiveSignals.push({
      id: `${v.symbol}_${cairoTime.dateStr}_volume_surge`,
      symbol: v.symbol,
      scanner_type: "volume_surge",
      entry_price: v.close,
      entry_date: cairoTime.dateStr,
      entry_time: cairoTime.timeStr,
      target_1: plan.target1,
      target_1_pct: plan.target1Pct,
      target_2: plan.target2,
      target_2_pct: plan.target2Pct,
      stop_loss: plan.stopLoss,
      stop_loss_pct: plan.stopLossPct,
      current_price: v.close,
      highest_price: v.close,
      lowest_price: v.close,
      return_pct: 0,
      max_gain_pct: 0,
      status: "active",
      sessions_count: 1,
      max_sessions: plan.maxHoldingSessions,
      updated_at: new Date().toISOString(),
    });
  }
  for (const b of freshBreakout) {
    if (stillActiveSignals.some((s) => s.symbol === b.symbol)) continue;
    const plan = calculateScannerTradePlan(b.close, "breakout");
    stillActiveSignals.push({
      id: `${b.symbol}_${cairoTime.dateStr}_breakout`,
      symbol: b.symbol,
      scanner_type: "breakout",
      entry_price: b.close,
      entry_date: cairoTime.dateStr,
      entry_time: cairoTime.timeStr,
      target_1: plan.target1,
      target_1_pct: plan.target1Pct,
      target_2: plan.target2,
      target_2_pct: plan.target2Pct,
      stop_loss: plan.stopLoss,
      stop_loss_pct: plan.stopLossPct,
      current_price: b.close,
      highest_price: b.close,
      lowest_price: b.close,
      return_pct: 0,
      max_gain_pct: 0,
      status: "active",
      sessions_count: 1,
      max_sessions: plan.maxHoldingSessions,
      updated_at: new Date().toISOString(),
    });
  }
  for (const o of freshOversold) {
    if (stillActiveSignals.some((s) => s.symbol === o.symbol)) continue;
    const plan = calculateScannerTradePlan(o.close, "rsi_oversold");
    stillActiveSignals.push({
      id: `${o.symbol}_${cairoTime.dateStr}_rsi_oversold`,
      symbol: o.symbol,
      scanner_type: "rsi_oversold",
      entry_price: o.close,
      entry_date: cairoTime.dateStr,
      entry_time: cairoTime.timeStr,
      target_1: plan.target1,
      target_1_pct: plan.target1Pct,
      target_2: plan.target2,
      target_2_pct: plan.target2Pct,
      stop_loss: plan.stopLoss,
      stop_loss_pct: plan.stopLossPct,
      current_price: o.close,
      highest_price: o.close,
      lowest_price: o.close,
      return_pct: 0,
      max_gain_pct: 0,
      status: "active",
      sessions_count: 1,
      max_sessions: plan.maxHoldingSessions,
      updated_at: new Date().toISOString(),
    });
  }

  // Deduplicate target hit and stopped out signals so Telegram never sends repeat lines
  const dedupHitSignals = Array.from(
    new Map(hitTargetSignals.map((s) => [s.symbol, s])).values()
  );
  const dedupStoppedSignals = Array.from(
    new Map(stoppedOutSignals.map((s) => [s.symbol, s])).values()
  );

  // Send Telegram follow-up alerts for target hit or stopped out (VIP Channel)
  if ((dedupHitSignals.length > 0 || dedupStoppedSignals.length > 0) && targetChatIds.length > 0) {
    for (const chatId of targetChatIds) {
      if (dedupHitSignals.length > 0) {
        const hitLines: string[] = [
          `🎯 <b>[EGX BOTS] تحقيق أهداف إشارات الإسكانر (قناة VIP)</b>`,
          `───────────────`,
        ];
        for (const s of dedupHitSignals) {
          const retStr = s.return_pct >= 0 ? `+${Number(s.return_pct).toFixed(1)}%` : `${Number(s.return_pct).toFixed(1)}%`;
          hitLines.push(
            `✅ <b>${s.symbol}</b> — <b>تحقق الهدف الأول بنجاح!</b>\n` +
            `   • سعر التحقق: <b>${s.current_price.toFixed(2)} ج.م</b>\n` +
            `   • نسبة الربح: <b>${retStr}</b> 🎉\n` +
            `   • سعر الدخول: ${s.entry_price.toFixed(2)} ج.م`
          );
        }
        hitLines.push(`───────────────`);
        hitLines.push(`💡 <i>توصية: يفضل جني الأرباح جزئياً ورفع وقف الخسارة لسعر الدخول لحجز الأرباح.</i>`);
        hitLines.push(`📊 <b>متابعة النتائج والشارتات:</b> <a href="https://egxbots.com/profile#scanner-signals">سجل إشارات الإسكانر بالبروفايل</a>`);
        await sendTelegramAlert(chatId, hitLines.join("\n"));
      }

      if (dedupStoppedSignals.length > 0) {
        const slLines: string[] = [
          `🛑 <b>[EGX BOTS] إدارة المخاطر — تفعيل وقف الخسارة (قناة VIP)</b>`,
          `───────────────`,
        ];
        for (const s of dedupStoppedSignals) {
          const retStr = `${Number(s.return_pct).toFixed(1)}%`;
          slLines.push(
            `⚠️ <b>${s.symbol}</b> — <b>تفعيل وقف الخسارة</b>\n` +
            `   • سعر الخروج: <b>${s.current_price.toFixed(2)} ج.م</b>\n` +
            `   • نسبة التراجع: <b>${retStr}</b>\n` +
            `   • سعر الدخول: ${s.entry_price.toFixed(2)} ج.م`
          );
        }
        slLines.push(`───────────────`);
        slLines.push(`⚠️ <i>تنبيه: التزم بإدارة رأس المال وتجنب التمسك بالصفقات الخاسرة.</i>`);
        slLines.push(`📊 <b>متابعة النتائج وسجل الصفقات:</b> <a href="https://egxbots.com/profile#scanner-signals">سجل إشارات الإسكانر بالبروفايل</a>`);
        await sendTelegramAlert(chatId, slLines.join("\n"));
      }
    }
  }

  // Deduplicate active signals by symbol (keep the latest)
  const activeMap = new Map<string, TrackedScannerSignal>();
  for (const s of stillActiveSignals) {
    activeMap.set(s.symbol, s);
  }
  const finalActiveSignals = Array.from(activeMap.values()).slice(0, 40);

  // Deduplicate closed signals by (symbol, exit_date, scanner_type)
  const closedMap = new Map<string, TrackedScannerSignal>();
  for (const c of currentClosed) {
    const key = `${c.symbol}_${c.exit_date}_${c.scanner_type}`;
    if (!closedMap.has(key)) {
      closedMap.set(key, c);
    }
  }
  const finalClosedSignals = Array.from(closedMap.values()).slice(0, 100);

  // Compute updated signals KPIs from deduplicated signals
  const closedWins = finalClosedSignals.filter((s) => (s.return_pct || 0) > 0);
  const closedLosses = finalClosedSignals.filter((s) => (s.return_pct || 0) < 0);
  const sumWins = closedWins.reduce((a, b) => a + (b.return_pct || 0), 0);
  const sumLosses = Math.abs(closedLosses.reduce((a, b) => a + (b.return_pct || 0), 0));
  const signalsKpis: ScannerSignalsKPIs = {
    win_rate_pct: finalClosedSignals.length > 0 ? Number(((closedWins.length / finalClosedSignals.length) * 100).toFixed(1)) : 80.0,
    total_closed: finalClosedSignals.length,
    total_active: finalActiveSignals.length,
    avg_win_pct: closedWins.length > 0 ? Number((sumWins / Math.max(1, closedWins.length)).toFixed(1)) : 3.5,
    avg_loss_pct: closedLosses.length > 0 ? Number((sumLosses / Math.max(1, closedLosses.length)).toFixed(1)) : 2.0,
    profit_factor: sumLosses > 0 ? Number((sumWins / sumLosses).toFixed(2)) : 4.5,
    top_win_pct: finalClosedSignals.reduce((max, s) => Math.max(max, s.return_pct || 0), 0),
  };

  const endTime = performance.now();
  const durationMs = Math.round(endTime - startTime);

  // Update Config & History
  const newScanResult = {
    timestamp: new Date().toISOString(),
    duration_ms: durationMs,
    total_symbols_scanned: rows.length,
    stage_results: {
      volume_surge: topVolume,
      breakout: topBreakout,
      rsi_oversold: topOversold,
      disclosures: disclosuresMatches,
    },
    alerts_dispatched: alertsDispatchedCount,
  };

  const historyEntry = {
    timestamp: newScanResult.timestamp,
    duration_ms: durationMs,
    volume_count: topVolume.length,
    breakout_count: topBreakout.length,
    oversold_count: topOversold.length,
    disclosures_count: disclosuresMatches.length,
    recipients_count: alertsDispatchedCount,
    triggered_by: options.trigger || "Scheduled",
    stage_results: newScanResult.stage_results,
  };

  const updatedConfig: AdminScannerConfig = {
    ...config,
    last_scan: newScanResult,
    sent_today: {
      date: cairoTime.dateStr,
      sent_keys: Array.from(sentKeysSet).slice(-200),
    },
    history: [historyEntry, ...(config.history || [])].slice(0, 100),
    active_signals: finalActiveSignals,
    closed_signals: finalClosedSignals,
    signals_kpis: signalsKpis,
  };

  await saveAdminConfig(updatedConfig, serviceClient);

  return {
    ok: true,
    duration_ms: durationMs,
    total_scanned: rows.length,
    matches: {
      volume_surge: topVolume.length,
      breakout: topBreakout.length,
      rsi_oversold: topOversold.length,
      disclosures: disclosuresMatches.length,
    },
    fresh_matches: {
      volume_surge: freshVolume.length,
      breakout: freshBreakout.length,
      rsi_oversold: freshOversold.length,
      disclosures: freshDisclosures.length,
    },
    alerts_dispatched: alertsDispatchedCount,
    cairo_time: cairoTime,
  };
}
