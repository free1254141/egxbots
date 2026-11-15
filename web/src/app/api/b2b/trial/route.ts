import { NextRequest, NextResponse } from "next/server";
import { createB2BTrialForUser, getVerifiedB2BUser } from "@/lib/b2b-server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  try {
    const user = await getVerifiedB2BUser(req);
    if (!user) {
      return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const result = await createB2BTrialForUser(user, body.tier);

    if (!result.ok) {
      return NextResponse.json(
        {
          ok: false,
          error: result.error,
          ...(result.already_used ? { already_used: true } : {}),
          ...(result.message ? { message: result.message } : {}),
        },
        { status: result.status }
      );
    }

    return NextResponse.json({
      ok: true,
      license: result.license,
      activation_code: result.activation_code,
      connect_url: result.connect_url,
      message: result.message,
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err?.message || "Server error" }, { status: 500 });
  }
}
