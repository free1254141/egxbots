import { requireAdmin } from "@/lib/admin-auth";
import { NextRequest, NextResponse } from "next/server";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export interface SocialReportImageItem {
  id: string;
  name: string;
  path: string;
  session_date: string;
  kind: "stock" | "market" | "accumulation" | "follow_up" | "unknown";
  symbol: string | null;
  url: string;
  size: number;
  created_at: string | null;
  last_modified: string | null;
  social_title: string | null;
  social_caption: string | null;
  social_hashtags: string[] | null;
  content: string | null;
  image_status: string | null;
}

function parseKind(filename: string): "stock" | "market" | "accumulation" | "follow_up" | "unknown" {
  if (filename.startsWith("accumulation")) return "accumulation";
  if (filename.startsWith("follow_up")) return "follow_up";
  if (filename.startsWith("market")) return "market";
  if (filename.startsWith("stock")) return "stock";
  return "unknown";
}

export async function GET(req: NextRequest) {
  const auth = await requireAdmin(req);
  if (auth instanceof Response) return auth;

  try {
    const url = new URL(req.url);
    const dateParam = url.searchParams.get("date"); // optional YYYY-MM-DD filter
    const kindParam = url.searchParams.get("kind"); // optional kind filter

    const client = getSupabaseServiceClient();

    // 1. Fetch root items (folders representing session dates)
    const { data: rootItems, error: storageError } = await client.storage
      .from("social-reports")
      .list("", { limit: 100, sortBy: { column: "name", order: "desc" } });

    if (storageError) {
      return NextResponse.json({ detail: storageError.message }, { status: 500 });
    }

    // Filter folder names (e.g. "2026-10-19")
    const folders = (rootItems || [])
      .filter((item: any) => item.name && /^\d{4}-\d{2}-\d{2}$/.test(item.name))
      .map((item: any) => item.name)
      .sort((a: string, b: string) => b.localeCompare(a));

    const targetFolders = dateParam ? folders.filter((f: string) => f === dateParam) : folders;

    // 2. Query daily_social_reports metadata for enrichment (strict bounded read)
    const { data: dbReports } = await client
      .from("daily_social_reports")
      .select("session_date, kind, symbol, image_status, image_url, social_title, social_caption, social_hashtags, content, created_at, updated_at")
      .order("session_date", { ascending: false })
      .limit(300);

    const reportLookup = new Map<string, any>();
    if (dbReports && Array.isArray(dbReports)) {
      for (const r of dbReports) {
        reportLookup.set(`${r.session_date}_${r.kind}`, r);
      }
    }

    // 3. List files in target date folders concurrently
    const folderResults = await Promise.all(
      targetFolders.map(async (folderDate: string) => {
        const { data: files, error: folderErr } = await client.storage
          .from("social-reports")
          .list(folderDate, { limit: 20, sortBy: { column: "name", order: "asc" } });

        if (folderErr || !files) return [];

        return files.filter((f: any) => f.name.endsWith(".png")).map((f: any): SocialReportImageItem => {
          const filePath = `${folderDate}/${f.name}`;
          const kind = parseKind(f.name);
          const meta = f.metadata || {};
          const matchedDb = reportLookup.get(`${folderDate}_${kind}`);
          const { data: pubData } = client.storage.from("social-reports").getPublicUrl(filePath);

          return {
            id: f.id || filePath,
            name: f.name,
            path: filePath,
            session_date: folderDate,
            kind,
            symbol: matchedDb?.symbol || null,
            url: matchedDb?.image_url || pubData.publicUrl,
            size: meta.size || meta.contentLength || 0,
            created_at: f.created_at || meta.lastModified || matchedDb?.created_at || null,
            last_modified: meta.lastModified || f.updated_at || null,
            social_title: matchedDb?.social_title || null,
            social_caption: matchedDb?.social_caption || null,
            social_hashtags: matchedDb?.social_hashtags || null,
            content: matchedDb?.content || null,
            image_status: matchedDb?.image_status || "ready",
          };
        });
      })
    );

    let allImages = folderResults.flat();

    if (kindParam && kindParam !== "all") {
      allImages = allImages.filter((img) => img.kind === kindParam);
    }

    // Sort images: newest session date first, then by kind
    allImages.sort((a, b) => {
      const dateCmp = b.session_date.localeCompare(a.session_date);
      if (dateCmp !== 0) return dateCmp;
      return a.name.localeCompare(b.name);
    });

    const totalBytes = allImages.reduce((sum, img) => sum + img.size, 0);

    return NextResponse.json({
      bucket: "social-reports",
      stats: {
        total_images: allImages.length,
        total_bytes: totalBytes,
        total_mb: Number((totalBytes / (1024 * 1024)).toFixed(2)),
        total_dates: folders.length,
        latest_date: folders[0] || null,
      },
      dates: folders,
      images: allImages,
    });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error?.message || "Failed to fetch social report images" },
      { status: 500 }
    );
  }
}
