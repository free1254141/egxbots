import { buildCompoundDeterministicPlan } from "../pipeline";
import { fuzzyFindStockSymbol } from "../fuzzy-stocks";
import { SessionState } from "../types";

describe("Fuzzy stock matcher fast-path", () => {
    const dummySession: SessionState = {
        current_symbol: null,
        last_symbols: [],
        summary: ""
    };

    it("matches exact ticker symbol", () => {
        const match = fuzzyFindStockSymbol("ABUK");
        expect(match).not.toBeNull();
        expect(match?.symbol).toBe("ABUK");
    });

    it("matches Arabic stock name with typical typos", () => {
        const match1 = fuzzyFindStockSymbol("حلل عتاقه");
        expect(match1).not.toBeNull();
        expect(match1?.symbol).toBe("ATQA");

        const match2 = fuzzyFindStockSymbol('"حلل عتاقه"');
        expect(match2).not.toBeNull();
        expect(match2?.symbol).toBe("ATQA");

        const match3 = fuzzyFindStockSymbol("عتاقا");
        expect(match3).not.toBeNull();
        expect(match3?.symbol).toBe("ATQA");
    });

    it("matches colloquial multi-word stock names", () => {
        const match = fuzzyFindStockSymbol("ايه رأيك في سهم ابو كير");
        expect(match).not.toBeNull();
        expect(match?.symbol).toBe("ABUK");
    });

    it("returns null for non-stock conversational queries", () => {
        expect(fuzzyFindStockSymbol("ازيك يا فنان")).toBeNull();
        expect(fuzzyFindStockSymbol("السوق طالع ولا نازل")).toBeNull();
        expect(fuzzyFindStockSymbol("هات كل التوصيات المفتوحة")).toBeNull();
    });

    it("builds deterministic plan for matched stocks", () => {
        const plan1 = buildCompoundDeterministicPlan('"حلل عتاقه"', dummySession);
        expect(plan1?.entities.symbols).toContain("ATQA");
        expect(plan1?.intent).toBe("stock_analysis");

        const plan2 = buildCompoundDeterministicPlan("ABUK", dummySession);
        expect(plan2?.entities.symbols).toContain("ABUK");
        expect(plan2?.intent).toBe("stock_analysis");
    });
});
