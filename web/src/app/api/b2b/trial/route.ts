import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { isAllowedAdminEmail } from "@/lib/admin-auth-client";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient(req);
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const isAdmin = isAllowedAdminEmail(session.user.email);
    const body = await req.json().catch(() => ({}));
    const requestedTier = String(body.tier || "b2b_pro");
    const validTiers = ["b2b_starter", "b2b_pro", "b2b_enterprise"];
    const tier = validTiers.includes(requestedTier) ? requestedTier : "b2b_pro";

    // Enforce 1 trial per user (unless admin)
    if (!isAdmin) {
      const { data: existingTrials, error: checkErr } = await supabase
        .from("b2b_group_licenses")
        .select("id, order_id, created_at")
        .eq("owner_user_id", session.user.id)
        .ilike("order_id", "B2B-TRIAL-%")
        .limit(1);

      if (checkErr) {
        return NextResponse.json({ ok: false, error: checkErr.message }, { status: 500 });
      }

      if (existingTrials && existingTrials.length > 0) {
        return NextResponse.json(
          {
            ok: false,
            error: "trial_already_claimed",
            message:
              "لقد استنفدت بالفعل فترة التجربة المجانية (3 أيام) المخصصة لحسابك. يمكنك الاشتراك المباشر لترخيص البوت في مجموعتك.",
          },
          { status: 400 }
        );
      }
    }

    const dailyLimitMap: Record<string, number> = {
      b2b_starter: 50,
      b2b_pro: 120,
      b2b_enterprise: 250,
    };
    const dailyLimit = dailyLimitMap[tier] || 120;

    const randomSuffix = Math.random().toString(36).substring(2, 8).toUpperCase();
    const orderId = `B2B-TRIAL-${randomSuffix}`;
    const startsAt = new Date().toISOString();
    const expiresAt = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(); // 3 days free trial

    const { data: newLicense, error: insertErr } = await supabase
      .from("b2b_group_licenses")
      .insert({
        owner_user_id: session.user.id,
        order_id: orderId,
        tier,
        daily_limit: dailyLimit,
        daily_used: 0,
        custom_signature: "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS",
        status: "active",
        starts_at: startsAt,
        expires_at: expiresAt,
        group_title: "مجموعة تجريبية (قيد التفعيل بـ تليجرام)",
      })
      .select()
      .single();

    if (insertErr || !newLicense) {
      return NextResponse.json(
        { ok: false, error: insertErr?.message || "Failed to create trial license" },
        { status: 500 }
      );
    }

    const activationCode = String(newLicense.id).slice(0, 8);
    const botUsername = process.env.TELEGRAM_BOT_USERNAME || "egxbots_bot";
    const cleanBot = botUsername.replace(/^@/, "");
    const connectUrl = `https://t.me/${cleanBot}?startgroup=activate_${activationCode}`;

    return NextResponse.json({
      ok: true,
      license: newLicense,
      activation_code: activationCode,
      connect_url: connectUrl,
      message: "تم تفعيل رخصتك التجريبية (3 أيام) بنجاح!",
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}
