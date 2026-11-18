import { createClient, type User } from "@supabase/supabase-js";
import type { NextRequest } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { isAllowedAdminEmail } from "@/lib/admin-auth-client";

export const B2B_TRIAL_DAILY_LIMIT = 30;
export const B2B_TRIAL_DURATION_DAYS = 3;
export const B2B_VALID_TIERS = ["b2b_starter", "b2b_pro", "b2b_enterprise"] as const;
export type B2BTier = (typeof B2B_VALID_TIERS)[number];

/** Create a server-side Supabase service_role client for privileged B2B operations. */
export function getB2BServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !serviceKey) {
    throw new Error("Missing Supabase service role configuration");
  }
  return createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
}

/** Resolve verified Supabase user from cookies or Authorization header. */
export async function getVerifiedB2BUser(req: NextRequest): Promise<User | null> {
  const supabase = await createSupabaseServerClient(req);
  const { data, error } = await supabase.auth.getUser();
  if (error || !data?.user) return null;
  return data.user;
}

export function normalizeB2BTier(tier: unknown, fallback: B2BTier = "b2b_pro"): B2BTier {
  const s = String(tier || fallback).trim().toLowerCase();
  return (B2B_VALID_TIERS as readonly string[]).includes(s) ? (s as B2BTier) : fallback;
}

/** Shared helper for starting a 3-day B2B free trial with 1-per-user enforcement and safe 30/day cap. */
export async function createB2BTrialForUser(user: User, requestedTier?: unknown) {
  const isAdmin = isAllowedAdminEmail(user.email);
  const tier = normalizeB2BTier(requestedTier, "b2b_pro");
  const adminDb = getB2BServiceClient();

  const botUsername = (process.env.TELEGRAM_BOT_USERNAME || "egxbots_bot").replace(/^@/, "");

  if (!isAdmin) {
    const { data: existingTrials, error: checkErr } = await adminDb
      .from("b2b_group_licenses")
      .select("*")
      .eq("owner_user_id", user.id)
      .ilike("order_id", "B2B-TRIAL-%")
      .order("created_at", { ascending: false })
      .limit(1);

    if (checkErr) {
      return { ok: false as const, status: 500, error: checkErr.message };
    }

    if (existingTrials && existingTrials.length > 0) {
      const existing = existingTrials[0];
      // If the user created the trial but hasn't linked their Telegram group yet,
      // refresh the 3-day window and return the activation modal data so they can link seamlessly!
      if (!existing.telegram_chat_id) {
        const refreshedExpiry = new Date(Date.now() + B2B_TRIAL_DURATION_DAYS * 24 * 60 * 60 * 1000).toISOString();
        const { data: updated } = await adminDb
          .from("b2b_group_licenses")
          .update({ status: "active", expires_at: refreshedExpiry, updated_at: new Date().toISOString() })
          .eq("id", existing.id)
          .select()
          .single();
        const activeLic = updated || existing;
        const code = String(activeLic.id).slice(0, 8);
        const url = `https://t.me/${botUsername}?startgroup=activate_${code}&admin=delete_messages+pin_messages`;
        return {
          ok: true as const,
          status: 200,
          license: activeLic,
          activation_code: code,
          connect_url: url,
          message: "رخصتك التجريبية جاهزة! اضغط زر الربط لاختيار مجموعتك على تليجرام وتفعيل البوت فوراً.",
        };
      }

      return {
        ok: false as const,
        status: 400,
        error: "trial_already_claimed",
        already_used: true,
        message:
          "لقد استنفدت بالفعل فترة التجربة المجانية (3 أيام) المخصصة لحسابك. يمكنك الاشتراك المباشر لترخيص البوت في مجموعتك.",
      };
    }
  }

  const randomSuffix = Math.random().toString(36).substring(2, 8).toUpperCase();
  const orderId = `B2B-TRIAL-${randomSuffix}`;
  const startsAt = new Date().toISOString();
  const expiresAt = new Date(Date.now() + B2B_TRIAL_DURATION_DAYS * 24 * 60 * 60 * 1000).toISOString();

  const { data: newLicense, error: insertErr } = await adminDb
    .from("b2b_group_licenses")
    .insert({
      owner_user_id: user.id,
      order_id: orderId,
      tier,
      daily_limit: B2B_TRIAL_DAILY_LIMIT,
      daily_used: 0,
      custom_signature: "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS",
      allow_recommendations: false,
      status: "active",
      starts_at: startsAt,
      expires_at: expiresAt,
      group_title: "مجموعة تجريبية (قيد التفعيل بـ تليجرام)",
    })
    .select()
    .single();

  if (insertErr || !newLicense) {
    return {
      ok: false as const,
      status: 500,
      error: insertErr?.message || "Failed to create trial license",
    };
  }

  const activationCode = String(newLicense.id).slice(0, 8);
  const connectUrl = `https://t.me/${botUsername}?startgroup=activate_${activationCode}&admin=delete_messages+pin_messages`;

  return {
    ok: true as const,
    status: 200,
    license: newLicense,
    activation_code: activationCode,
    connect_url: connectUrl,
    message: "تم تفعيل رخصتك التجريبية (3 أيام) بنجاح!",
  };
}
