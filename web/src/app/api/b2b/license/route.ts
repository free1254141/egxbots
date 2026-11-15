import { NextRequest, NextResponse } from "next/server";
import { isAllowedAdminEmail } from "@/lib/admin-auth-client";
import {
  createB2BTrialForUser,
  getB2BServiceClient,
  getVerifiedB2BUser,
} from "@/lib/b2b-server";

export const runtime = "nodejs";

const LICENSE_COLUMNS =
  "id, tier, daily_limit, daily_used, last_used_date, custom_signature, allow_recommendations, telegram_chat_id, group_title, status, starts_at, expires_at, order_id, owner_user_id";

export async function GET(req: NextRequest) {
  try {
    const user = await getVerifiedB2BUser(req);
    if (!user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const isAdmin = isAllowedAdminEmail(user.email);
    const adminDb = getB2BServiceClient();
    const url = new URL(req.url);
    const requestedLicenseId = url.searchParams.get("license_id");

    let query = adminDb
      .from("b2b_group_licenses")
      .select(LICENSE_COLUMNS)
      .order("expires_at", { ascending: false });

    if (!isAdmin) {
      query = query.eq("owner_user_id", user.id);
    } else {
      query = query.limit(25);
    }

    const { data: licenses, error } = await query;
    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    let activeList = licenses || [];
    if (requestedLicenseId && isAdmin && !activeList.some((l) => l.id === requestedLicenseId)) {
      const { data: specific } = await adminDb
        .from("b2b_group_licenses")
        .select(LICENSE_COLUMNS)
        .eq("id", requestedLicenseId)
        .maybeSingle();
      if (specific) {
        activeList = [specific, ...activeList];
      }
    }

    const primaryLicense = requestedLicenseId
      ? activeList.find((l) => l.id === requestedLicenseId) || activeList[0] || null
      : activeList[0] || null;

    return NextResponse.json({
      ok: true,
      has_license: Boolean(primaryLicense),
      license: primaryLicense,
      licenses: activeList,
      is_admin: isAdmin,
      user_email: user.email,
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err?.message || "Server error" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const user = await getVerifiedB2BUser(req);
    if (!user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const isAdmin = isAllowedAdminEmail(user.email);
    const adminDb = getB2BServiceClient();
    const body = await req.json().catch(() => ({}));
    const { action, license_id, code, telegram_chat_id, custom_signature, group_title, allow_recommendations } = body;

    // 1. Start 3-day Free Trial
    if (action === "start_trial") {
      const result = await createB2BTrialForUser(user, body.tier);
      if (!result.ok) {
        return NextResponse.json(
          {
            ok: false,
            error: result.message || result.error,
            ...(result.already_used ? { already_used: true } : {}),
          },
          { status: result.status }
        );
      }
      return NextResponse.json({
        ok: true,
        license: result.license,
        activation_code: result.activation_code,
        connect_url: result.connect_url,
        message: "تم إنشاء رخصتك التجريبية (3 أيام) بنجاح!",
      });
    }

    // 2. Claim license with exact activation code / UUID (>= 8 chars) or exact order_id
    if (action === "claim" || (code && !license_id)) {
      const searchCode = String(code || "").trim();
      if (searchCode.length < 8) {
        return NextResponse.json(
          { ok: false, error: "يجب إدخال كود التفعيل كاملاً (8 أحرف على الأقل)" },
          { status: 400 }
        );
      }

      const { data: allLics, error: listErr } = await adminDb
        .from("b2b_group_licenses")
        .select("id, order_id, owner_user_id, expires_at")
        .in("status", ["active", "paused"]);

      if (listErr) {
        return NextResponse.json({ ok: false, error: listErr.message }, { status: 500 });
      }

      const sc = searchCode.toLowerCase();
      const now = new Date();
      const matched = (allLics || []).find((l: any) => {
        if (l.expires_at && new Date(l.expires_at) <= now) return false;
        const lid = String(l.id || "").toLowerCase();
        const ord = String(l.order_id || "").toLowerCase();
        return lid === sc || lid.startsWith(sc) || (Boolean(ord) && ord === sc);
      });

      if (!matched) {
        return NextResponse.json({ ok: false, error: "كود الترخيص غير صحيح أو منتهي الصلاحية" }, { status: 404 });
      }

      if (matched.owner_user_id && matched.owner_user_id !== user.id && !isAdmin) {
        return NextResponse.json(
          { ok: false, error: "هذه الرخصة مرتبطة بالفعل بحساب مستخدم آخر ولا يمكن نقلها" },
          { status: 409 }
        );
      }

      const { data: updated, error: linkErr } = await adminDb
        .from("b2b_group_licenses")
        .update({
          owner_user_id: user.id,
          updated_at: new Date().toISOString(),
        })
        .eq("id", matched.id)
        .select(LICENSE_COLUMNS)
        .single();

      if (linkErr) {
        return NextResponse.json({ ok: false, error: linkErr.message }, { status: 500 });
      }

      return NextResponse.json({ ok: true, license: updated, message: "تم ربط الترخيص بحسابك بنجاح!" });
    }

    if (!license_id) {
      return NextResponse.json({ ok: false, error: "license_id is required" }, { status: 400 });
    }

    // 3. Unlink current Telegram group so owner can transfer to another group cleanly
    if (action === "unlink") {
      let unlinkQuery = adminDb
        .from("b2b_group_licenses")
        .update({
          telegram_chat_id: null,
          group_title: "مجموعة تليجرام (بانتظار التفعيل)",
          updated_at: new Date().toISOString(),
        })
        .eq("id", license_id);

      if (!isAdmin) {
        unlinkQuery = unlinkQuery.eq("owner_user_id", user.id);
      }

      const { data: unlinked, error: unlinkErr } = await unlinkQuery.select(LICENSE_COLUMNS).single();
      if (unlinkErr) {
        return NextResponse.json({ ok: false, error: unlinkErr.message }, { status: 500 });
      }
      return NextResponse.json({ ok: true, license: unlinked, message: "تم فك ربط المجموعة السابقة بنجاح" });
    }

    // 4. Update configuration (signature & group title; telegram_chat_id changes are admin-only)
    const updates: Record<string, any> = {
      updated_at: new Date().toISOString(),
    };

    if (typeof custom_signature === "string") {
      updates.custom_signature = custom_signature.slice(0, 150).trim();
    }

    if (typeof group_title === "string") {
      updates.group_title = group_title.slice(0, 100).trim();
    }

    if (typeof allow_recommendations === "boolean") {
      updates.allow_recommendations = allow_recommendations;
    }

    if (isAdmin && telegram_chat_id !== undefined) {
      const parsedChatId = telegram_chat_id === null ? null : Number(telegram_chat_id);
      if (parsedChatId === null || (!Number.isNaN(parsedChatId) && parsedChatId !== 0)) {
        updates.telegram_chat_id = parsedChatId;
      }
    }

    let updateQuery = adminDb
      .from("b2b_group_licenses")
      .update(updates)
      .eq("id", license_id);

    if (!isAdmin) {
      updateQuery = updateQuery.eq("owner_user_id", user.id);
    }

    const { data, error } = await updateQuery.select(LICENSE_COLUMNS).single();

    if (error) {
      return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, license: data });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err?.message || "Server error" }, { status: 500 });
  }
}
