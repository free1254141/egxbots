import { getCanonicalStockName, CANONICAL_STOCK_NAMES } from "../stock-names";
import { ARABIC_STOCK_MAPPINGS } from "../symbol-aliases";

describe("Canonical Stock Names & Aliases", () => {
    test("correctly maps Egyptian mills and industrial stocks without mix-ups", () => {
        expect(getCanonicalStockName("CEFM").name_ar).toBe("مطاحن مصر الوسطى");
        expect(getCanonicalStockName("EDFM").name_ar).toBe("مطاحن شرق الدلتا");
        expect(getCanonicalStockName("SCFM").name_ar).toBe("مطاحن ومخابز جنوب القاهرة والجيزة");
        expect(getCanonicalStockName("MILS").name_ar).toBe("مطاحن ومخابز شمال القاهرة");
        expect(getCanonicalStockName("AFMC").name_ar).toBe("مطاحن ومخابز الإسكندرية");
        expect(getCanonicalStockName("MBEG").name_ar).toBe("إم بي للهندسة");
        expect(getCanonicalStockName("EGBE").name_ar).toBe("البنك المصري الخليجي");
    });

    test("correctly distinguishes Pharma and Cement stocks", () => {
        expect(getCanonicalStockName("MPCI").name_ar).toBe("ممفيس للأدوية والصناعات الكيماوية");
        expect(getCanonicalStockName("MCQE").name_ar).toBe("مصر للأسمنت - قنا");
        expect(getCanonicalStockName("PHAR").name_ar).toBe("المصرية الدولية للصناعات الدوائية - إيبيكو");
    });

    test("strictly distinguishes TALM (تعليم) from TMGH (طلعت مصطفى)", () => {
        expect(getCanonicalStockName("TALM").name_ar).toBe("تعليم لخدمات الإدارة");
        expect(getCanonicalStockName("TMGH").name_ar).toBe("مجموعة طلعت مصطفى القابضة");
        
        // Alias mapping
        expect(ARABIC_STOCK_MAPPINGS["طلعت"]).toBe("TMGH");
        expect(ARABIC_STOCK_MAPPINGS["سهم طلعت"]).toBe("TMGH");
        expect(ARABIC_STOCK_MAPPINGS["مجموعة طلعت"]).toBe("TMGH");
        expect(ARABIC_STOCK_MAPPINGS["تعليم"]).toBe("TALM");
    });

    test("correctly provides verified names for recent active candidates", () => {
        expect(getCanonicalStockName("SEIG").name_ar).toBe("السعودية المصرية للاستثمار والتمويل");
        expect(getCanonicalStockName("ODIN").name_ar).toBe("أودن للاستثمارات المالية");
        expect(getCanonicalStockName("GTWL").name_ar).toBe("جولدن تكس للأصواف");
        expect(getCanonicalStockName("MASR").name_ar).toBe("مدينة مصر للإسكان والتعمير");
        expect(getCanonicalStockName("RREI").name_ar).toBe("العربية للاستثمار العقاري");
        expect(getCanonicalStockName("MAAL").name_ar).toBe("مرسيليا المصرية الخليجية للاستثمار العقاري");
    });
});
