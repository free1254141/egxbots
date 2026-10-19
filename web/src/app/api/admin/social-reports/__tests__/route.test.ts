import { NextRequest } from "next/server";
import { GET } from "../route";
import { requireAdmin } from "@/lib/admin-auth";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

jest.mock("@/lib/admin-auth", () => ({ requireAdmin: jest.fn() }));
jest.mock("@/lib/supabase/route-data", () => ({ getSupabaseServiceClient: jest.fn() }));

const mockRequireAdmin = requireAdmin as jest.Mock;
const mockGetSupabaseServiceClient = getSupabaseServiceClient as jest.Mock;

describe("Social Reports Admin API Route", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequireAdmin.mockResolvedValue({ user: { id: "admin-1" } });
  });

  it("returns 401 when unauthorized", async () => {
    mockRequireAdmin.mockResolvedValue(new Response("Unauthorized", { status: 401 }));
    const req = new NextRequest("https://egxbots.com/api/admin/social-reports");
    const res = await GET(req);
    expect(res.status).toBe(401);
    expect(mockGetSupabaseServiceClient).not.toHaveBeenCalled();
  });

  it("fetches, parses, and enriches bucket files correctly", async () => {
    const mockStorageFrom = {
      list: jest.fn((folder: string) => {
        if (folder === "") {
          return Promise.resolve({
            data: [
              { name: "2026-10-19" },
              { name: "2026-10-18" },
              { name: "not-a-date" },
            ],
            error: null,
          });
        }
        if (folder === "2026-10-19") {
          return Promise.resolve({
            data: [
              {
                id: "file-1",
                name: "stock-v4-abc12345.png",
                metadata: { size: 102400, lastModified: "2026-10-19T14:00:00Z" },
              },
              {
                id: "file-2",
                name: "market-v4-def67890.png",
                metadata: { size: 1048576, lastModified: "2026-10-19T14:05:00Z" },
              },
            ],
            error: null,
          });
        }
        if (folder === "2026-10-18") {
          return Promise.resolve({
            data: [
              {
                id: "file-3",
                name: "accumulation-v4-acc111.png",
                metadata: { size: 51200, lastModified: "2026-10-18T14:00:00Z" },
              },
            ],
            error: null,
          });
        }
        return Promise.resolve({ data: [], error: null });
      }),
      getPublicUrl: jest.fn((path: string) => ({
        data: { publicUrl: `https://mock.supabase.co/storage/v1/object/public/social-reports/${path}` },
      })),
    };

    const mockDbQuery = {
      select: jest.fn().mockReturnThis(),
      order: jest.fn().mockReturnThis(),
      limit: jest.fn().mockResolvedValue({
        data: [
          {
            session_date: "2026-10-19",
            kind: "stock",
            symbol: "COMI",
            social_title: "تحليل سهم التجاري الدولي",
            social_caption: "تقرير كامل ومفصل",
            social_hashtags: ["#EGXBOTS", "#COMI"],
            image_url: "https://mock.supabase.co/storage/v1/object/public/social-reports/2026-10-19/stock-v4-abc12345.png",
            image_status: "ready",
          },
        ],
        error: null,
      }),
    };

    mockGetSupabaseServiceClient.mockReturnValue({
      storage: {
        from: jest.fn(() => mockStorageFrom),
      },
      from: jest.fn(() => mockDbQuery),
    });

    const req = new NextRequest("https://egxbots.com/api/admin/social-reports");
    const res = await GET(req);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.bucket).toBe("social-reports");
    expect(json.dates).toEqual(["2026-10-19", "2026-10-18"]);
    expect(json.stats.total_images).toBe(3);
    expect(json.stats.total_dates).toBe(2);
    expect(json.stats.latest_date).toBe("2026-10-19");
    expect(json.images).toHaveLength(3);

    // Enriched item check
    const stockImg = json.images.find((i: any) => i.kind === "stock");
    expect(stockImg).toBeDefined();
    expect(stockImg.symbol).toBe("COMI");
    expect(stockImg.social_title).toBe("تحليل سهم التجاري الدولي");
    expect(stockImg.session_date).toBe("2026-10-19");
  });

  it("filters by kind when kind query parameter is passed", async () => {
    const mockStorageFrom = {
      list: jest.fn((folder: string) => {
        if (folder === "") {
          return Promise.resolve({ data: [{ name: "2026-10-19" }], error: null });
        }
        return Promise.resolve({
          data: [
            { id: "1", name: "stock-v4-1.png", metadata: { size: 100 } },
            { id: "2", name: "market-v4-2.png", metadata: { size: 200 } },
          ],
          error: null,
        });
      }),
      getPublicUrl: jest.fn((path: string) => ({
        data: { publicUrl: `https://mock.supabase.co/${path}` },
      })),
    };

    mockGetSupabaseServiceClient.mockReturnValue({
      storage: { from: jest.fn(() => mockStorageFrom) },
      from: jest.fn(() => ({
        select: jest.fn().mockReturnThis(),
        order: jest.fn().mockReturnThis(),
        limit: jest.fn().mockResolvedValue({ data: [], error: null }),
      })),
    });

    const req = new NextRequest("https://egxbots.com/api/admin/social-reports?kind=market");
    const res = await GET(req);
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.images).toHaveLength(1);
    expect(json.images[0].kind).toBe("market");
  });
});
