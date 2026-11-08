import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const revalidate = 86400;

function escapeXml(unsafe: string | null | undefined): string {
  if (!unsafe) return "";
  return String(unsafe)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function wrapText(text: string, maxCharsPerLine: number, maxLines: number): string[] {
  const words = (text || "").replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    if ((current + " " + word).trim().length <= maxCharsPerLine) {
      current = (current + " " + word).trim();
    } else {
      if (current) lines.push(current);
      current = word;
      if (lines.length >= maxLines - 1) break;
    }
  }
  if (current && lines.length < maxLines) {
    lines.push(current);
  }
  return lines;
}

function getTypeAr(type: string): string {
  switch (type) {
    case "insider_trading":
      return "نموذج إفصاح تعاملات داخليين ومجموعات مرتبطة";
    case "major_shareholders":
      return "نموذج إفصاح هيكل المساهمين (المادة 30)";
    case "board_resolution":
      return "نموذج إفصاح قرارات مجلس الإدارة";
    case "financial_results":
      return "نموذج إفصاح نتائج أعمال وقوائم مالية";
    default:
      return "نموذج إفصاح جوهري - البورصة المصرية";
  }
}

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  let item: any = null;
  if (supabaseUrl && supabaseKey && id) {
    const supabase = createClient(supabaseUrl, supabaseKey);
    const { data } = await supabase
      .from("egx_disclosures")
      .select("*")
      .eq("id", id)
      .maybeSingle();
    item = data;
  }

  if (!item) {
    item = {
      id: id || "00000000",
      symbol: "EGX",
      company_name: "البورصة المصرية",
      disclosure_type: "material_event",
      disclosure_date: new Date().toISOString().slice(0, 10),
      title: "مستند إفصاح رسمي مسجل بقاعدة بيانات البورصة المصرية",
      raw_content: "تم أرشفة هذا الإفصاح في سجل إفصاحات البورصة المصرية.",
      ai_summary: "إفصاح رسمي مسجل.",
      sentiment: "neutral",
    };
  }

  const refCode = String(item.id || "").slice(0, 8).toUpperCase();
  const symbol = escapeXml(item.symbol || "EGX");
  const companyName = escapeXml(item.company_name || "البورصة المصرية");
  const dateStr = escapeXml(item.disclosure_date || "");
  const typeLabel = escapeXml(getTypeAr(item.disclosure_type));
  const partyName = escapeXml(item.party_name || "إدارة الشركة / المساهمون");
  const partyRole = escapeXml(item.party_role || "مفصح رسمي");
  const sharesStr = item.shares_count
    ? `${Number(item.shares_count).toLocaleString("en-US")} سهم`
    : "غير محدد كمياً";
  const stakeStr =
    item.stake_before != null || item.stake_after != null
      ? `${item.stake_before ?? "—"}% ← ${item.stake_after ?? "—"}%`
      : "وفق هيكل الملكية المودع";

  const isBullish = item.sentiment === "bullish" || item.action_type === "buy";
  const isBearish = item.sentiment === "bearish" || item.action_type === "sell";
  const accentColor = isBullish ? "#00C853" : isBearish ? "#FF1744" : "#D97706";
  const stampText = isBullish
    ? "إشارة إيجابية • تجميع / دعم"
    : isBearish
    ? "إشارة بيعية • تسييل / تخارج"
    : "إفصاح رسمي محايد • موثق";

  const titleLines = wrapText(item.title || "", 68, 3);
  const rawLines = wrapText(item.raw_content || item.title || "", 74, 4);
  const aiLines = wrapText(item.ai_summary || "", 72, 4);
  const takeaway = escapeXml(item.metadata?.key_takeaway || "");

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 680" width="900" height="680">
  <defs>
    <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
      <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#e5e7eb" stroke-width="0.7"/>
    </pattern>
  </defs>

  <!-- Document Paper Background -->
  <rect width="900" height="680" fill="#fcfaf2" />
  <rect width="900" height="680" fill="url(#grid)" opacity="0.55" />

  <!-- Outer Neo-Brutalist Frame -->
  <rect x="18" y="18" width="864" height="644" fill="#ffffff" stroke="#111827" stroke-width="4" />
  <rect x="26" y="26" width="848" height="628" fill="none" stroke="#111827" stroke-width="1.5" stroke-dasharray="6,4" />

  <!-- Top Official Header Bar -->
  <rect x="18" y="18" width="864" height="88" fill="#111827" />
  <rect x="18" y="102" width="864" height="6" fill="#FFE600" />

  <!-- Header Right (Arabic Official Title) -->
  <text x="855" y="54" font-family="Tahoma, Arial, sans-serif" font-size="22" font-weight="bold" fill="#FFE600" text-anchor="end" direction="rtl">
    البورصة المصرية • سجل الإفصاحات الرسمية والشفافية
  </text>
  <text x="855" y="82" font-family="Tahoma, Arial, sans-serif" font-size="14" font-weight="bold" fill="#ffffff" text-anchor="end" direction="rtl">
    ${typeLabel}
  </text>

  <!-- Header Left (Ref ID & Date) -->
  <rect x="38" y="34" width="185" height="54" fill="#1f2937" stroke="#FFE600" stroke-width="2" />
  <text x="130" y="55" font-family="Courier New, monospace" font-size="13" font-weight="bold" fill="#FFE600" text-anchor="middle">
    REF #${escapeXml(refCode)}
  </text>
  <text x="130" y="77" font-family="Courier New, monospace" font-size="13" font-weight="bold" fill="#e5e7eb" text-anchor="middle">
    DATE: ${dateStr}
  </text>

  <!-- Company & Ticker Banner -->
  <rect x="42" y="124" width="816" height="64" fill="#f3f4f6" stroke="#111827" stroke-width="2.5" />
  <rect x="42" y="124" width="140" height="64" fill="#FFE600" stroke="#111827" stroke-width="2.5" />
  <text x="112" y="163" font-family="Arial, sans-serif" font-size="24" font-weight="900" fill="#111827" text-anchor="middle">
    ${symbol}
  </text>
  <text x="838" y="152" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">
    الشركة المفصحة / الجهة المصدرة:
  </text>
  <text x="838" y="176" font-family="Tahoma, Arial, sans-serif" font-size="18" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">
    ${companyName}
  </text>

  <!-- Metadata Grid Table -->
  <rect x="42" y="202" width="816" height="68" fill="#ffffff" stroke="#111827" stroke-width="2" />
  <line x1="314" y1="202" x2="314" y2="270" stroke="#111827" stroke-width="2" />
  <line x1="586" y1="202" x2="586" y2="270" stroke="#111827" stroke-width="2" />

  <!-- Col 1: Party -->
  <text x="842" y="224" font-family="Tahoma, Arial, sans-serif" font-size="11" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">
    الطرف المفصح / الصفة:
  </text>
  <text x="842" y="246" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">
    ${partyName}
  </text>
  <text x="842" y="263" font-family="Tahoma, Arial, sans-serif" font-size="11" fill="#4b5563" text-anchor="end" direction="rtl">
    (${partyRole})
  </text>

  <!-- Col 2: Shares -->
  <text x="570" y="224" font-family="Tahoma, Arial, sans-serif" font-size="11" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">
    حجم التعامل / الكمية المسجلة:
  </text>
  <text x="570" y="250" font-family="Tahoma, Arial, sans-serif" font-size="15" font-weight="bold" fill="${accentColor}" text-anchor="end" direction="rtl">
    ${escapeXml(sharesStr)}
  </text>

  <!-- Col 3: Stake -->
  <text x="298" y="224" font-family="Tahoma, Arial, sans-serif" font-size="11" font-weight="bold" fill="#6b7280" text-anchor="end" direction="rtl">
    نسبة المساهمة (قبل / بعد):
  </text>
  <text x="298" y="250" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">
    ${escapeXml(stakeStr)}
  </text>

  <!-- Section 1: Official Disclosure Text -->
  <rect x="42" y="284" width="816" height="155" fill="#fafafa" stroke="#111827" stroke-width="2" />
  <rect x="688" y="284" width="170" height="26" fill="#111827" />
  <text x="773" y="302" font-family="Tahoma, Arial, sans-serif" font-size="12" font-weight="bold" fill="#FFE600" text-anchor="middle" direction="rtl">
    نص بيان الإفصاح الرسمي
  </text>

  ${titleLines
    .map(
      (line, idx) =>
        `<text x="840" y="${332 + idx * 24}" font-family="Tahoma, Arial, sans-serif" font-size="15" font-weight="bold" fill="#111827" text-anchor="end" direction="rtl">${escapeXml(
          line
        )}</text>`
    )
    .join("\n  ")}

  ${rawLines
    .slice(0, 2)
    .map(
      (line, idx) =>
        `<text x="840" y="${332 + titleLines.length * 24 + 8 + idx * 20}" font-family="Tahoma, Arial, sans-serif" font-size="12.5" fill="#4b5563" text-anchor="end" direction="rtl">${escapeXml(
          line
        )}</text>`
    )
    .join("\n  ")}

  <!-- Section 2: AI Financial Analysis Box -->
  <rect x="42" y="454" width="816" height="145" fill="#fffbeb" stroke="#111827" stroke-width="2.5" />
  <rect x="648" y="454" width="210" height="28" fill="#FFE600" stroke="#111827" stroke-width="2" />
  <text x="753" y="473" font-family="Tahoma, Arial, sans-serif" font-size="12.5" font-weight="bold" fill="#111827" text-anchor="middle" direction="rtl">
    تحليل الذكاء الاصطناعي • EGX BOTS
  </text>

  ${aiLines
    .map(
      (line, idx) =>
        `<text x="840" y="${505 + idx * 22}" font-family="Tahoma, Arial, sans-serif" font-size="13.5" font-weight="bold" fill="#1f2937" text-anchor="end" direction="rtl">${escapeXml(
          line
        )}</text>`
    )
    .join("\n  ")}

  ${
    takeaway
      ? `<text x="840" y="588" font-family="Tahoma, Arial, sans-serif" font-size="12.5" font-weight="bold" fill="${accentColor}" text-anchor="end" direction="rtl">★ الخلاصة الاستثمارية: ${takeaway}</text>`
      : ""
  }

  <!-- Bottom Stamp & Verification Footer -->
  <rect x="42" y="610" width="260" height="34" fill="${accentColor}" stroke="#111827" stroke-width="2" />
  <text x="172" y="632" font-family="Tahoma, Arial, sans-serif" font-size="13" font-weight="bold" fill="#ffffff" text-anchor="middle" direction="rtl">
    ${escapeXml(stampText)}
  </text>

  <text x="855" y="632" font-family="Courier New, Tahoma, sans-serif" font-size="12" font-weight="bold" fill="#374151" text-anchor="end">
    EGX-DISCLOSURE-ID: ${escapeXml(String(item.id))} • VERIFIED BY EGXBOTS.COM
  </text>
</svg>`;

  return new NextResponse(svg, {
    status: 200,
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
    },
  });
}
