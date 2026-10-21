import { NextRequest, NextResponse } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { requireAdmin } from "@/lib/admin-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

export async function GET(req: NextRequest) {
  try {
    const auth = await requireAdmin(req);
    if (auth instanceof Response) return auth;
    const supabase = getSupabaseClient();
    
    // Get support messages and group by session
    const { data, error } = await supabase
      .from("support_messages")
      .select("id, session_id, user_id, user_name, content, created_at, sender")
      .order("created_at", { ascending: false })
      .limit(1000);

    if (error) {
      return NextResponse.json({ detail: error.message }, { status: 500 });
    }

    // Group messages into chat sessions
    const sessions: Record<string, any> = {};
    (data || []).forEach((msg: any) => {
      if (!sessions[msg.session_id]) {
        sessions[msg.session_id] = {
          session_id: msg.session_id,
          user_id: msg.user_id,
          user_name: msg.sender === "user" ? msg.user_name : undefined,
          last_message: msg.content,
          last_message_time: msg.created_at,
          last_at: msg.created_at,
          last_sender: msg.sender,
          message_count: 0,
        };
      }
      sessions[msg.session_id].message_count++;

      // Pick user_name from a user message if available
      if (!sessions[msg.session_id].user_name && msg.sender === "user" && msg.user_name) {
        sessions[msg.session_id].user_name = msg.user_name;
      }
    });

    const sessionList = Object.values(sessions);

    // Enrich with profile information if session_id matches a UUID
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const userIds = sessionList
      .map((s) => s.user_id || (uuidRegex.test(s.session_id) ? s.session_id : null))
      .filter(Boolean);

    if (userIds.length > 0) {
      try {
        const { data: profiles } = await supabase
          .from("profiles")
          .select("id, email, whatsapp_number, full_name, plan")
          .in("id", userIds);

        if (profiles) {
          const profMap = new Map<string, any>(profiles.map((p: any) => [p.id, p]));
          sessionList.forEach((s) => {
            const p: any = profMap.get(s.user_id || s.session_id);
            if (p) {
              if (p.full_name && (!s.user_name || s.user_name === "Admin" || s.user_name === "Guest")) {
                s.user_name = p.full_name;
              }
              s.email = p.email;
              s.whatsapp_number = p.whatsapp_number;
              s.plan = p.plan;
            }
          });
        }
      } catch {
        // non-blocking profile enrichment error
      }
    }

    // Ensure fallback user_name is never empty or "Admin"
    sessionList.forEach((s) => {
      if (!s.user_name || s.user_name === "Admin") {
        s.user_name = s.email ? s.email.split("@")[0] : `عميل (${s.session_id.slice(0, 8)})`;
      }
    });

    return NextResponse.json({ 
      chats: sessionList 
    });
  } catch {
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
    const sessionId = url.searchParams.get("session_id") || body.session_id;

    if (!sessionId) {
      return NextResponse.json({ detail: "session_id is required" }, { status: 400 });
    }

    const { error } = await supabase
      .from("support_messages")
      .delete()
      .eq("session_id", sessionId);

    if (error) {
      return NextResponse.json({ detail: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, deleted_session_id: sessionId });
  } catch (err: any) {
    return NextResponse.json({ detail: err.message || "Internal error" }, { status: 500 });
  }
}
