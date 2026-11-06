import { requireAdmin } from "@/lib/admin-auth";
import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { summarizeTrialFunnel, type MessageRow, type SubscriptionRow, type TrialEventRow, type TrialRow } from "@/lib/trial-funnel";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  try {
    const supabase = getSupabaseServiceClient();

    const { data: trialRows, error: trialError } = await supabase
      .from("subscription_trials")
      .select("user_id,started_at,expires_at")
      .order("started_at", { ascending: false })
      .limit(5000);
    if (trialError) throw trialError;

    const trials = (trialRows || []) as TrialRow[];
    if (trials.length === 0) {
      return NextResponse.json({ funnel: summarizeTrialFunnel([], [], [], []) });
    }

    const oldestTrial = trials.reduce((oldest, trial) => {
      const at = new Date(trial.started_at).getTime();
      return Number.isFinite(at) && at < oldest ? at : oldest;
    }, Date.now());

    const [subsRes, messagesRes, eventsRes] = await Promise.all([
      supabase
        .from("subscriptions")
        .select("user_id,plan_id,status,provider,current_period_start,created_at")
        .limit(5000),
      supabase
        .from("ai_chat_messages")
        .select("user_id,created_at")
        .eq("role", "user")
        .gte("created_at", new Date(oldestTrial).toISOString())
        .limit(5000),
      supabase
        .from("user_activity_events")
        .select("user_id,event_name,metadata")
        .eq("event_name", "trial_started")
        .limit(5000),
    ]);

    const funnel = summarizeTrialFunnel(
      trials,
      (subsRes.data || []) as SubscriptionRow[],
      (messagesRes.data || []) as MessageRow[],
      (eventsRes.data || []) as TrialEventRow[],
    );

    return NextResponse.json({ funnel });
  } catch (error) {
    console.error("[admin/trials/funnel]", error);
    return NextResponse.json({ error: "Trial funnel unavailable" }, { status: 500 });
  }
}
