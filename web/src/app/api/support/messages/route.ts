import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getSupabaseClient } from "@/lib/supabase/route-data";
import { getViewerContext } from "@/lib/supabase/viewer-context";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1"; // Prevent multi-region cold starts

/**
 * Support history for the signed-in owner of the session.
 *
 * This endpoint backs the 2-minute safety-net poll (Realtime delivers the live
 * updates), so it is called repeatedly while a chat is open. It therefore:
 *   - resolves identity through the cached viewer context instead of a Supabase
 *     Auth round trip on every poll,
 *   - selects explicit columns with a hard limit instead of `*`,
 *   - accepts `since` so an incremental poll only transfers new rows.
 */
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const sessionId = url.searchParams.get("session_id") || "";
    if (!sessionId) return NextResponse.json({ messages: [] });

    const { userId } = await getViewerContext(req);
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    if (sessionId !== userId) return NextResponse.json({ error: "Invalid support session" }, { status: 403 });

    const since = url.searchParams.get("since") || "";
    const supabase = getSupabaseClient();

    let query = supabase
      .from("support_messages")
      .select("id, session_id, sender, content, user_name, image_url, created_at")
      .eq("session_id", sessionId)
      .order("created_at", { ascending: true })
      .limit(200);

    if (since) {
      // Incremental: only what arrived after the client's newest message.
      query = query.gt("created_at", since);
    }

    const { data } = await query;

    return NextResponse.json({
      messages: data || [],
      incremental: Boolean(since),
      server_time: new Date().toISOString(),
    });
  } catch (error) {
    console.error("support messages route error:", error);
    return NextResponse.json({ messages: [] });
  }
}
