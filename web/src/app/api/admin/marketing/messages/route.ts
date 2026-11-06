import { requireAdmin } from "@/lib/admin-auth";
import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const preferredRegion = "fra1";

type Template = {
  label: string;
  subject: string;
  body: string[];
  when: string;
};

// Keep in sync with api/marketing_lifecycle.py. The log stores delivery
// metadata only, so this map is what the admin previews for each type.
const TEMPLATES: Record<string, Template> = {
  trial_welcome: {
    label: "ترحيب بدء التجربة (Day 0)",
    subject: "⚡ تجربتك في EGX BOTS Pro بدأت — اسأل أول سؤال دلوقتي",
    when: "خلال 24 ساعة من تفعيل التجربة",
    body: [
      "تم تفعيل تجربة Pro المجانية لمدة 3 أيام على حسابك، وكل مزايا VIP مفتوحة الآن.",
      "أسرع طريقة تشوف القيمة: افتح شات الذكاء الاصطناعي واسأل سؤال مباشر، مثل «رشّح لي 3 أسهم عليها فرصة النهارده» أو «حلّل سهم COMI وقولّي مناطق الدخول والخروج».",
      "كل تحليل بيرجعلك بمستويات دخول ووقف خسارة وأهداف، بالإضافة إلى التوصيات المفتوحة ومتابعة المحفظة.",
      "ولو ربطت حسابك بتيليجرام، هتاخد 10 رسائل إضافية مجاناً وتقدر تتابع من الموبايل.",
    ],
  },
  trial_day1: {
    label: "تنشيط اليوم الأول (Day 1)",
    subject: "3 أسئلة تفتح لك قيمة Pro قبل نهاية تجربتك",
    when: "20–48 ساعة من بدء التجربة",
    body: [
      "فاضل أقل من يومين على نهاية تجربتك، وأفضل استغلال ليها هو أسئلة مباشرة على أسهمك.",
      "جرّب واحد من دول الآن: «رشّح لي 3 أسهم عليها فرصة شراء النهارده» — «حلّل سهم في محفظتي وقولّي مناطق الدخول والخروج» — «إيه أقوى القطاعات سيولة هذا الأسبوع؟»",
      "كل إجابة بتوصلك بمستويات تنفيذ واضحة، ومقدرة تتابع توصياتك ومحفظتك من نفس المكان.",
    ],
  },
  trial_expiring: {
    label: "قرب انتهاء التجربة",
    subject: "⏳ فترتك التجريبية في EGX BOTS Pro تنتهي قريباً — اشترك في عرض المؤسسين وثبّت 100 ج.م مدى الحياة",
    when: "أقل من 24 ساعة على انتهاء التجربة",
    body: [
      "نود إعلامك أن تجربتك المجانية لباقة Pro ستنتهي خلال الساعات القادمة.",
      "لتستمر في استخدام الشات بوت واستلام إشعارات النماذج الفنية دون انقطاع، اشترك الآن في عرض المؤسسين بـ 100 ج.م شهرياً مدى الحياة.",
    ],
  },
  abandoned_checkout: {
    label: "سلة دفع متروكة",
    subject: "🔥 تذكير: احجز عرض المؤسسين (100 ج.م شهرياً مدى الحياة) | EGX BOTS",
    when: "2–72 ساعة من محاولة الدفع غير المكتملة",
    body: [
      "لاحظنا أنك بدأت خطوات الاشتراك في باقة Pro للمؤسسين ولم تستكمل عملية الدفع بعد.",
      "عرض المؤسسين متاح لفترة محدودة (15 يوماً فقط) بسعر 100 ج.م شهرياً مدى الحياة بدلاً من 200 ج.م.",
      "يمكنك تفعيل تجربة Pro المجانية لمدة 3 أيام بضغطة واحدة من صفحة الباقات.",
    ],
  },
  subscription_reminder: {
    label: "تذكير بقرب انتهاء الاشتراك",
    subject: "تذكير: اشتراك Pro قارب على الانتهاء",
    when: "قبل انتهاء الاشتراك",
    body: ["رسالة تذكير تلقائية بقرب انتهاء اشتراك Pro مع رابط التجديد."],
  },
};

function labelFor(type: string): string {
  return TEMPLATES[type]?.label || type;
}

export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  try {
    const url = new URL(req.url);
    const requestedLimit = Number(url.searchParams.get("limit") || 200);
    const limit = Number.isFinite(requestedLimit)
      ? Math.min(Math.max(Math.floor(requestedLimit), 1), 500)
      : 200;

    const supabase = getSupabaseServiceClient();
    const { data, error } = await supabase
      .from("marketing_message_log")
      .select("id,user_id,email,message_type,channel,status,sent_at,metadata,provider_message_id")
      .order("sent_at", { ascending: false })
      .limit(limit);
    if (error) throw error;

    const messages = (data || []).map((row: Record<string, any>) => ({
      ...row,
      label: labelFor(String(row.message_type || "")),
    }));

    const counts: Record<string, number> = {};
    for (const row of messages) {
      const type = String(row.message_type || "unknown");
      counts[type] = (counts[type] || 0) + 1;
    }

    return NextResponse.json({ messages, templates: TEMPLATES, counts });
  } catch (error) {
    console.error("[admin/marketing/messages]", error);
    return NextResponse.json({ error: "Marketing messages unavailable" }, { status: 500 });
  }
}
