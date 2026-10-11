/** One numeric representation for prose, tables and financial evidence. */
export function normalizeEvidenceNumbers(text: string): string {
    return text.replace(/[٠-٩]/g, d => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
        .replace(/[۰-۹]/g, d => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
        .replace(/٫/g, ".").replace(/٬/g, "")
        .replace(/[−–—﹣－]/g, "-")
        .replace(/(?<=\d),(?=\d{3}(?:\D|$))/g, "");
}
