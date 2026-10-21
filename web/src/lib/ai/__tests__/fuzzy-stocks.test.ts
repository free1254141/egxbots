import { fuzzyFindStockSymbol } from "../fuzzy-stocks";

describe("fuzzyFindStockSymbol Fast-Path Test Suite", () => {
    it("should match common Egyptian stock typos and colloquial Arabic queries", () => {
        // Direct typos
        const res1 = fuzzyFindStockSymbol("حلل عتاقه");
        expect(res1?.symbol).toBe("ATQA");

        const res2 = fuzzyFindStockSymbol("حلل عتاقا");
        expect(res2?.symbol).toBe("ATQA");

        // Abu Qir variations
        const res3 = fuzzyFindStockSymbol("سهم ابوقير");
        expect(res3?.symbol).toBe("ABUK");

        const res4 = fuzzyFindStockSymbol("ابو كير للاسمدة");
        expect(res4?.symbol).toBe("ABUK");

        // Talaat Moustafa
        const res5 = fuzzyFindStockSymbol("رايك في طلعت مصطفي");
        expect(res5?.symbol).toBe("TMGH");

        // Fawry
        const res6 = fuzzyFindStockSymbol("سهم فوري النهارده");
        expect(res6?.symbol).toBe("FWRY");

        // Latin Ticker
        const res7 = fuzzyFindStockSymbol("حلل COMI");
        expect(res7?.symbol).toBe("COMI");
    });

    it("should safely return null for broad/complex queries so they fall back to DeepSeek AI", () => {
        expect(fuzzyFindStockSymbol("عايز اشتري ايه النهارده")).toBeNull();
        expect(fuzzyFindStockSymbol("ازيك يا بوت عامل ايه")).toBeNull();
        expect(fuzzyFindStockSymbol("مين اعلى اسهم سيولة في البورصة")).toBeNull();
        expect(fuzzyFindStockSymbol("هات كل التوصيات المفتوحة")).toBeNull();
    });
});
