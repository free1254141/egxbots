import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

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
  }>;
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
};

const BOT_STATE_KEY = "scanner_alerts";

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

/** Send individual Telegram message with fallback to relay URL */
export async function sendTelegramAlert(chatId: string | number, text: string): Promise<boolean> {
  const token = process.env.ARTORO_AI_BOT?.trim();
  if (!token || !chatId) return false;

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
      if (base === relayUrl) continue;
    } catch {
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
  const freshVolume = options.forceDispatch
    ? topVolume
    : topVolume.filter((s) => !sentKeysSet.has(`${s.symbol}:volume_surge`));

  const freshBreakout = options.forceDispatch
    ? topBreakout
    : topBreakout.filter((s) => !sentKeysSet.has(`${s.symbol}:breakout`));

  const freshOversold = options.forceDispatch
    ? topOversold
    : topOversold.filter((s) => !sentKeysSet.has(`${s.symbol}:rsi_oversold`));

  const freshDisclosures = options.forceDispatch
    ? disclosuresMatches
    : disclosuresMatches.filter((d) => !sentKeysSet.has(`disclosure:${d.id}`));

  const hasAnyFreshMatches =
    freshVolume.length > 0 || freshBreakout.length > 0 || freshOversold.length > 0 || freshDisclosures.length > 0;

  // ── STEP 4: Query Active Pro Subscribers ──────────────────────────────────
  const [subRes, profileRes] = await Promise.all([
    serviceClient.from("subscriptions").select("user_id").eq("status", "active"),
    serviceClient
      .from("profiles")
      .select("id, telegram_chat_id")
      .not("telegram_chat_id", "is", null),
  ]);

  const activeProUids = new Set((subRes.data || []).map((s: any) => s.user_id));
  const proProfiles = (profileRes.data || []).filter((p: any) => activeProUids.has(p.id));

  // If specific recipient requested (e.g. testing)
  const targetProfiles = options.singleRecipientChatId
    ? proProfiles.filter((p: any) => String(p.telegram_chat_id) === String(options.singleRecipientChatId))
    : proProfiles;

  // ── STEP 5: Dispatch Alerts to Telegram ───────────────────────────────────
  let alertsDispatchedCount = 0;

  if (hasAnyFreshMatches && targetProfiles.length > 0) {
    // Fetch all user settings & portfolios in bulk for target users
    const userIds = targetProfiles.map((p: any) => p.id);
    const [settingsRes, portfolioRes] = await Promise.all([
      serviceClient.from("user_settings").select("user_id, app_state").in("user_id", userIds),
      serviceClient.from("positions").select("user_id, symbol").eq("status", "open").in("user_id", userIds),
    ]);

    const settingsMap = new Map((settingsRes.data || []).map((s: any) => [s.user_id, s.app_state?.scanner_alerts]));
    const portfolioMap = new Map<string, Set<string>>();
    for (const item of portfolioRes.data || []) {
      if (!portfolioMap.has(item.user_id)) portfolioMap.set(item.user_id, new Set());
      portfolioMap.get(item.user_id)?.add(String(item.symbol).toUpperCase());
    }

    // Dispatch loop
    for (const user of targetProfiles) {
      const rawPrefs: any = settingsMap.get(user.id) || {};
      const prefs: ScannerPreferences = {
        volume_surge: rawPrefs.volume_surge ?? true,
        breakout: rawPrefs.breakout ?? true,
        rsi_oversold: rawPrefs.rsi_oversold ?? true,
        portfolio_watchlist: rawPrefs.portfolio_watchlist ?? true,
        disclosures: rawPrefs.disclosures ?? true,
      };

      const userPortfolio = portfolioMap.get(user.id) || new Set<string>();

      // Filter matches per user preference
      const userVolume = prefs.volume_surge ? freshVolume : [];
      const userBreakout = prefs.breakout ? freshBreakout : [];
      const userOversold = prefs.rsi_oversold ? freshOversold : [];
      const userDisclosures = prefs.disclosures ? freshDisclosures : [];

      // Check watchlist matches
      const portfolioHits: string[] = [];
      if (prefs.portfolio_watchlist && userPortfolio.size > 0) {
        for (const v of userVolume) {
          if (userPortfolio.has(v.symbol)) portfolioHits.push(`• السهم <b>${v.symbol}</b> في محفظتك رصد سيولة غير طبيعية (${v.r_vol}x)`);
        }
        for (const b of userBreakout) {
          if (userPortfolio.has(b.symbol)) portfolioHits.push(`• السهم <b>${b.symbol}</b> في محفظتك يسجل اختراق فني (+${b.change_pct}%)`);
        }
        for (const o of userOversold) {
          if (userPortfolio.has(o.symbol)) portfolioHits.push(`• السهم <b>${o.symbol}</b> في محفظتك يرتد من تشبع بيعي (RSI=${o.rsi_14})`);
        }
      }

      const totalUserHits = userVolume.length + userBreakout.length + userOversold.length + userDisclosures.length;
      if (totalUserHits === 0) continue;

      // Construct Telegram Neobrutalist Arabic Message
      const lines: string[] = [
        `⚡ <b>[EGX BOTS] رادار الإسكانر الفوري — جلسة البورصة</b>`,
        `───────────────`,
      ];

      if (userVolume.length > 0) {
        lines.push(`🔥 <b>رادار السيولة غير الطبيعية (Volume Surge):</b>`);
        for (const v of userVolume) {
          lines.push(`• <b>${v.symbol}</b>: ${v.close.toFixed(2)} ج.م (<b>${v.change_pct >= 0 ? "+" : ""}${v.change_pct}%</b>) | سيولة <b>${v.r_vol}x</b> ضعف المعتاد 📊`);
        }
        lines.push(``);
      }

      if (userBreakout.length > 0) {
        lines.push(`🚀 <b>رادار الاختراقات الفنية (Breakout):</b>`);
        for (const b of userBreakout) {
          lines.push(`• <b>${b.symbol}</b>: ${b.close.toFixed(2)} ج.م (<b>+${b.change_pct}%</b>) | اختراق قمة 20 جلسة 🎯`);
        }
        lines.push(``);
      }

      if (userOversold.length > 0) {
        lines.push(`💎 <b>ارتداد من تشبع بيعي (RSI Bounce):</b>`);
        for (const o of userOversold) {
          lines.push(`• <b>${o.symbol}</b>: ${o.close.toFixed(2)} ج.م (<b>+${o.change_pct}%</b>) | مؤشر RSI: <b>${o.rsi_14}</b> 📈`);
        }
        lines.push(``);
      }

      if (portfolioHits.length > 0) {
        lines.push(`💼 <b>تنبيه خاص لأسهم محفظتك:</b>`);
        lines.push(...portfolioHits);
        lines.push(``);
      }

      if (userDisclosures.length > 0) {
        lines.push(`📢 <b>إفصاحات وأخبار رسمية حديثة:</b>`);
        for (const d of userDisclosures) {
          lines.push(`• ${d.title}`);
        }
        lines.push(``);
      }

      lines.push(`───────────────`);
      lines.push(`⏱️ التوقيت: <b>${cairoTime.timeStr} بتوقيت القاهرة</b>`);
      lines.push(`🔗 تفاصيل الشارت والمؤشرات: <a href="https://egxbots.com">EGX BOTS</a>`);

      const text = lines.join("\n");
      const sent = await sendTelegramAlert(user.telegram_chat_id, text);
      if (sent) alertsDispatchedCount++;
    }

    // Register newly sent keys into sentToday
    for (const v of freshVolume) sentKeysSet.add(`${v.symbol}:volume_surge`);
    for (const b of freshBreakout) sentKeysSet.add(`${b.symbol}:breakout`);
    for (const o of freshOversold) sentKeysSet.add(`${o.symbol}:rsi_oversold`);
    for (const d of freshDisclosures) sentKeysSet.add(`disclosure:${d.id}`);
  }

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
  };

  const updatedConfig: AdminScannerConfig = {
    ...config,
    last_scan: newScanResult,
    sent_today: {
      date: cairoTime.dateStr,
      sent_keys: Array.from(sentKeysSet).slice(-200),
    },
    history: [historyEntry, ...(config.history || [])].slice(0, 30),
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
