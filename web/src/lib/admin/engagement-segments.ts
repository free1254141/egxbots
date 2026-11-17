import { isExcludedAdminUser } from "@/lib/admin/admin-exclusions";

export const PRO_MONTHLY_CHAT_LIMIT = 350;

export interface EngagementUserInput {
  id: string;
  email?: string | null;
  display_name?: string | null;
}

export interface ChatbotLimitRow {
  user_id?: string | null;
  date?: string | null;
  chat_count?: number | null;
}

export interface ChatMessageMetaRow {
  user_id?: string | null;
  created_at?: string | null;
}

export interface ActivityEventRow {
  user_id?: string | null;
  event_name?: string | null;
  path?: string | null;
}

export interface SubscriptionStatusRow {
  user_id?: string | null;
  plan_id?: string | null;
  status?: string | null;
  current_period_end?: string | null;
}

export interface ChatterLeaderRow {
  user_id: string;
  email: string;
  display_name: string | null;
  month: string;
  month_chats: number;
  all_time_chats: number;
  is_active_paid: boolean;
  is_paid_ever: boolean;
  pct_of_350: number;
}

export interface PeakMonthBucket {
  id: "zero" | "1_10" | "11_50" | "51_150" | "151_349" | "350_plus";
  label_ar: string;
  label_en: string;
  count: number;
  pct: number;
}

export interface UsersEngagementSummary {
  generated_at: string;
  total_users: number;
  subscribers: {
    active_paid_count: number;
    active_paid_pct: number;
    paid_ever_count: number;
    paid_ever_pct: number;
    active_trial_count: number;
    active_trial_pct: number;
  };
  interests: {
    chat_messaged_count: number;
    chat_messaged_pct: number;
    chat_interested_count: number;
    chat_interested_pct: number;
    recs_interested_count: number;
    recs_interested_pct: number;
    recs_web_scanner_count: number;
    recs_web_scanner_pct: number;
    recs_bot_or_vip_count: number;
    recs_bot_or_vip_pct: number;
  };
  overlap: {
    both_count: number;
    both_pct: number;
    chat_only_count: number;
    chat_only_pct: number;
    recs_only_count: number;
    recs_only_pct: number;
    neither_count: number;
    neither_pct: number;
  };
  paid_breakdown: {
    active_paid_chat_count: number;
    active_paid_chat_pct: number;
    active_paid_recs_count: number;
    active_paid_recs_pct: number;
    active_paid_both_count: number;
    paid_ever_chat_count: number;
    paid_ever_chat_pct: number;
    paid_ever_recs_count: number;
    paid_ever_recs_pct: number;
  };
  chat_limit_350: {
    monthly_limit: number;
    hit_350_months_count: number;
    users_ever_hit_350_count: number;
    approached_150_users_count: number;
    approached_50_users_count: number;
    max_month_chats_ever: number;
    max_month_messages_ever: number;
    max_month_leader: {
      user_id: string;
      email: string;
      display_name: string | null;
      month: string;
      chats: number;
    } | null;
    peak_buckets: PeakMonthBucket[];
    top_monthly_chatters: ChatterLeaderRow[];
    top_all_time_chatters: ChatterLeaderRow[];
  };
}

function pct(count: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((count / total) * 1000) / 10;
}

const CAIRO_MONTH_FMT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Africa/Cairo",
  year: "numeric",
  month: "2-digit",
});

function toCairoMonth(dateInput?: string | null): string | null {
  if (!dateInput) return null;
  const raw = String(dateInput).trim();
  if (/^\d{4}-\d{2}/.test(raw) && raw.length === 10) {
    return raw.slice(0, 7);
  }
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed)) {
    return /^\d{4}-\d{2}/.test(raw) ? raw.slice(0, 7) : null;
  }
  return CAIRO_MONTH_FMT.format(new Date(parsed)).slice(0, 7);
}

function cleanPath(path?: string | null): string {
  return String(path || "").split("?")[0].trim().toLowerCase();
}

export function summarizeUsersEngagement(params: {
  now?: Date;
  users: EngagementUserInput[];
  excludeUserIds?: Set<string>;
  chatbotLimits: ChatbotLimitRow[];
  chatMessages: ChatMessageMetaRow[];
  chatLogUserIds?: string[];
  scheduledAutomationUserIds?: string[];
  activityEvents: ActivityEventRow[];
  botSubscriptionUserIds?: string[];
  proTelegramInviteUserIds?: string[];
  scannerPositionUserIds?: string[];
  subscriptions: SubscriptionStatusRow[];
  paidEverUserIds?: string[];
}): UsersEngagementSummary {
  const now = params.now ?? new Date();
  const nowMs = now.getTime();

  const validUsersById = new Map<string, { id: string; email: string; display_name: string | null }>();
  for (const u of params.users || []) {
    const uid = String(u.id || "").trim();
    if (!uid) continue;
    const email = String(u.email || "").trim().toLowerCase();
    if (isExcludedAdminUser(uid, email, params.excludeUserIds)) continue;
    validUsersById.set(uid, {
      id: uid,
      email: email || uid,
      display_name: u.display_name ? String(u.display_name).trim() : null,
    });
  }

  const chatMessaged = new Set<string>();
  const chatInterested = new Set<string>();
  const recsWebScanner = new Set<string>();
  const recsBotOrVip = new Set<string>();
  const recsInterested = new Set<string>();
  const activePaid = new Set<string>();
  const activeTrial = new Set<string>();
  const paidEver = new Set<string>();

  const monthlyLimitByKey = new Map<string, { user_id: string; month: string; chats: number }>();
  const allTimeLimitByUser = new Map<string, number>();

  for (const row of params.chatbotLimits || []) {
    const uid = String(row.user_id || "").trim();
    if (!validUsersById.has(uid)) continue;
    const count = Number(row.chat_count || 0);
    if (count > 0) {
      chatMessaged.add(uid);
      chatInterested.add(uid);
    }
    const ym = toCairoMonth(row.date);
    if (!ym || count <= 0) continue;
    allTimeLimitByUser.set(uid, (allTimeLimitByUser.get(uid) || 0) + count);
    const key = `${uid}|${ym}`;
    const prev = monthlyLimitByKey.get(key);
    if (prev) {
      prev.chats += count;
    } else {
      monthlyLimitByKey.set(key, { user_id: uid, month: ym, chats: count });
    }
  }

  const msgMonthByKey = new Map<string, number>();
  for (const msg of params.chatMessages || []) {
    const uid = String(msg.user_id || "").trim();
    if (!validUsersById.has(uid)) continue;
    chatMessaged.add(uid);
    chatInterested.add(uid);
    const ym = toCairoMonth(msg.created_at);
    if (ym) {
      const k = `${uid}|${ym}`;
      msgMonthByKey.set(k, (msgMonthByKey.get(k) || 0) + 1);
    }
  }

  for (const rawId of params.chatLogUserIds || []) {
    const uid = String(rawId || "").trim();
    if (validUsersById.has(uid)) {
      chatMessaged.add(uid);
      chatInterested.add(uid);
    }
  }

  for (const rawId of params.scheduledAutomationUserIds || []) {
    const uid = String(rawId || "").trim();
    if (validUsersById.has(uid)) {
      chatInterested.add(uid);
    }
  }

  for (const ev of params.activityEvents || []) {
    const uid = String(ev.user_id || "").trim();
    if (!validUsersById.has(uid)) continue;
    const p = cleanPath(ev.path);
    const name = String(ev.event_name || "").trim().toLowerCase();
    if (p.startsWith("/chat") || name === "trial_first_message") {
      chatInterested.add(uid);
    }
    if (p.startsWith("/scanner") || name === "feature_use") {
      recsWebScanner.add(uid);
      recsInterested.add(uid);
    }
  }

  for (const rawId of params.botSubscriptionUserIds || []) {
    const uid = String(rawId || "").trim();
    if (validUsersById.has(uid)) {
      recsBotOrVip.add(uid);
      recsInterested.add(uid);
    }
  }

  for (const rawId of params.proTelegramInviteUserIds || []) {
    const uid = String(rawId || "").trim();
    if (validUsersById.has(uid)) {
      recsBotOrVip.add(uid);
      recsInterested.add(uid);
    }
  }

  for (const rawId of params.scannerPositionUserIds || []) {
    const uid = String(rawId || "").trim();
    if (validUsersById.has(uid)) {
      recsInterested.add(uid);
    }
  }

  for (const sub of params.subscriptions || []) {
    const uid = String(sub.user_id || "").trim();
    if (!validUsersById.has(uid)) continue;
    const status = String(sub.status || "").trim().toLowerCase();
    const planId = String(sub.plan_id || "").trim().toLowerCase();
    const isLifetime = planId === "lifetime" || planId === "pro_lifetime";
    const endMs = sub.current_period_end ? Date.parse(sub.current_period_end) : Number.NaN;
    const notExpired = isLifetime || !Number.isFinite(endMs) || endMs > nowMs;
    if (status === "active" && notExpired && planId !== "free") {
      activePaid.add(uid);
      paidEver.add(uid);
    } else if (status === "trialing" && notExpired) {
      activeTrial.add(uid);
    }
  }

  for (const rawId of params.paidEverUserIds || []) {
    const uid = String(rawId || "").trim();
    if (validUsersById.has(uid)) {
      paidEver.add(uid);
    }
  }

  // Overlap and subscriber intersection counts
  let bothCount = 0;
  let chatOnlyCount = 0;
  let recsOnlyCount = 0;
  let neitherCount = 0;
  let activePaidChatCount = 0;
  let activePaidRecsCount = 0;
  let activePaidBothCount = 0;
  let paidEverChatCount = 0;
  let paidEverRecsCount = 0;

  for (const uid of validUsersById.keys()) {
    const hasChat = chatInterested.has(uid);
    const hasRecs = recsInterested.has(uid);
    if (hasChat && hasRecs) bothCount += 1;
    else if (hasChat) chatOnlyCount += 1;
    else if (hasRecs) recsOnlyCount += 1;
    else neitherCount += 1;

    if (activePaid.has(uid)) {
      if (hasChat) activePaidChatCount += 1;
      if (hasRecs) activePaidRecsCount += 1;
      if (hasChat && hasRecs) activePaidBothCount += 1;
    }
    if (paidEver.has(uid)) {
      if (hasChat) paidEverChatCount += 1;
      if (hasRecs) paidEverRecsCount += 1;
    }
  }

  // Monthly 350 quota evaluation
  let hit350MonthsCount = 0;
  const usersHit350 = new Set<string>();
  const peakMonthByUser = new Map<string, { month: string; chats: number }>();

  const monthlyEntries = Array.from(monthlyLimitByKey.values()).sort((a, b) => {
    if (b.chats !== a.chats) return b.chats - a.chats;
    return b.month.localeCompare(a.month);
  });

  for (const entry of monthlyEntries) {
    if (entry.chats >= PRO_MONTHLY_CHAT_LIMIT) {
      hit350MonthsCount += 1;
      usersHit350.add(entry.user_id);
    }
    const curPeak = peakMonthByUser.get(entry.user_id);
    if (!curPeak || entry.chats > curPeak.chats) {
      peakMonthByUser.set(entry.user_id, { month: entry.month, chats: entry.chats });
    }
  }

  let maxMonthMessagesEver = 0;
  for (const cnt of msgMonthByKey.values()) {
    if (cnt > maxMonthMessagesEver) maxMonthMessagesEver = cnt;
  }

  let approached150Count = 0;
  let approached50Count = 0;
  let bucket0 = 0;
  let bucket1_10 = 0;
  let bucket11_50 = 0;
  let bucket51_150 = 0;
  let bucket151_349 = 0;
  let bucket350Plus = 0;

  for (const uid of validUsersById.keys()) {
    const peak = peakMonthByUser.get(uid)?.chats || 0;
    if (peak >= 150) approached150Count += 1;
    if (peak >= 50) approached50Count += 1;
    if (peak === 0) bucket0 += 1;
    else if (peak <= 10) bucket1_10 += 1;
    else if (peak <= 50) bucket11_50 += 1;
    else if (peak <= 150) bucket51_150 += 1;
    else if (peak < PRO_MONTHLY_CHAT_LIMIT) bucket151_349 += 1;
    else bucket350Plus += 1;
  }

  const totalUsers = validUsersById.size;
  const peakBuckets: PeakMonthBucket[] = [
    { id: "zero", label_ar: "0 رسالة", label_en: "0 chats", count: bucket0, pct: pct(bucket0, totalUsers) },
    { id: "1_10", label_ar: "1 – 10 رسائل", label_en: "1–10 chats", count: bucket1_10, pct: pct(bucket1_10, totalUsers) },
    { id: "11_50", label_ar: "11 – 50 رسالة", label_en: "11–50 chats", count: bucket11_50, pct: pct(bucket11_50, totalUsers) },
    { id: "51_150", label_ar: "51 – 150 رسالة", label_en: "51–150 chats", count: bucket51_150, pct: pct(bucket51_150, totalUsers) },
    { id: "151_349", label_ar: "151 – 349 رسالة", label_en: "151–349 chats", count: bucket151_349, pct: pct(bucket151_349, totalUsers) },
    { id: "350_plus", label_ar: "وصل 350+ (الحد الأقصى)", label_en: "350+ (Hit Cap)", count: bucket350Plus, pct: pct(bucket350Plus, totalUsers) },
  ];

  const topMonthlyChatters: ChatterLeaderRow[] = monthlyEntries.slice(0, 15).map((entry) => {
    const info = validUsersById.get(entry.user_id)!;
    return {
      user_id: entry.user_id,
      email: info.email,
      display_name: info.display_name,
      month: entry.month,
      month_chats: entry.chats,
      all_time_chats: allTimeLimitByUser.get(entry.user_id) || entry.chats,
      is_active_paid: activePaid.has(entry.user_id),
      is_paid_ever: paidEver.has(entry.user_id),
      pct_of_350: Math.round((entry.chats / PRO_MONTHLY_CHAT_LIMIT) * 1000) / 10,
    };
  });

  const topAllTimeChatters: ChatterLeaderRow[] = Array.from(allTimeLimitByUser.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([uid, total]) => {
      const info = validUsersById.get(uid)!;
      const peak = peakMonthByUser.get(uid);
      return {
        user_id: uid,
        email: info.email,
        display_name: info.display_name,
        month: peak?.month || "—",
        month_chats: peak?.chats || 0,
        all_time_chats: total,
        is_active_paid: activePaid.has(uid),
        is_paid_ever: paidEver.has(uid),
        pct_of_350: Math.round(((peak?.chats || 0) / PRO_MONTHLY_CHAT_LIMIT) * 1000) / 10,
      };
    });

  const topMonthly = topMonthlyChatters[0] || null;
  const activePaidCount = activePaid.size;
  const paidEverCount = paidEver.size;
  const activeTrialCount = activeTrial.size;

  return {
    generated_at: now.toISOString(),
    total_users: totalUsers,
    subscribers: {
      active_paid_count: activePaidCount,
      active_paid_pct: pct(activePaidCount, totalUsers),
      paid_ever_count: paidEverCount,
      paid_ever_pct: pct(paidEverCount, totalUsers),
      active_trial_count: activeTrialCount,
      active_trial_pct: pct(activeTrialCount, totalUsers),
    },
    interests: {
      chat_messaged_count: chatMessaged.size,
      chat_messaged_pct: pct(chatMessaged.size, totalUsers),
      chat_interested_count: chatInterested.size,
      chat_interested_pct: pct(chatInterested.size, totalUsers),
      recs_interested_count: recsInterested.size,
      recs_interested_pct: pct(recsInterested.size, totalUsers),
      recs_web_scanner_count: recsWebScanner.size,
      recs_web_scanner_pct: pct(recsWebScanner.size, totalUsers),
      recs_bot_or_vip_count: recsBotOrVip.size,
      recs_bot_or_vip_pct: pct(recsBotOrVip.size, totalUsers),
    },
    overlap: {
      both_count: bothCount,
      both_pct: pct(bothCount, totalUsers),
      chat_only_count: chatOnlyCount,
      chat_only_pct: pct(chatOnlyCount, totalUsers),
      recs_only_count: recsOnlyCount,
      recs_only_pct: pct(recsOnlyCount, totalUsers),
      neither_count: neitherCount,
      neither_pct: pct(neitherCount, totalUsers),
    },
    paid_breakdown: {
      active_paid_chat_count: activePaidChatCount,
      active_paid_chat_pct: pct(activePaidChatCount, activePaidCount),
      active_paid_recs_count: activePaidRecsCount,
      active_paid_recs_pct: pct(activePaidRecsCount, activePaidCount),
      active_paid_both_count: activePaidBothCount,
      paid_ever_chat_count: paidEverChatCount,
      paid_ever_chat_pct: pct(paidEverChatCount, paidEverCount),
      paid_ever_recs_count: paidEverRecsCount,
      paid_ever_recs_pct: pct(paidEverRecsCount, paidEverCount),
    },
    chat_limit_350: {
      monthly_limit: PRO_MONTHLY_CHAT_LIMIT,
      hit_350_months_count: hit350MonthsCount,
      users_ever_hit_350_count: usersHit350.size,
      approached_150_users_count: approached150Count,
      approached_50_users_count: approached50Count,
      max_month_chats_ever: topMonthly?.month_chats || 0,
      max_month_messages_ever: maxMonthMessagesEver,
      max_month_leader: topMonthly
        ? {
            user_id: topMonthly.user_id,
            email: topMonthly.email,
            display_name: topMonthly.display_name,
            month: topMonthly.month,
            chats: topMonthly.month_chats,
          }
        : null,
      peak_buckets: peakBuckets,
      top_monthly_chatters: topMonthlyChatters,
      top_all_time_chatters: topAllTimeChatters,
    },
  };
}
