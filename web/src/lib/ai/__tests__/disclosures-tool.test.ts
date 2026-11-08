import { executeAgenticTool } from "../agentic-tools";
import { executeStructuredTools } from "../tools-v2";

describe("get_disclosures agentic tool", () => {
  it("should fetch disclosures and return structured response", async () => {
    // Mock Supabase client
    const mockData = [
      {
        id: "test-id-1",
        symbol: "FWRY",
        company_name: "فوري لتكنولوجيا البنوك والمدفوعات الالكترونية",
        disclosure_type: "insider_trading",
        disclosure_date: "2026-11-04",
        title: "شراء مجموعة مرتبطة بداخلي 90,946 سهم في شركة فوري",
        raw_content: "شراء 90946 سهم",
        ai_summary: "شراء مطلعين يعكس ثقة داعمة للسهم",
        sentiment: "bullish",
        action_type: "buy",
        shares_count: 90946,
        party_name: "مجموعة مرتبطة بداخلي",
        party_role: "مجموعة مرتبطة",
        source_url: "https://example.com/pdf",
        metadata: { key_takeaway: "تجميع مطلعين إيجابي" }
      }
    ];

    const mockSupabase = {
      from: jest.fn().mockReturnValue({
        select: jest.fn().mockReturnThis(),
        order: jest.fn().mockReturnThis(),
        eq: jest.fn().mockReturnThis(),
        limit: jest.fn().mockResolvedValue({ data: mockData, error: null })
      })
    };

    const res = await executeAgenticTool("get_disclosures", { symbol: "FWRY", limit: 5 }, mockSupabase, "test-user");

    expect(res.status).toBe("success");
    expect(res.availability).toBe("available");
    expect(res.count).toBe(1);
    expect(res.symbol).toBe("FWRY");
    expect(res.disclosures[0].symbol).toBe("FWRY");
    expect(res.disclosures[0].ai_summary).toBe("شراء مطلعين يعكس ثقة داعمة للسهم");
    expect(res.disclosures[0].sentiment).toBe("bullish");
  });

  it("should handle general market queries without symbol", async () => {
    const mockData = [
      {
        id: "test-id-2",
        symbol: null,
        company_name: "البورصة المصرية",
        disclosure_type: "insider_trading",
        disclosure_date: "2026-11-05",
        title: "تعاملات الداخليين والمساهمين الرئيسيين",
        ai_summary: "إفصاح روتيني عن تعاملات الجلسة",
        sentiment: "neutral",
        action_type: "general",
        metadata: {}
      }
    ];

    const mockSupabase = {
      from: jest.fn().mockReturnValue({
        select: jest.fn().mockReturnThis(),
        order: jest.fn().mockReturnThis(),
        eq: jest.fn().mockReturnThis(),
        limit: jest.fn().mockResolvedValue({ data: mockData, error: null })
      })
    };

    const res = await executeAgenticTool("get_disclosures", { limit: 10 }, mockSupabase, "test-user");

    expect(res.status).toBe("success");
    expect(res.symbol).toBe("all");
    expect(res.count).toBe(1);
  });

  it("should support get_disclosures in executeStructuredTools", async () => {
    const mockData = [
      {
        id: "test-id-3",
        symbol: "FWRY",
        company_name: "فوري",
        disclosure_type: "insider_trading",
        disclosure_date: "2026-11-04",
        title: "شراء مطلعين",
        ai_summary: "تجميع إيجابي",
        sentiment: "bullish",
      }
    ];

    const mockSupabase = {
      from: jest.fn().mockReturnValue({
        select: jest.fn().mockReturnThis(),
        order: jest.fn().mockReturnThis(),
        in: jest.fn().mockReturnThis(),
        limit: jest.fn().mockResolvedValue({ data: mockData, error: null })
      })
    };

    const plan: any = {
      intent: "disclosures",
      entities: { symbols: ["FWRY"] },
      tools: ["get_disclosures"],
      needs_historical_data: true
    };

    const out = await executeStructuredTools(mockSupabase, plan, [], "user-1", "session-1", "إفصاحات فوري");
    expect(out.results.some(r => r.tool === "get_disclosures")).toBe(true);
    expect(out.formattedText).toContain("إفصاحات وتعاملات الداخليين");
  });
});
