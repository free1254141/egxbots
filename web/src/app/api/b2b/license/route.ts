import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { isAllowedAdminEmail } from "@/lib/admin-auth-client";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient(req);
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const isAdmin = isAllowedAdminEmail(session.user.email);
    const url = new URL(req.url);
    const requestedLicenseId = url.searchParams.get("license_id");

    // 1. Fetch licenses owned by this user
    let query = supabase
      .from("b2b_group_licenses")
      .select("id, tier, daily_limit, daily_used, last_used_date, custom_signature, telegram_chat_id, group_title, status, starts_at, expires_at, order_id, owner_user_id")
      .order("expires_at", { ascending: false });

    if (requestedLicenseId && isAdmin) {
      query = query.eq("id", requestedLicenseId);
    } else if (!isAdmin) {
      query = query.eq("owner_user_id", session.user.id);
    }

    const { data: licenses, error } = await query;

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    // If admin and no personal license found, fall back to the first available license in DB
    let activeList = licenses || [];
    if (activeList.length === 0 && isAdmin) {
      const { data: allLics } = await supabase
        .from("b2b_group_licenses")
        .select("id, tier, daily_limit, daily_used, last_used_date, custom_signature, telegram_chat_id, group_title, status, starts_at, expires_at, order_id, owner_user_id")
        .order("created_at", { ascending: false })
        .limit(10);
      activeList = allLics || [];
    }

    const primaryLicense = activeList[0] || null;

    return NextResponse.json({
      ok: true,
      has_license: Boolean(primaryLicense),
      license: primaryLicense,
      licenses: activeList,
      is_admin: isAdmin,
      user_email: session.user.email,
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}

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
    const { action, license_id, code, telegram_chat_id, custom_signature, group_title } = body;

    // Action: Start 3-day Free Trial
    if (action === "start_trial") {
      const requestedTier = String(body.tier || "b2b_pro");
      const validTiers = ["b2b_starter", "b2b_pro", "b2b_enterprise"];
      const tier = validTiers.includes(requestedTier) ? requestedTier : "b2b_pro";

      if (!isAdmin) {
        const { data: existingTrials } = await supabase
          .from("b2b_group_licenses")
          .select("id, order_id")
          .eq("owner_user_id", session.user.id)
          .ilike("order_id", "B2B-TRIAL-%")
          .limit(1);

        if (existingTrials && existingTrials.length > 0) {
          return NextResponse.json(
            {
              ok: false,
              error: "لقد استنفدت بالفعل فترة التجربة المجانية لحسابك. يمكنك الاشتراك المباشر لترخيص البوت في مجموعتك.",
              already_used: true,
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
      const orderId = `B2B-TRIAL-${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
      const startsAt = new Date().toISOString();
      const expiresAt = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();

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
        return NextResponse.json({ ok: false, error: insertErr?.message || "Failed to create trial" }, { status: 500 });
      }

      const activationCode = String(newLicense.id).slice(0, 8);
      const botUsername = (process.env.TELEGRAM_BOT_USERNAME || "egxbots_bot").replace(/^@/, "");
      const connectUrl = `https://t.me/${botUsername}?startgroup=activate_${activationCode}`;

      return NextResponse.json({
        ok: true,
        license: newLicense,
        activation_code: activationCode,
        connect_url: connectUrl,
        message: "تم إنشاء رخصتك التجريبية (3 أيام) بنجاح!",
      });
    }

    // Action: Claim license with activation code or order id
    if (action === "claim" || (code && !license_id)) {
      const searchCode = (code || "").trim();
      if (!searchCode) {
        return NextResponse.json({ ok: false, error: "كود التفعيل مطلوب" }, { status: 400 });
      }

      const { data: allLics } = await supabase
        .from("b2b_group_licenses")
        .select("id, order_id, owner_user_id")
        .in("status", ["active", "paused"]);

      const matched = (allLics || []).find((l: any) => {
        const lid = String(l.id || "").toLowerCase();
        const ord = String(l.order_id || "").toLowerCase();
        const sc = searchCode.toLowerCase();
        return lid.startsWith(sc) || ord.includes(sc) || lid === sc;
      });

      if (!matched) {
        return NextResponse.json({ ok: false, error: "كود الترخيص غير صحيح أو منتهي" }, { status: 404 });
      }

      // Link to this user
      const { data: updated, error: linkErr } = await supabase
        .from("b2b_group_licenses")
        .update({
          owner_user_id: session.user.id,
          updated_at: new Date().toISOString(),
        })
        .eq("id", matched.id)
        .select()
        .single();

      if (linkErr) {
        return NextResponse.json({ ok: false, error: linkErr.message }, { status: 500 });
      }

      return NextResponse.json({ ok: true, license: updated, message: "تم ربط الترخيص بحسابك بنجاح!" });
    }

    if (!license_id) {
      return NextResponse.json({ ok: false, error: "license_id is required" }, { status: 400 });
    }

    const updates: Record<string, any> = {
      updated_at: new Date().toISOString(),
    };

    if (typeof custom_signature === "string") {
      updates.custom_signature = custom_signature.slice(0, 150).trim();
    }

    if (typeof group_title === "string") {
      updates.group_title = group_title.slice(0, 100).trim();
    }

    if (telegram_chat_id !== undefined) {
      const parsedChatId = Number(telegram_chat_id);
      if (!isNaN(parsedChatId) && parsedChatId !== 0) {
        updates.telegram_chat_id = parsedChatId;
      }
    }

    let updateQuery = supabase
      .from("b2b_group_licenses")
      .update(updates)
      .eq("id", license_id);

    if (!isAdmin) {
      updateQuery = updateQuery.eq("owner_user_id", session.user.id);
    }

    const { data, error } = await updateQuery.select().single();

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, license: data });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 });
  }
}
