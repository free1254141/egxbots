export const SAUDI_VIP_TELEGRAM_WEB_URL = "https://web.telegram.org/a/#-1004397045436";

export async function createSaudiProTelegramInvite(userId: string, expiresAt: string): Promise<string> {
  const token = process.env.SUPPORT_BOT_TOKEN?.trim();
  const chatId = process.env.SAUDI_TELEGRAM_PRO_CHAT_ID?.trim() || "-1004397045436";
  if (!token || !chatId) return SAUDI_VIP_TELEGRAM_WEB_URL;

  const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
  const now = Date.now();
  const rawExpireMs = new Date(expiresAt).getTime();
  const maxExpireMs = now + 365 * 86_400_000;

  const payload: Record<string, unknown> = {
    chat_id: chatId,
    name: `Saudi Pro ${userId.slice(0, 8)}`,
    member_limit: 1,
  };

  if (Number.isFinite(rawExpireMs) && rawExpireMs > now && rawExpireMs <= maxExpireMs) {
    payload.expire_date = Math.floor(rawExpireMs / 1000);
  }

  const body = JSON.stringify(payload);

  for (const base of [relayUrl, "https://api.telegram.org"]) {
    try {
      const response = await fetch(`${base}/bot${token}/createChatInviteLink`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.ok && data.result?.invite_link) {
        return String(data.result.invite_link);
      }
      if (base === relayUrl) continue;
    } catch {
      if (base === relayUrl) continue;
    }
  }
  return SAUDI_VIP_TELEGRAM_WEB_URL;
}

export async function createProTelegramInvite(userId: string, expiresAt: string): Promise<string> {
  const token = process.env.SUPPORT_BOT_TOKEN?.trim();
  const chatId = process.env.TELEGRAM_PRO_CHAT_ID?.trim();
  if (!token || !chatId) return "";

  const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
  const now = Date.now();
  const rawExpireMs = new Date(expiresAt).getTime();
  const maxExpireMs = now + 365 * 86_400_000;

  const payload: Record<string, unknown> = {
    chat_id: chatId,
    name: `Pro ${userId.slice(0, 8)}`,
    member_limit: 1,
  };

  // Only pass expire_date if it is within Telegram's allowed window (up to 365 days).
  // If subscription is longer (e.g. lifetime or >1 year), omit expire_date for a permanent single-use link.
  if (Number.isFinite(rawExpireMs) && rawExpireMs > now && rawExpireMs <= maxExpireMs) {
    payload.expire_date = Math.floor(rawExpireMs / 1000);
  }

  const body = JSON.stringify(payload);

  for (const base of [relayUrl, "https://api.telegram.org"]) {
    try {
      const response = await fetch(`${base}/bot${token}/createChatInviteLink`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload?.ok) {
        return String(payload.result?.invite_link || "");
      }
      if (base === relayUrl) continue;
    } catch {
      if (base === relayUrl) continue;
    }
  }
  return "";
}

type RevokeProTelegramAccessInput = {
  inviteLink?: string | null;
  telegramUserId?: string | number | null;
};

/** Revoke a user-scoped invite and remove its joined member, when known. */
export async function revokeProTelegramAccess({ inviteLink, telegramUserId }: RevokeProTelegramAccessInput): Promise<{ inviteRevoked: boolean; memberRemoved: boolean }> {
  const token = process.env.SUPPORT_BOT_TOKEN?.trim();
  const chatId = process.env.TELEGRAM_PRO_CHAT_ID?.trim();
  if (!token || !chatId) return { inviteRevoked: false, memberRemoved: false };

  const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
  const call = async (method: string, payload: Record<string, unknown>) => {
    for (const base of [relayUrl, "https://api.telegram.org"]) {
      try {
        const response = await fetch(`${base}/bot${token}/${method}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          cache: "no-store",
          signal: AbortSignal.timeout(10_000),
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data?.ok) return true;
      } catch {
        // Try Telegram's official endpoint after an unavailable relay.
      }
    }
    return false;
  };

  const inviteRevoked = inviteLink?.trim()
    ? await call("revokeChatInviteLink", { chat_id: chatId, invite_link: inviteLink.trim() })
    : false;
  const rawUserId = String(telegramUserId ?? "").trim();
  if (!/^-?\d+$/.test(rawUserId)) return { inviteRevoked, memberRemoved: false };

  const until = Math.floor(Date.now() / 1000) + 60;
  const banned = await call("banChatMember", { chat_id: chatId, user_id: Number(rawUserId), until_date: until });
  const unbanned = banned && await call("unbanChatMember", { chat_id: chatId, user_id: Number(rawUserId), only_if_banned: true });
  return { inviteRevoked, memberRemoved: Boolean(unbanned) };
}

export type SendProWelcomeDirectMessageInput = {
  chatId: string | number;
  inviteLink?: string;
  planTitle?: string;
  displayName?: string;
};

/**
 * Dispatch an instant celebratory welcome message with the personal VIP invite link
 * directly to the user's active Telegram bot chat.
 */
export async function sendProWelcomeDirectMessage({
  chatId,
  inviteLink,
  planTitle = "تجربة Pro المجانية (3 أيام)",
  displayName,
}: SendProWelcomeDirectMessageInput): Promise<boolean> {
  const token = (
    process.env.ARTORO_AI_BOT ||
    process.env.TELEGRAM_BOT_TOKEN ||
    process.env.SUPPORT_BOT_TOKEN
  )?.trim();
  if (!token || !chatId) return false;

  const relayUrl = (process.env.TELEGRAM_RELAY_URL || "https://api.telegram.org").replace(/\/$/, "");
  const name = displayName?.trim() || "عزيزنا المستثمر";

  let msg = `🎉 <b>أهلاً وسهلاً بك يا ${name}!</b>\n\n`;
  msg += `✅ <b>تم تفعيل ${planTitle} بنجاح!</b> 🚀\n\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━\n`;
  if (inviteLink) {
    msg += `💎 <b>رابط انضمامك الخاص لقناة التوصيات VIP:</b>\n`;
    msg += `${inviteLink}\n`;
    msg += `<i>(هذا الرابط شخصي وخاص بحسابك وصالح طوال فترة اشتراكك)</i>\n\n`;
  }
  msg += `📊 <b>المزايا المتاحة لك الآن:</b>\n`;
  msg += `• إشارات دخول وتنبيهات الأهداف ووقف الخسارة لحظياً على قناة VIP\n`;
  msg += `• وصول كامل لكافة تقارير البورصة المصرية ومساعد الذكاء الاصطناعي\n`;
  msg += `• استشارات وتحليلات ذكية لأي سهم تريده عبر هذا الشات\n\n`;
  msg += `━━━━━━━━━━━━━━━━━━━━\n`;
  msg += `💡 <b>كيف تبدأ؟</b>\n`;
  if (inviteLink) {
    msg += `1. اضغط زر <b>الانضمام لقناة VIP</b> أدناه لمتابعة الصفقات أولاً بأول.\n`;
    msg += `2. اسألني هنا عن أي سهم في البورصة المصرية (مثلاً اكتب رمز السهم مثل <code>COMI</code> أو <code>TMGH</code>).\n\n`;
  } else {
    msg += `1. اسألني هنا عن أي سهم في البورصة المصرية (مثلاً اكتب رمز السهم مثل <code>COMI</code> أو <code>TMGH</code>).\n\n`;
  }
  msg += `نتمنى لك تداولات موفقة ومربحة دائماً! 📈`;

  const buttons: Array<Array<{ text: string; url: string }>> = [];
  if (inviteLink) {
    buttons.push([{ text: "💎 الانضمام لقناة VIP", url: inviteLink }]);
  }
  buttons.push([{ text: "🌐 فتح موقع المنصة والتقارير", url: "https://egxbots.com/reports" }]);

  const payload = {
    chat_id: chatId,
    text: msg,
    parse_mode: "HTML",
    reply_markup: { inline_keyboard: buttons },
  };

  for (const base of [relayUrl, "https://api.telegram.org"]) {
    try {
      const response = await fetch(`${base}/bot${token}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.ok) return true;
      if (base === relayUrl) continue;
    } catch {
      if (base === relayUrl) continue;
    }
  }
  return false;
}
