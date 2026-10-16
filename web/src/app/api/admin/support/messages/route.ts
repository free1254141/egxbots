import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { requireAdmin } from "@/lib/admin-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const auth = await requireAdmin(req);
    if (auth instanceof Response) return auth;
    const url = new URL(req.url);
    const sessionId = url.searchParams.get("session_id") || "";
    if (!sessionId) {
      return NextResponse.json({ messages: [] });
    }

    const supabase = getSupabaseClient();
    const { data, error } = await supabase
      .from("support_messages")
      .select("*")
      .eq("session_id", sessionId)
      .order("created_at", { ascending: true });

    if (error) {
      console.error("admin get session messages error:", error);
      return NextResponse.json({ detail: error.message }, { status: 500 });
    }

    return NextResponse.json({ messages: data || [] });
  } catch (err: any) {
    console.error("admin get session messages route error:", err);
    return NextResponse.json({ detail: "Internal error" }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const auth = await requireAdmin(req);
    if (auth instanceof Response) return auth;
    const supabase = getSupabaseClient();

    const url = new URL(req.url);
    const body = await req.json().catch(() => ({}));
    const messageId = url.searchParams.get("message_id") || body.message_id;
    const sessionId = url.searchParams.get("session_id") || body.session_id;

    if (messageId) {
      const { error } = await supabase
        .from("support_messages")
        .delete()
        .eq("id", messageId);

      if (error) {
        return NextResponse.json({ detail: error.message }, { status: 500 });
      }
      return NextResponse.json({ ok: true, deleted_message_id: messageId });
    }

    if (sessionId) {
      const { error } = await supabase
        .from("support_messages")
        .delete()
        .eq("session_id", sessionId);

      if (error) {
        return NextResponse.json({ detail: error.message }, { status: 500 });
      }
      return NextResponse.json({ ok: true, deleted_session_id: sessionId });
    }

    return NextResponse.json({ detail: "message_id or session_id is required" }, { status: 400 });
  } catch (err: any) {
    return NextResponse.json({ detail: err.message || "Internal error" }, { status: 500 });
  }
}
