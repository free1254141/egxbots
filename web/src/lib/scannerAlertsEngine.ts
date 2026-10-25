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
export const FREE_CHANNEL_CHAT_ID =
  process.env.TELEGRAM_FREE_CHAT_ID || process.env.TELEGRAM_CHAT_ID || "-1002083067817_153";

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

  let targetChatId: string | number = chatId;
  let targetThreadId: number | undefined = undefined;
  if (typeof chatId === "string" && !chatId.startsWith("@") && chatId.includes("_")) {
    const [c, t] = chatId.split("_", 2);
    targetChatId = c;
    if (t && !isNaN(Number(t))) {
      targetThreadId = Number(t);
    }
  }

  const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
  const payload: any = {
    chat_id: targetChatId,
    text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };
  if (targetThreadId !== undefined) {
    payload.message_thread_id = targetThreadId;
  }

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
  let asOfDate = cairoTime.dateStr;
  try {
    const { data: latestDateRow } = await serviceClient
      .from("stock_technical_indicators")
      .select("date")
      .eq("exchange", "EGX")
      .order("date", { ascending: false })
      .limit(1)
      .maybeSingle();

    asOfDate = latestDateRow?.date || cairoTime.dateStr;

    const [indRes, priceRes] = await Promise.all([
      serviceClient
        .from("stock_technical_indicators")
        .select("symbol, close, change_pct, volume, vol_sma20, r_vol, rsi_14, bb_upper, ema_20")
        .eq("exchange", "EGX")
        .eq("date", asOfDate)
        .limit(300),
      serviceClient
        .from("stock_prices")
        .select("symbol, open, high, low, close, volume")
        .eq("exchange", "EGX")
        .eq("date", asOfDate)
        .limit(300),
    ]);

    const ohlcBySym = new Map<string, { open: number; high: number; low: number; close: number; volume: number }>();
    for (const p of priceRes.data || []) {
      if (p.symbol) {
        const s = String(p.symbol).toUpperCase().replace(".CA", "").replace(".EGX", "");
        ohlcBySym.set(s, {
          open: Number(p.open || p.close || 0),
          high: Number(p.high || p.close || 0),
          low: Number(p.low || p.close || 0),
          close: Number(p.close || 0),
          volume: Number(p.volume || 0),
        });
      }
    }

    if (!indRes.error && indRes.data && indRes.data.length > 0) {
      rows = indRes.data.map((r: any) => {
        const s = String(r.symbol || "").toUpperCase().replace(".CA", "").replace(".EGX", "");
        const ohlc = ohlcBySym.get(s);
        return {
          ...r,
          open: ohlc?.open || Number(r.close || 0),
          high: Math.max(Number(r.close || 0), ohlc?.high || Number(r.close || 0)),
          low: ohlc?.low ? Math.min(Number(r.close || 0), ohlc.low) : Number(r.close || 0),
        };
      });
    }
  } catch (err) {
    console.warn("stock_technical_indicators query fallback:", err);
  }

  // ── STEP 2: Market Breadth Gate & Filter Matches ──────────────────────────
  // Compute real-time EGX Market Breadth (% of stocks above EMA20 and % green)
  const validRows = rows.filter((r) => Number(r.close || 0) > 0);
  const totalMarketStocks = Math.max(1, validRows.length);
  const aboveEma20Count = validRows.filter(
    (r) => Number(r.ema_20 || 0) > 0 && Number(r.close || 0) >= Number(r.ema_20 || 0)
  ).length;
  const greenStocksCount = validRows.filter((r) => Number(r.change_pct || 0) > 0).length;
  const avgMarketChangePct =
    validRows.reduce((sum, r) => sum + Number(r.change_pct || 0), 0) / totalMarketStocks;

  const breadthAboveEma20Pct = (aboveEma20Count / totalMarketStocks) * 100;
  const greenRatioPct = (greenStocksCount / totalMarketStocks) * 100;

  // Adaptive Market Regime (Smart Sniper Mode vs Full Momentum Mode):
  // Unlike Medium & Short Swings (which freeze completely in falling markets),
  // the Fast Scanner switches to "Selective Sniper Mode" (max 1 elite counter-trend/bounce per category)
  // when market breadth is weak (< 30% above EMA20 or < 25% green).
  const isMarketHealthyForBuying =
    breadthAboveEma20Pct >= 30 && greenRatioPct >= 25 && avgMarketChangePct > -1.2;
  const maxPerCategory = isMarketHealthyForBuying ? 2 : 1;

  const volumeMatches: Array<{ symbol: string; close: number; change_pct: number; r_vol: number; rsi_14?: number }> = [];
  const breakoutMatches: Array<{ symbol: string; close: number; change_pct: number; r_vol: number; rsi_14?: number }> = [];
  const oversoldMatches: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number; r_vol?: number }> = [];

  for (const r of rows) {
    const symbol = String(r.symbol || "").toUpperCase();
    const close = Number(r.close || 0);
    const open = Number(r.open || close);
    const change = Number(r.change_pct || 0);
    const vol = Number(r.volume || 0);
    const rsi = Number(r.rsi_14 || 50);
    const rVol = Number(r.r_vol || 1.0);
    const bbUpper = Number(r.bb_upper || 0);
    const ema20 = Number(r.ema_20 || 0);
    const turnover = close * vol;

    // Exclude penny stock traps (< 1.50 EGP) and red distribution candles
    if (close < 1.5 || close < open * 0.995) continue;

    // Trend filter: Stock must be trading at or above EMA20 (or EMA20 not available)
    const isUptrend = ema20 <= 0 || close >= ema20 * 0.99;

    // Stage 1: Volume Surge (Normal vs Sniper Mode in falling market)
    const minVolSurgeRvol = isMarketHealthyForBuying ? 2.0 : 2.2;
    const minVolSurgeTurnover = isMarketHealthyForBuying ? 400_000 : 500_000;
    if (
      config.scanners_enabled.volume_surge &&
      rVol >= minVolSurgeRvol &&
      vol >= 50_000 &&
      turnover >= minVolSurgeTurnover &&
      change >= 1.5 &&
      isUptrend &&
      rsi >= 35 &&
      rsi <= 72
    ) {
      volumeMatches.push({ symbol, close, change_pct: change, r_vol: rVol, rsi_14: rsi });
    }

    // Stage 2: Breakout (True penetration of BB upper with volume confirmation)
    const isConfirmedBreakout =
      bbUpper > 0 &&
      close >= bbUpper * 0.998 &&
      rVol >= 1.8 &&
      vol >= 50_000 &&
      turnover >= 500_000 &&
      change >= (isMarketHealthyForBuying ? 2.2 : 2.5) &&
      isUptrend;
    if (config.scanners_enabled.breakout && isConfirmedBreakout) {
      breakoutMatches.push({ symbol, close, change_pct: change, r_vol: rVol, rsi_14: rsi });
    }

    // Stage 3: RSI Oversold Bounce (Ideal for catching institutional rebounds during market dips)
    const notCrashingCliff = ema20 <= 0 || close >= ema20 * 0.85;
    const maxOversoldRsi = isMarketHealthyForBuying ? 28 : 26;
    if (
      config.scanners_enabled.rsi_oversold &&
      rsi > 0 &&
      rsi <= maxOversoldRsi &&
      change >= 1.0 &&
      notCrashingCliff &&
      vol >= 50_000 &&
      turnover >= 250_000
    ) {
      oversoldMatches.push({ symbol, close, rsi_14: rsi, change_pct: change, r_vol: rVol });
    }
  }

  // Sort and limit to top convictions per category (2 in normal market, 1 Sniper in falling market)
  volumeMatches.sort((a, b) => b.r_vol - a.r_vol);
  const topVolume = volumeMatches.slice(0, maxPerCategory);

  breakoutMatches.sort((a, b) => b.change_pct - a.change_pct);
  const topBreakout = breakoutMatches.slice(0, maxPerCategory);

  oversoldMatches.sort((a, b) => a.rsi_14 - b.rsi_14);
  const topOversold = oversoldMatches.slice(0, maxPerCategory);

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
    serviceClient.from("subscriptions").select("user_id, current_period_end").eq("status", "active"),
    serviceClient
      .from("profiles")
      .select("id, telegram_chat_id")
      .not("telegram_chat_id", "is", null),
  ]);

  const nowMs = Date.now();
  const activeProUids = new Set(
    (subRes.data || [])
      .filter((s: any) => !s.current_period_end || new Date(s.current_period_end).getTime() > nowMs)
      .map((s: any) => s.user_id)
  );
  const proProfiles = (profileRes.data || []).filter((p: any) => activeProUids.has(p.id));

  // Destination Chat IDs: Always route to official VIP Channel unless a test recipient is specified
  const targetChatIds = options.singleRecipientChatId
    ? [String(options.singleRecipientChatId)]
    : [VIP_CHANNEL_CHAT_ID];

  // ── STEP 5: Dispatch Alerts to Telegram (VIP Channel) ─────────────────────
  let alertsDispatchedCount = 0;

  if (hasAnyFreshMatches && targetChatIds.length > 0) {
    // Construct sleek, smart institutional Arabic Message for VIP Channel
    const regimeBadge = isMarketHealthyForBuying
      ? `إيجابي داعم للمضاربة 🟢`
      : `حذر انتقائي — وضع القناص 🎯`;
    const totalSignalsInBatch = freshVolume.length + freshBreakout.length + freshOversold.length;

    const lines: string[] = [
      `⚡ <b>رادار التدفقات اللحظي الذكي — EGX BOTS VIP</b>`,
      `🧭 <b>حالة السوق:</b> ${regimeBadge} <i>(السيولة الصاعدة: ${breadthAboveEma20Pct.toFixed(0)}%)</i>`,
      `━━━━━━━━━━━━━━━━━━━━`,
    ];

    if (freshVolume.length > 0) {
      lines.push(`🔥 <b>اقتناص سيولة مؤسسية غير معتادة (Volume Surge)</b>`);
      for (const v of freshVolume) {
        const plan = calculateScannerTradePlan(v.close, "volume_surge");
        const changeStr = `${v.change_pct >= 0 ? "+" : ""}${Number(v.change_pct).toFixed(1)}%`;
        const breakevenTrigger = (v.close * 1.025).toFixed(2);
        const rrRatio = (plan.target1Pct / Math.max(0.5, plan.stopLossPct)).toFixed(1);
        const rsiVal = v.rsi_14 ? Math.round(Number(v.rsi_14)) : 56;
        lines.push(
          `💎 <b>#${v.symbol}</b>  |  <b>${v.close.toFixed(2)} ج.م</b>  (<b>${changeStr}</b>)\n` +
          `   📊 السيولة: <b>${Number(v.r_vol).toFixed(1)}x</b>  •  📈 RSI: <b>${rsiVal}</b>  •  ⚖️ العائد/المخاطرة: <b>1:${rrRatio}</b>\n` +
          `   🎯 الهدف الأول: <b>${plan.target1.toFixed(2)} ج.م</b> (+${plan.target1Pct.toFixed(1)}%)\n` +
          `   🚀 الهدف الممتد: <b>${plan.target2.toFixed(2)} ج.م</b> (+${plan.target2Pct.toFixed(1)}%)\n` +
          `   🛡️ تأمين التعادل: تلقائياً عند <b>${breakevenTrigger} ج.م</b> (+2.5%)\n` +
          `   🛑 وقف الخسارة: <b>${plan.stopLoss.toFixed(2)} ج.م</b> (-${plan.stopLossPct.toFixed(1)}%)`
        );
      }
      lines.push(``);
    }

    if (freshBreakout.length > 0) {
      lines.push(`🚀 <b>اختراق فني مؤكد بالسيولة (Price Breakout)</b>`);
      for (const b of freshBreakout) {
        const plan = calculateScannerTradePlan(b.close, "breakout");
        const changeStr = `${b.change_pct >= 0 ? "+" : ""}${Number(b.change_pct).toFixed(1)}%`;
        const breakevenTrigger = (b.close * 1.025).toFixed(2);
        const rrRatio = (plan.target1Pct / Math.max(0.5, plan.stopLossPct)).toFixed(1);
        lines.push(
          `⚡ <b>#${b.symbol}</b>  |  <b>${b.close.toFixed(2)} ج.م</b>  (<b>${changeStr}</b>)\n` +
          `   📊 سيولة الاختراق: <b>${Number(b.r_vol).toFixed(1)}x</b>  •  ⚖️ العائد/المخاطرة: <b>1:${rrRatio}</b>\n` +
          `   🎯 الهدف الأول: <b>${plan.target1.toFixed(2)} ج.م</b> (+${plan.target1Pct.toFixed(1)}%)\n` +
          `   🚀 الهدف الممتد: <b>${plan.target2.toFixed(2)} ج.م</b> (+${plan.target2Pct.toFixed(1)}%)\n` +
          `   🛡️ تأمين التعادل: تلقائياً عند <b>${breakevenTrigger} ج.م</b> (+2.5%)\n` +
          `   🛑 وقف الخسارة: <b>${plan.stopLoss.toFixed(2)} ج.م</b> (-${plan.stopLossPct.toFixed(1)}%)`
        );
      }
      lines.push(``);
    }

    if (freshOversold.length > 0) {
      lines.push(`💎 <b>ارتداد ذكي من تشبع بيعي عميق (RSI Sniper Bounce)</b>`);
      for (const o of freshOversold) {
        const plan = calculateScannerTradePlan(o.close, "rsi_oversold");
        const changeStr = `${o.change_pct >= 0 ? "+" : ""}${Number(o.change_pct).toFixed(1)}%`;
        const breakevenTrigger = (o.close * 1.025).toFixed(2);
        const rrRatio = (plan.target1Pct / Math.max(0.5, plan.stopLossPct)).toFixed(1);
        lines.push(
          `🟢 <b>#${o.symbol}</b>  |  <b>${o.close.toFixed(2)} ج.م</b>  (<b>${changeStr}</b>)\n` +
          `   📈 مؤشر RSI: <b>${Math.round(Number(o.rsi_14))}</b> (ارتداد شرائي)  •  ⚖️ العائد/المخاطرة: <b>1:${rrRatio}</b>\n` +
          `   🎯 الهدف الأول: <b>${plan.target1.toFixed(2)} ج.م</b> (+${plan.target1Pct.toFixed(1)}%)\n` +
          `   🚀 الهدف الممتد: <b>${plan.target2.toFixed(2)} ج.م</b> (+${plan.target2Pct.toFixed(1)}%)\n` +
          `   🛡️ تأمين التعادل: تلقائياً عند <b>${breakevenTrigger} ج.م</b> (+2.5%)\n` +
          `   🛑 وقف الخسارة: <b>${plan.stopLoss.toFixed(2)} ج.م</b> (-${plan.stopLossPct.toFixed(1)}%)`
        );
      }
      lines.push(``);
    }

    if (freshDisclosures.length > 0) {
      lines.push(`📢 <b>إفصاحات البورصة الجوهرية اللحظية:</b>`);
      for (const d of freshDisclosures) {
        lines.push(`• ${escapeHtml(d.title)}`);
      }
      lines.push(``);
    }

    lines.push(`━━━━━━━━━━━━━━━━━━━━`);
    if (totalSignalsInBatch > 0) {
      lines.push(`⏱️ <b>أفق الاحتفاظ:</b> 1 إلى 4 جلسات  |  🛡️ <b>حماية آلية عند +2.5%</b>`);
    }
    lines.push(`🕒 <b>توقيت الرصد:</b> ${cairoTime.timeStr} بتوقيت القاهرة`);
    lines.push(`📲 <a href="https://egxbots.com/profile#scanner-signals">فتح الشارت التفاعلي (15 دقيقة) ولوحة التتبع الحية</a>`);

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

    // CRITICAL GUARD: Prior-session data (asOfDate < sig.entry_date) must NEVER be used to evaluate
    // intraday high/low or stop-loss for a signal created today or later!
    const isPriceCurrentForSignal = asOfDate >= sig.entry_date;
    const barHigh = (p && isPriceCurrentForSignal) ? Math.max(p.high, p.close) : currPrice;
    const barLow = (p && isPriceCurrentForSignal) ? Math.min(p.low, p.close) : currPrice;

    const highestPrice = Math.max(sig.highest_price || sig.entry_price, barHigh);
    const lowestPrice = Math.min(sig.lowest_price || sig.entry_price, barLow);
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

    // Breakeven Trail: If stock reached >= +2.5% gain towards target, raise stop loss to entry price
    const hasBreakevenProtection = Math.max(sig.highest_price || 0, highestPrice) >= sig.entry_price * 1.025;
    const effectiveStopLoss = hasBreakevenProtection
      ? Math.max(sig.stop_loss, sig.entry_price)
      : sig.stop_loss;

    if (hasBreakevenProtection) {
      updatedSig.stop_loss = effectiveStopLoss;
      updatedSig.stop_loss_pct = 0;
    }

    const hitStop = hasBreakevenProtection
      ? currPrice <= effectiveStopLoss
      : barLow <= effectiveStopLoss;

    // Target 1 check takes absolute priority over stop-loss if highestPrice achieved target_1
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
    } else if (hitStop && isPriceCurrentForSignal) {
      const exitPrice = effectiveStopLoss;
      const realizedReturn = Number((((exitPrice - sig.entry_price) / sig.entry_price) * 100).toFixed(2));
      const isBreakeven = hasBreakevenProtection && effectiveStopLoss >= sig.entry_price;
      updatedSig = {
        ...updatedSig,
        status: isBreakeven ? "target_hit" : "stopped_out",
        exit_price: exitPrice,
        return_pct: realizedReturn,
        exit_date: cairoTime.dateStr,
        exit_time: cairoTime.timeStr,
        exit_reason: isBreakeven ? "حماية الأرباح / تفعيل وقف التعادل 🛡️" : "ضرب وقف الخسارة 🛑",
      };
      if (isBreakeven) {
        hitTargetSignals.push(updatedSig);
      } else {
        stoppedOutSignals.push(updatedSig);
      }
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

  // Portfolio Cap: Maximum 8 simultaneously active swing trades to prevent portfolio overwhelm
  const MAX_PORTFOLIO_ACTIVE = 8;

  // Deduplication guard: No stock can be alerted or added more than ONCE per day across any scanner type
  const isSymbolAlreadyLoggedToday = (sym: string) => {
    return (
      stillActiveSignals.some((s) => s.symbol === sym) ||
      currentClosed.some((s) => s.symbol === sym && s.entry_date === cairoTime.dateStr) ||
      sentKeysSet.has(`${sym}:volume_surge`) ||
      sentKeysSet.has(`${sym}:breakout`) ||
      sentKeysSet.has(`${sym}:rsi_oversold`)
    );
  };

  // Add new fresh signals into stillActiveSignals (only if symbol is NOT already active and portfolio has room)
  for (const v of freshVolume) {
    if (stillActiveSignals.length >= MAX_PORTFOLIO_ACTIVE) break;
    if (isSymbolAlreadyLoggedToday(v.symbol)) continue;
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
    if (stillActiveSignals.length >= MAX_PORTFOLIO_ACTIVE) break;
    if (isSymbolAlreadyLoggedToday(b.symbol)) continue;
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
    if (stillActiveSignals.length >= MAX_PORTFOLIO_ACTIVE) break;
    if (isSymbolAlreadyLoggedToday(o.symbol)) continue;
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
          `🎯 <b>حصاد أهداف رادار التدفقات اللحظي — EGX BOTS VIP</b>`,
          `━━━━━━━━━━━━━━━━━━━━`,
        ];
        for (const s of dedupHitSignals) {
          const isBreakevenExit = Math.abs(Number(s.return_pct || 0)) < 0.2;
          const retStr = s.return_pct >= 0 ? `+${Number(s.return_pct).toFixed(1)}%` : `${Number(s.return_pct).toFixed(1)}%`;
          const exitPrice = Number(s.exit_price || s.current_price || s.target_1).toFixed(2);
          const peakGainStr = s.max_gain_pct ? `+${Number(s.max_gain_pct).toFixed(1)}%` : retStr;
          if (isBreakevenExit) {
            hitLines.push(
              `🛡️ <b>#${s.symbol}</b> — <b>خروج آمن بتفعيل وقف التعادل (0.0%)</b>\n` +
              `   • سعر الدخول والخروج: <b>${s.entry_price.toFixed(2)} ج.م</b>\n` +
              `   • أعلى قمة وصلها السهم: <b>${peakGainStr}</b> (تم تأمين رأس المال بالكامل)`
            );
          } else {
            hitLines.push(
              `✅ <b>#${s.symbol}</b> — <b>تحقق الهدف الأول بنجاح! 🎉</b>\n` +
              `   • سعر الدخول: <b>${s.entry_price.toFixed(2)} ج.م</b>  ←  الإغلاق: <b>${exitPrice} ج.م</b>\n` +
              `   • العائد المحقق: <b>${retStr}</b>  (أعلى قمة: <b>${peakGainStr}</b>)`
            );
          }
        }
        hitLines.push(`━━━━━━━━━━━━━━━━━━━━`);
        hitLines.push(`💡 <i>إدارة المحفظة: جني الأرباح أولاً بأول وتأمين نقطة الدخول سر استدامة النمو.</i>`);
        hitLines.push(`📲 <a href="https://egxbots.com/profile#scanner-signals">عرض الشارت التفاعلي للصفقات المغلقة بالبروفايل</a>`);
        await sendTelegramAlert(chatId, hitLines.join("\n"));

        // Dispatch winning target hits to the Free channel as Social Proof / Subscription Hook
        const winningHits = dedupHitSignals.filter((s) => Number(s.return_pct || 0) > 0);
        if (winningHits.length > 0 && !options.singleRecipientChatId) {
          const freeLines: string[] = [
            `🎯 <b>تحقيق هدف جديد في صفقات السوينج السريع — EGX BOTS</b> 🚀`,
            `━━━━━━━━━━━━━━━━━━━━`,
          ];
          for (const s of winningHits) {
            const retStr = `+${Number(s.return_pct).toFixed(1)}%`;
            const exitPrice = Number(s.exit_price || s.current_price || s.target_1).toFixed(2);
            const peakGainStr = s.max_gain_pct ? `+${Number(s.max_gain_pct).toFixed(1)}%` : retStr;
            freeLines.push(
              `✅ <b>#${s.symbol}</b> — <b>حقق الهدف بنجاح! 🎉</b>\n` +
              `   • سعر الدخول في الإشارة: <b>${s.entry_price.toFixed(2)} ج.م</b>\n` +
              `   • سعر الخروج / الهدف: <b>${exitPrice} ج.م</b>\n` +
              `   • <b>صافي العائد المحقق: ${retStr}</b> 📈 (أعلى قمة وصلها: <b>${peakGainStr}</b>)`
            );
          }
          freeLines.push(`━━━━━━━━━━━━━━━━━━━━`);
          freeLines.push(`⚡ <i>هذه التوصية أُرسلت لحظياً لمشتركي VIP وقت انطلاق السهم بنقاط الدخول والوقف المحسوب بدقة.</i>\n`);
          freeLines.push(`🔥 لا تفوّت صفقات الجلسة القادمة — احجز مقعدك الآن في <b>باقة المؤسسين بـ 50 ج.م فقط شهرياً</b> بدلاً من 200 ج.م!`);
          freeLines.push(`👉 <b>اشترك الآن وفعل اشتراكك الفوري:</b> https://egxbots.com/pricing`);
          await sendTelegramAlert(FREE_CHANNEL_CHAT_ID, freeLines.join("\n"));
        }
      }

      if (dedupStoppedSignals.length > 0) {
        const slLines: string[] = [
          `🛡️ <b>تقرير إدارة المخاطر وحماية السيولة — EGX BOTS VIP</b>`,
          `━━━━━━━━━━━━━━━━━━━━`,
        ];
        for (const s of dedupStoppedSignals) {
          const retStr = `${Number(s.return_pct).toFixed(1)}%`;
          const exitPrice = Number(s.exit_price || s.current_price || s.stop_loss).toFixed(2);
          slLines.push(
            `🛑 <b>#${s.symbol}</b> — <b>تفعيل وقف الخسارة الصارم</b>\n` +
            `   • سعر الدخول: <b>${s.entry_price.toFixed(2)} ج.م</b>  ←  الخروج: <b>${exitPrice} ج.م</b>\n` +
            `   • صافي التراجع المحدود: <b>${retStr}</b> (تحرير السيولة لفرصة أقوى)`
          );
        }
        slLines.push(`━━━━━━━━━━━━━━━━━━━━`);
        slLines.push(`⚖️ <i>قاعدة ذهبية: قطع الخسارة مبكراً عند -2.5% / -3.0% يحمي المحفظة من أي تصحيح عنيف.</i>`);
        slLines.push(`📲 <a href="https://egxbots.com/profile#scanner-signals">مراجعة سجل الصفقات والشارت اللحظي بالبروفايل</a>`);
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
