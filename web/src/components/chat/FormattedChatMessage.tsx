"use client";

import React, { useEffect, useRef, useState } from "react";
import { parseMarkdownTable, exportTableToExcel } from "@/lib/excelExport";
import { FileSpreadsheet, Download, Check, Sparkles, Copy, Share2, Clock, Zap, Briefcase, Loader2, Crown, Lock, AlertCircle } from "lucide-react";
import StockCard, { StockData } from "./StockCard";
import type { ChatTable } from "@/contexts/ChatContext";
import { sanitizeUiLabel, stripEnvironmentLeak } from "@/lib/ai/sanitizer";
import { getCanonicalStockName } from "@/lib/ai/stock-names";
import { isShariaCompliant } from "@/lib/shariaStocks";

interface FormattedChatMessageProps {
    content: string;
    role: "user" | "assistant" | "system";
    suggestedButtons?: string[];
    onButtonClick?: (text: string) => void;
    showSuggestedButtons?: boolean;
    isStreaming?: boolean;
    tables?: ChatTable[];
    showShareButton?: boolean;
    onShare?: () => void;
    sharing?: boolean;
    latencyMs?: number;
    userQuery?: string;
}

interface RawPipeStock {
    symbol: string;
    score: string;
    val1: string;
    val2: string;
    val3: string;
    val4: string;
    val5: string;
    signal: string;
    days: string;
}

type ContentBlock = 
    | { type: "text"; content: string }
    | { type: "table"; headers: string[]; rows: string[][] }
    | { type: "stock_card"; stock: StockData; rawJson: string; tableData?: { headers: string[]; rows: string[][] } }
    | { type: "stock_cards"; stocks: StockData[]; tableData?: { headers: string[]; rows: string[][] } }
    | { type: "raw_pipe_table"; items: RawPipeStock[] };

export const EGX_STOCKS_METADATA: Record<string, { name: string; sector: string; isShariah?: boolean }> = {
    COMI: { name: "البنك التجاري الدولي", sector: "بنوك", isShariah: false },
    TMGH: { name: "مجموعة طلعت مصطفى", sector: "عقارات", isShariah: true },
    EAST: { name: "الشرقية - إيسترن كومباني", sector: "أغذية ومشروبات وتبغ", isShariah: false },
    SEIG: { name: "السعودية المصرية للاستثمار والتمويل", sector: "استثمار وخدمات مالية", isShariah: false },
    HRHO: { name: "إي إف جي القابضة", sector: "خدمات مالية غير مصرفية", isShariah: false },
    SWDY: { name: "السويدي إليكتريك", sector: "صناعي وهندسي", isShariah: true },
    FWRY: { name: "فوري لتكنولوجيا البنوك", sector: "تكنولوجيا مالية", isShariah: true },
    AMOC: { name: "الإسكندرية للزيوت المعدنية", sector: "طاقة وبترول", isShariah: true },
    EKHO: { name: "القابضة المصرية الكويتية", sector: "استثمار وخدمات مالية", isShariah: true },
    ABUK: { name: "أبو قير للأسمدة", sector: "كيماويات وأسمدة", isShariah: true },
    MFPC: { name: "مصر لإنتاج الأسمدة - موبكو", sector: "كيماويات وأسمدة", isShariah: true },
    ETEL: { name: "المصرية للاتصالات", sector: "اتصالات", isShariah: true },
    JUFO: { name: "جهينة للصناعات الغذائية", sector: "أغذية ومشروبات", isShariah: true },
    DOMT: { name: "دومتي للصناعات الغذائية", sector: "أغذية ومشروبات", isShariah: true },
    SKPC: { name: "سيدي كرير للبتروكيماويات", sector: "كيماويات وبتروكيماويات", isShariah: true },
    ISPH: { name: "ابن سينا فارما", sector: "رعاية صحية وأدوية", isShariah: true },
    GBCO: { name: "جي بي كوربوريشن", sector: "سيارات وتجارة", isShariah: true },
    GBAUTO: { name: "جي بي كوربوريشن", sector: "سيارات وتجارة", isShariah: true },
    HELI: { name: "مصر الجديدة للإسكان", sector: "عقارات", isShariah: true },
    PHDC: { name: "بالم هيلز للتعمير", sector: "عقارات", isShariah: true },
    ACGC: { name: "العربية لحليج الأقطان", sector: "غزل ونسيج", isShariah: true },
    EFID: { name: "إيديتا للصناعات الغذائية", sector: "أغذية ومشروبات", isShariah: true },
    EFIH: { name: "إي فاينانس", sector: "تكنولوجيا مالية", isShariah: true },
    CRST: { name: "كريست مارك", sector: "خدمات واستثمار", isShariah: true },
    EDFM: { name: "مطاحن شرق الدلتا", sector: "أغذية ومطاحن", isShariah: true },
    MILS: { name: "مطاحن ومخابز شمال القاهرة", sector: "أغذية ومطاحن", isShariah: true },
    MBEG: { name: "إم بي للهندسة", sector: "صناعي وهندسي", isShariah: true },
    WCDF: { name: "مطاحن ومخابز وسط وغرب الدلتا", sector: "أغذية ومطاحن", isShariah: true },
    LCSW: { name: "ليسيكو مصر", sector: "مواد بناء وسيراميك", isShariah: true },
    ETRS: { name: "المصرية لخدمات النقل - إيجيترانس", sector: "نقل ولوجستيات", isShariah: true },
    BTFH: { name: "بلتون المالية القابضة", sector: "خدمات مالية غير مصرفية", isShariah: false },
    AFMC: { name: "مطاحن الإسكندرية", sector: "أغذية ومطاحن", isShariah: true },
    CIEB: { name: "بنك كريدي أجريكول مصر", sector: "بنوك", isShariah: false },
    ADIB: { name: "مصرف أبوظبي الإسلامي", sector: "بنوك إسلامية", isShariah: true },
    CCAP: { name: "القلعة للاستشارات المالية", sector: "استثمار وخدمات مالية", isShariah: false },
    KORA: { name: "قرة للطاقة", sector: "طاقة وخدمات هندسية", isShariah: true },
    ORAS: { name: "أوراسكوم كونستراكشون", sector: "مقاولات وتشييد", isShariah: true },
    ORHD: { name: "أوراسكوم للتنمية مصر", sector: "عقارات وسياحة", isShariah: true },
    CICH: { name: "سي آي كابيتال القابضة", sector: "خدمات مالية غير مصرفية", isShariah: false },
    VALU: { name: "فاليو", sector: "تكنولوجيا مالية واستهلاكية", isShariah: false },
    POUL: { name: "القاهرة للدواجن", sector: "أغذية ودواجن", isShariah: true },
    ISMA: { name: "الإسماعيلية مصر للدواجن", sector: "أغذية ودواجن", isShariah: true },
    IRON: { name: "الحديد والصلب المصرية", sector: "تعدين وحديد", isShariah: true },
    MBSC: { name: "مصر بني سويف للأسمنت", sector: "مواد بناء وأسمنت", isShariah: true },
    MPCI: { name: "ممفيس للأدوية والصناعات الكيماوية", sector: "رعاية صحية وأدوية", isShariah: true },
    MCQE: { name: "مصر للأسمنت - قنا", sector: "مواد بناء وأسمنت", isShariah: true },
    DEIN: { name: "دايس للملابس الجاهزة", sector: "ملابس ومنسوجات", isShariah: true },
    CEFM: { name: "مطاحن مصر الوسطى", sector: "أغذية ومطاحن", isShariah: true },
    SCFM: { name: "مطاحن ومخابز جنوب القاهرة والجيزة", sector: "أغذية ومطاحن", isShariah: true },
    PHAR: { name: "المصرية الدولية للأدوية - إيبيكو", sector: "رعاية صحية وأدوية", isShariah: true },
    ODIN: { name: "أودن للاستثمارات المالية", sector: "استثمار وخدمات مالية", isShariah: false },
    TALM: { name: "تعليم لخدمات الإدارة", sector: "خدمات تعليمية", isShariah: true },
    GTWL: { name: "جولدن تكس للأصواف", sector: "غزل ونسيج", isShariah: true },
    MASR: { name: "مدينة مصر للإسكان والتعمير", sector: "عقارات", isShariah: true },
    RREI: { name: "العربية للاستثمار العقاري", sector: "عقارات", isShariah: true },
    MAAL: { name: "مرسيليا المصرية الخليجية للاستثمار", sector: "عقارات وسياحة", isShariah: true },
    EGBE: { name: "البنك المصري الخليجي", sector: "بنوك", isShariah: false },
};

function parseNum(val: string | undefined): number | undefined {
    if (!val) return undefined;
    const str = String(val).trim();
    if (!str || str === "-" || str === "—" || str === "N/A" || str === "null") return undefined;
    // CRITICAL: Guard against dates (e.g. 30-10-2026 or 2026-10-30 or 30/10/2026)
    // parseFloat("30-10-2026") evaluates to 30, which falsely becomes 30.00 EGP price!
    if (/^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}/.test(str)) {
        return undefined;
    }
    const cleaned = str.replace(/[^\d.-]/g, "");
    if (!cleaned) return undefined;
    const n = parseFloat(cleaned);
    return isNaN(n) ? undefined : n;
}

export function tryParseRecommendationsTable(headers: string[], rows: string[][]): StockData[] | null {
    if (!headers || headers.length < 3 || !rows || rows.length === 0) return null;

    const findIdx = (pattern: RegExp, exclude?: RegExp) => {
        for (let i = 0; i < headers.length; i++) {
            if (pattern.test(headers[i])) {
                if (exclude && exclude.test(headers[i])) continue;
                return i;
            }
        }
        return -1;
    };

    const symbolIdx = findIdx(/السهم|الرمز|الكود/i);
    // CRITICAL: entryIdx must NOT match "تاريخ الدخول"
    let entryIdx = findIdx(/سعر الدخول|منطقة الدخول/i);
    if (entryIdx === -1) {
        entryIdx = findIdx(/الدخول/i, /تاريخ/i);
    }
    const currentPriceIdx = findIdx(/السعر الحالي|سعر الإغلاق|الإغلاق/i);
    const target1Idx = findIdx(/المستهدف\s*1?|الهدف\s*1?|تارجت\s*1?|المستهدف الأول/i);
    const target2Idx = findIdx(/المستهدف\s*2|الهدف\s*2|تارجت\s*2|المستهدف الثاني/i);
    const stopLossIdx = findIdx(/وقف الخسارة|الوقف|Stop\s*Loss/i);
    const returnIdx = findIdx(/العائد|التغير|الربح/i);
    const signalTypeIdx = findIdx(/نوع الإشارة|الإشارة|النوع/i);
    const timeframeIdx = findIdx(/الأفق|المدى|الفريم/i);
    const rsiIdx = findIdx(/RSI/i);
    const rvolIdx = findIdx(/الحجم النسبي|السيولة/i);
    const wyckoffIdx = findIdx(/وايكوف|التجميع|مرحلة/i);

    if (symbolIdx === -1 || entryIdx === -1 || (target1Idx === -1 && stopLossIdx === -1)) {
        return null;
    }

    const stocks: StockData[] = [];
    for (const row of rows) {
        if (!row || row.length <= symbolIdx) continue;
        const rawSymbol = row[symbolIdx]?.trim() || "";
        if (!rawSymbol || rawSymbol === "-" || rawSymbol.startsWith("---") || /المؤشر|المستوى/i.test(rawSymbol)) continue;

        const isExplicitShariah = rawSymbol.includes("شرعي") || rawSymbol.includes("EGX33") || rawSymbol.includes("شريعة");
        
        // Clean symbol: strip bold asterisks **CRST** -> CRST, badges, etc.
        const cleanSymbol = rawSymbol
            .replace(/\*/g, "")
            .replace(/[✅🚀⚡🧲]/g, "")
            .replace(/\(شرعي\)|\(شريعة\)|\(.*?\)|شرعي/g, "")
            .trim()
            .toUpperCase();

        const entry = parseNum(row[entryIdx]);
        const currentPrice = currentPriceIdx !== -1 ? parseNum(row[currentPriceIdx]) : undefined;
        const target1 = target1Idx !== -1 ? parseNum(row[target1Idx]) : undefined;
        const target2 = target2Idx !== -1 ? parseNum(row[target2Idx]) : undefined;
        const stopLoss = stopLossIdx !== -1 ? parseNum(row[stopLossIdx]) : undefined;
        
        let changePct: number | undefined;
        if (returnIdx !== -1 && row[returnIdx]) {
            changePct = parseNum(row[returnIdx]);
        }

        const rsiVal = rsiIdx !== -1 ? parseNum(row[rsiIdx]) : undefined;
        const rvolVal = rvolIdx !== -1 ? parseNum(row[rvolIdx]) : undefined;
        const wyckoffVal = wyckoffIdx !== -1 && row[wyckoffIdx] ? row[wyckoffIdx].replace(/\*/g, "").trim() : undefined;

        const signalType = signalTypeIdx !== -1 && row[signalTypeIdx] ? row[signalTypeIdx].replace(/\*/g, "").trim() : "فرصة مضاربة";
        const timeframe = timeframeIdx !== -1 && row[timeframeIdx] ? row[timeframeIdx].replace(/\*/g, "").trim() : "1-3 جلسات";

        const canonical = getCanonicalStockName(cleanSymbol);
        const meta = EGX_STOCKS_METADATA[cleanSymbol] || {
            name: canonical.name_ar,
            sector: canonical.sector || "سوق الأسهم المصرية",
            isShariah: isShariaCompliant(cleanSymbol)
        };

        if (cleanSymbol && (entry !== undefined || target1 !== undefined || stopLoss !== undefined || currentPrice !== undefined)) {
            const finalPrice = currentPrice !== undefined && currentPrice > 0 ? currentPrice : (entry || 0);
            stocks.push({
                symbol: cleanSymbol,
                name: meta?.name || cleanSymbol,
                sector: meta?.sector,
                price: finalPrice,
                changePercent: changePct !== undefined ? changePct : 0,
                entryRange: entry ? `${entry.toFixed(2)} ج.م` : undefined,
                target1,
                target2,
                stopLoss,
                recommendation: signalType || "فرصة مضاربة",
                signal: signalType || "دخول مؤكد",
                signalType,
                rsi: rsiVal,
                rVol: rvolVal,
                wyckoffPhase: wyckoffVal,
                isShariah: isExplicitShariah || meta?.isShariah,
                timeframe
            });
        }
    }

    return stocks.length > 0 ? stocks : null;
}

export function tryParseAnalysisTable(headers: string[], rows: string[][], recentText: string): StockData | null {
    if (!rows || rows.length < 2) return null;

    let hasClose = false;
    let hasSupport = false;
    let hasResistance = false;
    let hasRsi = false;
    let hasEma = false;

    let price: number | undefined;
    let support1: number | undefined;
    let support2: number | undefined;
    let resistance1: number | undefined;
    let resistance2: number | undefined;
    let rsi: number | undefined;
    let macdVal: string | undefined;
    let volRatio: number | undefined;
    let pe: number | undefined;
    let eps: number | undefined;
    let marketCap: string | undefined;
    let wyckoffPhase: string | undefined;
    let ema50: number | undefined;
    let ema200: number | undefined;
    let changePct: number | undefined;

    for (const row of rows) {
        if (!row || row.length < 2) continue;
        const key = row[0]?.trim() || "";
        const val = row[1]?.trim() || "";
        const extraVal = row[2]?.trim() || "";

        if (/الإغلاق الحالي|آخر سعر|سعر الإغلاق|إغلاق/i.test(key)) {
            hasClose = true;
            price = parseNum(val);
            if (changePct === undefined && extraVal) {
                const rowChange = parseNum(extraVal);
                if (rowChange !== undefined && /%/.test(extraVal)) {
                    changePct = rowChange;
                }
            }
        } else if (/الدعم الأول|دعم أول|الدعم 1/i.test(key)) {
            hasSupport = true;
            support1 = parseNum(val);
        } else if (/الدعم الثاني|دعم ثان|الدعم 2/i.test(key)) {
            support2 = parseNum(val);
        } else if (/المقاومة الأولى|مقاومة أولى|المقاومة 1/i.test(key)) {
            hasResistance = true;
            resistance1 = parseNum(val);
        } else if (/المقاومة الثانية|مقاومة ثانية|المقاومة 2/i.test(key)) {
            resistance2 = parseNum(val);
        } else if (/RSI/i.test(key)) {
            hasRsi = true;
            rsi = parseNum(val);
        } else if (/MACD/i.test(key)) {
            macdVal = val;
        } else if (/الحجم النسبي/i.test(key)) {
            volRatio = parseNum(val);
        } else if (/مضاعف الربحية|P\/E/i.test(key)) {
            pe = parseNum(val);
        } else if (/ربحية السهم|EPS/i.test(key)) {
            eps = parseNum(val);
        } else if (/القيمة السوقية/i.test(key)) {
            marketCap = val;
        } else if (/مرحلة وايكوف/i.test(key)) {
            wyckoffPhase = val;
        } else if (/EMA\s*50/i.test(key)) {
            hasEma = true;
            ema50 = parseNum(val);
        } else if (/EMA\s*200/i.test(key)) {
            hasEma = true;
            ema200 = parseNum(val);
        } else if (/EMA/i.test(key)) {
            hasEma = true;
        }
    }

    const matchCount = (hasClose ? 1 : 0) + (hasSupport ? 1 : 0) + (hasResistance ? 1 : 0) + (hasRsi ? 1 : 0) + (hasEma ? 1 : 0);
    if (matchCount < 1 && !rsi) {
        return null;
    }

    let symbol = "";
    let name = "";
    let recommendation = "";
    let isShariah = false;

    // Clean asterisks from text for reliable regex matching
    const cleanRecent = recentText.replace(/\*/g, "");

    // Extract symbol and name from recent preceding text
    const symbolMatch = cleanRecent.match(/(?:تحليل سهم|سهم|شركة)?\s*([^\(\n\r#\|]{2,40}?)\s*[\(\[]\s*([A-Za-z0-9_]{2,8})\s*[\)\]]/i)
                     || cleanRecent.match(/###\s*📊?\s*(?:تحليل سهم|سهم)?\s*([^\(\n\r#\|]+?)\s*[\(\[]\s*([A-Za-z0-9_]{2,8})\s*[\)\]]/i)
                     || cleanRecent.match(/(?:تحليل سهم|سهم|سهمي)\s+([A-Za-z0-9_]{2,8})/i)
                     || cleanRecent.match(/[\(\[]\s*([A-Za-z0-9_]{2,8})\s*[\)\]]/);

    if (symbolMatch) {
        if (symbolMatch[2]) {
            name = symbolMatch[1].replace(/###|📊/g, "").trim();
            symbol = symbolMatch[2].trim().toUpperCase();
        } else {
            symbol = symbolMatch[1].trim().toUpperCase();
            name = symbol;
        }
    }

    // Fallback: check if any KNOWN_STOCK_SYMBOLS appears in recent text
    if (!symbol) {
        for (const s of KNOWN_STOCK_SYMBOLS) {
            const regex = new RegExp(`\\b${s}\\b`, "i");
            if (regex.test(cleanRecent)) {
                symbol = s;
                break;
            }
        }
    }

    if (!symbol) return null;

    // Price extraction from preceding text if table didn't have it (e.g. ATQA, FWRY)
    if (!price || price === 0) {
        const textPriceMatch = cleanRecent.match(/(?:السعر الأخير|آخر إغلاق متاح|آخر سعر|سعر الإغلاق|إغلاق):\s*([+-]?[\d\.]+)/i)
                            || cleanRecent.match(/([+-]?[\d\.]+)\s*ج\.م\s*(?:\(جلسة|\(تغير)/i)
                            || cleanRecent.match(/(?:سعر السهم|سعر|الإغلاق)\s*[:=]?\s*([+-]?[\d\.]+)\s*ج\.م/i);
        if (textPriceMatch) {
            price = parseNum(textPriceMatch[1]);
        }
    }

    // Price change percentage from text
    if (changePct === undefined) {
        const changeMatch = cleanRecent.match(/(?:تغير الجلسة|التغير):\s*([+-]?[\d\.]+)\s*%/i)
                         || cleanRecent.match(/([+-]?[\d\.]+)\s*%\s*بتاريخ/i)
                         || cleanRecent.match(/،\s*([+-]?[\d\.]+)\s*%\s*\)/i)
                         || cleanRecent.match(/\(\s*([+-]?[\d\.]+)\s*%\s*\)/i);
        if (changeMatch) {
            changePct = parseFloat(changeMatch[1]);
        }
    }

    // Evaluation / Recommendation
    const evalMatch = cleanRecent.match(/التقييم الفني العام:\s*([^\n\r\|]+)/i);
    if (evalMatch) {
        recommendation = evalMatch[1].trim();
    }

    // Shariah check
    if (/متوافق مع الشريعة|EGX\s*33|شريعة/i.test(cleanRecent)) {
        if (!/غير متوافق|خارج EGX\s*33/i.test(cleanRecent)) {
            isShariah = true;
        }
    }

    const canonical = getCanonicalStockName(symbol);
    const meta = EGX_STOCKS_METADATA[symbol] || {
        name: canonical.name_ar,
        sector: canonical.sector || "سوق الأسهم المصرية",
        isShariah: isShariaCompliant(symbol)
    };

    return {
        symbol,
        name: name || meta?.name || symbol,
        sector: meta?.sector,
        price: price || 0,
        changePercent: changePct !== undefined ? changePct : 0,
        entryRange: support1 ? `${support1.toFixed(2)} ج.م` : undefined,
        support1,
        support2,
        resistance1,
        resistance2,
        target1: resistance1,
        target2: resistance2,
        stopLoss: support2 || (support1 ? Number((support1 * 0.98).toFixed(2)) : undefined),
        recommendation: recommendation || wyckoffPhase || "حيادي للمراقبة",
        signal: recommendation || "مراقبة فنية",
        rsi,
        macdSignal: macdVal,
        volumeRatio: volRatio,
        rVol: volRatio,
        peRatio: pe,
        eps,
        marketCap,
        wyckoffPhase,
        ema50,
        ema200,
        isShariah: isShariah || meta?.isShariah
    };
}

const KNOWN_STOCK_SYMBOLS = new Set([
    "COMI", "EAST", "HRHO", "SWDY", "FWRY", "TMGH", "AMOC", "EKHO", "ABUK", "MFPC",
    "ORAS", "CICH", "ETEL", "JUFO", "DOMT", "SKPC", "ISPH", "ORWE", "GBAUTO", "GBCO",
    "HELI", "PHDC", "EGX30", "EGX70", "EGX100", "USDEGP", "AALR", "ACAMD", "ACAP",
    "ADCI", "ADPC", "AFMC", "AIH", "AJWA", "ALUM", "APPC", "ARAB", "AREH", "ARVA",
    "ATQA", "AXPH", "BIOC", "BTFH", "CIEB", "CNFN", "COPR", "CPCI", "CRST", "EEII",
    "EFID", "EFIH", "EGAL", "EGBE", "EGCH", "EGREF", "EGSA", "EGTS", "EHDR", "EITP",
    "ELKA", "ELSH", "EOSB", "ETRS", "FAIT", "FERC", "GDWA", "GGCC", "GGRN", "GMCI",
    "GOUR", "GSSC", "ICFC", "IDRE", "INFI", "IRON", "ISMA", "KABO", "KASABF", "KRDI",
    "KZPC", "LUTS", "MASR", "MBSC", "MCQE", "MENA", "MFSC", "MICH", "MILS", "MOIL",
    "MOSC", "MPCO", "MTIE", "NEDA", "NHPS", "NINH", "PHTV", "POUL", "PRDC", "RACC",
    "RTVC", "RUBX", "SAUD", "SCEM", "SCTS", "SEIG", "SIPC", "SNFC", "SPIN", "TANM",
    "TRTO", "TWSA", "UEFM", "UNIT", "VALU", "VLMRA", "WATP"
]);

function parseStockJson(text: string): StockData[] | null {
    try {
        const trimmed = text.trim();
        if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
        
        const parsed = JSON.parse(trimmed);
        
        const isStockObj = (obj: any): obj is StockData => {
            if (!obj || typeof obj !== "object") return false;
            const symbol = obj.symbol || obj.ticker;
            if (!symbol || typeof symbol !== "string") return false;
            
            if (obj.type && ["stock", "stock_card", "stock_data", "stock_payload", "recommendation", "signal", "opportunity", "stock_cards"].includes(obj.type)) {
                return true;
            }
            
            const hasPrice = obj.price !== undefined;
            const hasRsi = obj.rsi !== undefined;
            const hasMacd = obj.macdSignal !== undefined || obj.macd_signal !== undefined || obj.macd !== undefined;
            const hasChange = obj.changePercent !== undefined || obj.change_percent !== undefined || obj.change !== undefined;
            
            const hasEntry = obj.entryRange !== undefined || obj.entry_range !== undefined || obj.entryPrice !== undefined || obj.entry_price !== undefined;
            const hasTarget = obj.target1 !== undefined || obj.target_1 !== undefined || obj.target !== undefined;
            return hasPrice || hasRsi || hasMacd || hasChange || hasEntry || hasTarget;
        };

        if (Array.isArray(parsed)) {
            const validStocks = parsed.filter(isStockObj);
            return validStocks.length > 0 ? validStocks : null;
        } else if (isStockObj(parsed)) {
            return [parsed];
        } else if (parsed && typeof parsed === "object") {
            const list = parsed.stocks || parsed.recommendations || parsed.signals || parsed.opportunities || parsed.items;
            if (Array.isArray(list)) {
                const validStocks = list.filter(isStockObj);
                return validStocks.length > 0 ? validStocks : null;
            }
        }

        return null;
    } catch {
        return null;
    }
}

function parseRawPipeLine(line: string): RawPipeStock[] | null {
    if (!line.includes("|")) return null;
    const trimmed = line.trim();
    if (trimmed.startsWith("|")) return null;
    if (!/(strong_?accumulation|strong_?distribution|accumulation|distribution)/i.test(line)) return null;
    const pipes = line.split("|").map(s => s.trim());
    if (pipes.length < 8) return null;

    const items: RawPipeStock[] = [];
    let i = 0;
    
    let currentHeader = pipes[0];
    
    try {
        while (i + 7 < pipes.length) {
            const val1 = pipes[i + 1];
            const val2 = pipes[i + 2];
            const val3 = pipes[i + 3];
            const val4 = pipes[i + 4];
            const val5 = pipes[i + 5];
            const signal = pipes[i + 6];
            const nextPart = pipes[i + 7];
            
            const headerMatch = currentHeader.match(/([A-Z0-9]{2,6})\s+([\d.]+)/i) || currentHeader.match(/([A-Z0-9]{2,6})/i);
            const symbol = headerMatch ? headerMatch[1].toUpperCase() : "STOCK";
            const score = headerMatch && headerMatch[2] ? headerMatch[2] : "N/A";
            const validSignal = /(strong\s+accumulation|strong\s+distribution|accumulation|distribution)/i.test(signal.replace(/_/g, " "));
            if (!/^[A-Z0-9]{2,10}$/.test(symbol) || !validSignal || !Number.isFinite(Number(val2)) || !Number.isFinite(Number(val4))) {
                return null;
            }
            
            const nextMatch = nextPart.match(/^([\d.]+)\s+(.*)$/);
            let days = nextPart;
            let nextHeader = "";
            if (nextMatch) {
                days = nextMatch[1];
                nextHeader = nextMatch[2].trim();
            }
            
            items.push({
                symbol,
                score,
                val1,
                val2,
                val3,
                val4,
                val5,
                signal: signal.replace(/_/g, " "),
                days
            });
            
            currentHeader = nextHeader;
            i += 7;
        }
    } catch (e) {
        console.warn("Failed to parse raw pipe line:", e);
    }
    
    return items.length > 0 ? items : null;
}

function normalizeTableText(content: string): string {
    if (!content.includes("|")) return content;
    const lines = content.split("\n");
    const newLines: string[] = [];
    const ignoredHeaders = new Set([
        "RSI", "MACD", "EMA", "SMA", "EGX", "AI", "KING", "VOL",
        "P/E", "ROE", "ROA", "EPS", "PB", "DY", "TICKER", "STOCK", "EGP"
    ]);

    for (const line of lines) {
        const trimmed = line.trim();
        // Detect collapsed multi-row single-line tables (where row boundaries were stripped or missing)
        if (trimmed.startsWith("|") && (trimmed.match(/\|/g) || []).length >= 10) {
            // First repair cells where two values got merged with 2+ spaces, e.g. "EGX AI  **ACAMD**" or "0.463  **ACAP**"
            const repairedLine = line.replace(/([^\n|]+?)\s{2,}(\*{0,2}[A-Z0-9]{2,10}\*{0,2})(?=\s*\|)/g, "$1 | $2");
            const pipeCount = (repairedLine.match(/\|/g) || []).length;

            if (pipeCount >= 15) {
                const cells = repairedLine.split("|").map(c => c.trim()).filter(Boolean);
                
                // Find where the first stock ticker or second-row identifier starts
                const firstRowIdx = cells.findIndex((cell, idx) => {
                    if (idx === 0) return false;
                    const clean = cell.replace(/\*/g, "").toUpperCase();
                    return /^[A-Z0-9]{2,6}$/.test(clean) && !ignoredHeaders.has(clean);
                });

                if (firstRowIdx >= 3 && cells.length >= firstRowIdx * 2) {
                    const colCount = firstRowIdx;
                    const headers = cells.slice(0, colCount);
                    newLines.push("| " + headers.join(" | ") + " |");
                    newLines.push("| " + headers.map(() => "---").join(" | ") + " |");
                    for (let i = colCount; i < cells.length; i += colCount) {
                        const row = cells.slice(i, i + colCount);
                        if (row.length > 0) {
                            newLines.push("| " + row.join(" | ") + " |");
                        }
                    }
                    continue;
                }
            }
            newLines.push(repairedLine);
        } else {
            newLines.push(line);
        }
    }

    return newLines.join("\n");
}

function parseContentBlocks(content: string): ContentBlock[] {
    const normalizedContent = normalizeTableText(content);
    const blocks: ContentBlock[] = [];
    const lines = normalizedContent.split("\n");
    let currentTextLines: string[] = [];
    let currentTableLines: string[] = [];
    let currentCodeBlockLines: string[] = [];
    let inTable = false;
    let inCodeBlock = false;
    let codeBlockLang = "";

    const flushText = () => {
        if (currentTextLines.length > 0) {
            blocks.push({ type: "text", content: currentTextLines.join("\n") });
            currentTextLines = [];
        }
    };

    const flushTable = () => {
        if (currentTableLines.length > 0) {
            const tableLines = currentTableLines.map(l => l.trim()).filter(Boolean);
            const contentLines = tableLines.filter(line => !/^\|[\s:\-|\+]+\|$/.test(line));
            
            if (contentLines.length >= 2) {
                const headers = contentLines[0]
                    .split("|")
                    .slice(1, -1)
                    .map(cell => cell.trim());
                const rows = contentLines.slice(1).map(line => {
                    const cells = line
                        .split("|")
                        .slice(1, -1)
                        .map(cell => cell.trim());
                    // Pad with "-" if row has fewer cells than headers
                    while (cells.length < headers.length) {
                        cells.push("-");
                    }
                    return cells;
                });
                if (headers.length > 0 && rows.length > 0) {
                    // 1. Try recommendations / opportunities table first
                    const recStocks = tryParseRecommendationsTable(headers, rows);
                    if (recStocks && recStocks.length > 0) {
                        flushText();
                        blocks.push({ 
                            type: "stock_cards", 
                            stocks: recStocks,
                            tableData: { headers, rows }
                        });
                        currentTableLines = [];
                        return;
                    }

                    // 2. Try single/comparative stock analysis table
                    const recentText = currentTextLines.join("\n") + "\n" + (blocks.length > 0 && blocks[blocks.length - 1].type === "text" ? (blocks[blocks.length - 1] as any).content : "");
                    const analyzedStock = tryParseAnalysisTable(headers, rows, recentText);
                    if (analyzedStock) {
                        flushText();
                        blocks.push({ 
                            type: "stock_card", 
                            stock: analyzedStock, 
                            rawJson: "",
                            tableData: { headers, rows }
                        });
                        currentTableLines = [];
                        return;
                    }

                    blocks.push({ type: "table", headers, rows });
                } else {
                    currentTextLines.push(...currentTableLines);
                }
            } else {
                currentTextLines.push(...currentTableLines);
            }
            currentTableLines = [];
        }
    };

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        // Code block start/end
        if (trimmed.startsWith("```")) {
            if (inCodeBlock) {
                inCodeBlock = false;
                const codeContent = currentCodeBlockLines.join("\n");
                const stocks = parseStockJson(codeContent);
                if (stocks && stocks.length > 0) {
                    flushText();
                    stocks.forEach(stock => {
                        blocks.push({ type: "stock_card", stock, rawJson: codeContent });
                    });
                } else {
                    currentTextLines.push("```" + codeBlockLang);
                    currentTextLines.push(...currentCodeBlockLines);
                    currentTextLines.push("```");
                }
                currentCodeBlockLines = [];
                codeBlockLang = "";
                continue;
            } else {
                if (inTable) {
                    flushTable();
                    inTable = false;
                }
                flushText();
                inCodeBlock = true;
                codeBlockLang = trimmed.substring(3).trim();
                currentCodeBlockLines = [];
                continue;
            }
        }

        if (inCodeBlock) {
            currentCodeBlockLines.push(line);
            continue;
        }

        // Table line detection: starts with "|" and has at least two pipes
        const isTableLine = trimmed.startsWith("|") && (trimmed.endsWith("|") || (trimmed.match(/\|/g) || []).length >= 2);

        if (isTableLine) {
            if (!inTable) {
                flushText();
                inTable = true;
            }
            const normalizedRow = trimmed.endsWith("|") ? trimmed : `${trimmed} |`;
            currentTableLines.push(normalizedRow);
        } else {
            // Check if this is an empty line between table rows
            if (inTable && trimmed === "") {
                let nextIsTable = false;
                for (let k = i + 1; k < lines.length; k++) {
                    const nextTrim = lines[k].trim();
                    if (nextTrim === "") continue;
                    if (nextTrim.startsWith("|") && (nextTrim.endsWith("|") || (nextTrim.match(/\|/g) || []).length >= 2)) {
                        nextIsTable = true;
                    }
                    break;
                }
                if (nextIsTable) {
                    // Do not flush table on blank line between rows
                    continue;
                }
            }

            if (inTable) {
                flushTable();
                inTable = false;
            }
            const rawPipeItems = parseRawPipeLine(line);
            if (rawPipeItems) {
                flushText();
                blocks.push({ type: "raw_pipe_table", items: rawPipeItems });
            } else {
                currentTextLines.push(line);
            }
        }
    }

    if (inCodeBlock) {
        const codeContent = currentCodeBlockLines.join("\n");
        const stocks = parseStockJson(codeContent);
        if (stocks && stocks.length > 0) {
            flushText();
            stocks.forEach(stock => {
                blocks.push({ type: "stock_card", stock, rawJson: codeContent });
            });
        } else {
            currentTextLines.push("```" + codeBlockLang);
            currentTextLines.push(...currentCodeBlockLines);
        }
    } else if (inTable) {
        flushTable();
    }

    flushText();

    // Inline JSON scan in text blocks
    const finalBlocks: ContentBlock[] = [];
    for (const b of blocks) {
        if (b.type === "text") {
            const jsonRegex = /\{[\s\S]*?\}/g;
            let lastIndex = 0;
            let match: RegExpExecArray | null;
            let textAdded = false;

            while ((match = jsonRegex.exec(b.content)) !== null) {
                const jsonCandidate = match[0];
                const stocks = parseStockJson(jsonCandidate);
                if (stocks && stocks.length > 0) {
                    const prefix = b.content.substring(lastIndex, match.index).trim();
                    if (prefix) {
                        finalBlocks.push({ type: "text", content: prefix });
                    }
                    stocks.forEach(stock => {
                        finalBlocks.push({ type: "stock_card", stock, rawJson: jsonCandidate });
                    });
                    lastIndex = match.index + jsonCandidate.length;
                    textAdded = true;
                }
            }

            if (textAdded) {
                const suffix = b.content.substring(lastIndex).trim();
                if (suffix) {
                    finalBlocks.push({ type: "text", content: suffix });
                }
            } else {
                finalBlocks.push(b);
            }
        } else {
            finalBlocks.push(b);
        }
    }

    // Consolidate consecutive stock_card blocks into stock_cards grid/carousel
    const consolidatedBlocks: ContentBlock[] = [];
    for (const b of finalBlocks) {
        if (b.type === "stock_card") {
            const last = consolidatedBlocks[consolidatedBlocks.length - 1];
            if (last && last.type === "stock_cards") {
                last.stocks.push(b.stock);
            } else {
                consolidatedBlocks.push({ type: "stock_cards", stocks: [b.stock], tableData: b.tableData });
            }
        } else {
            consolidatedBlocks.push(b);
        }
    }

    return consolidatedBlocks;
}

function renderTableCell(cellText: string) {
    const raw = String(cellText ?? "").trim();
    if (!raw || raw === "-" || raw === "—" || raw === "N/A") {
        return <span className="text-zinc-400 dark:text-zinc-500 font-mono">—</span>;
    }

    const clean = raw.replace(/\*\*/g, "").trim();

    // Check for negative return/loss
    const isNegative = /^[-−–]\s*\d/.test(clean) || /\(\s*[-−–]\s*\d/.test(clean) || clean.includes("🔴") || clean.includes("خسارة");
    if (isNegative) {
        return (
            <span className="inline-flex items-center font-mono font-bold text-[11px] sm:text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 dark:bg-rose-500/15 px-1.5 py-0.5 rounded dir-ltr tabular-nums">
                {clean}
            </span>
        );
    }

    // Check for positive return/gain
    const isPositive = /^\+\s*\d/.test(clean) || /\(\s*\+\s*\d/.test(clean) || clean.includes("🟢") || clean.includes("ربح");
    if (isPositive) {
        return (
            <span className="inline-flex items-center font-mono font-bold text-[11px] sm:text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 dark:bg-emerald-500/15 px-1.5 py-0.5 rounded dir-ltr tabular-nums">
                {clean}
            </span>
        );
    }

    // Numbers / Percentages / Decimals / Currency
    const isPureNumber = /^[\d,]+(?:\.\d+)?(?:\s*(?:ج\.م|EGP|جنيه|%|٪))?$/.test(clean);
    if (isPureNumber) {
        return (
            <span className="font-mono text-[11px] sm:text-xs tabular-nums text-zinc-900 dark:text-zinc-100 font-semibold dir-ltr">
                {clean}
            </span>
        );
    }

    // Check for stock ticker
    const isTicker = /^[A-Za-z]{2,6}$|^[A-Za-z]+[0-9]+[A-Za-z]*$/.test(clean) && !/^(RSI|MACD|EMA|SMA|EGX|AI|KING|VOL|EGP|BUY|SELL|HOLD)$/i.test(clean);
    if (isTicker) {
        return (
            <span className="inline-flex items-center px-2 py-0.5 rounded-md font-mono font-black text-[11px] sm:text-xs bg-zinc-100 dark:bg-black text-zinc-950 dark:text-white border border-zinc-200 dark:border-white/30 shadow-sm">
                {clean.toUpperCase()}
            </span>
        );
    }

    // General text (check if was bold)
    const wasBold = raw.startsWith("**") && raw.endsWith("**");
    return (
        <span className={`text-[11px] sm:text-xs text-zinc-800 dark:text-zinc-200 ${wasBold ? "font-bold" : "font-medium"}`}>
            {clean}
        </span>
    );
}

function ExportableTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
    const [copied, setCopied] = useState(false);
    return (
        <div className="my-3.5 border border-zinc-200 dark:border-white/20 rounded-xl overflow-hidden bg-white dark:bg-black shadow-md max-w-full">
            <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 bg-gradient-to-r from-zinc-50 to-zinc-100 dark:from-black dark:to-zinc-950 border-b border-zinc-200 dark:border-white/20 min-w-0">
                <div className="flex items-center gap-2">
                    <div className="p-1 rounded-md bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                        <FileSpreadsheet className="w-4 h-4" />
                    </div>
                    <span className="text-xs font-black text-zinc-900 dark:text-zinc-100">
                        جدول البيانات والتحليل
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-zinc-200 dark:bg-black text-zinc-600 dark:text-zinc-200 dark:border dark:border-white/20 font-bold">
                        {rows.length} {rows.length === 1 ? "صف" : rows.length === 2 ? "صفين" : rows.length <= 10 ? "صفوف" : "صف"}
                    </span>
                </div>
                <button
                    onClick={() => {
                        exportTableToExcel(headers, rows);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                    }}
                    className="flex items-center gap-1.5 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-lg transition-all shadow-sm active:scale-95 cursor-pointer"
                    title="تصدير الجدول كملف Excel / CSV"
                >
                    {copied ? <Check className="w-3.5 h-3.5" /> : <Download className="w-3.5 h-3.5" />}
                    <span>{copied ? "تم التحميل!" : "تصدير لإكسيل (Excel)"}</span>
                </button>
            </div>

            <div className="w-full max-w-full overflow-x-auto scrollbar-thin">
                <table className="w-full text-right border-collapse text-xs">
                    <thead>
                        <tr className="bg-zinc-100/90 dark:bg-black text-zinc-900 dark:text-white border-b border-zinc-200 dark:border-white/20">
                            {headers.map((h, i) => (
                                <th
                                    key={i}
                                    className="px-3 py-2.5 text-[11px] sm:text-xs font-extrabold whitespace-nowrap text-zinc-700 dark:text-zinc-200 border-l border-zinc-200/80 dark:border-white/15 last:border-l-0"
                                >
                                    {h.replace(/\*\*/g, "").trim()}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-200/70 dark:divide-white/10">
                        {rows.map((row, rIdx) => (
                            <tr
                                key={rIdx}
                                className="even:bg-zinc-50/60 dark:even:bg-zinc-950/70 hover:bg-amber-500/5 dark:hover:bg-zinc-900/60 transition-colors"
                            >
                                {row.map((cell, cIdx) => (
                                    <td
                                        key={cIdx}
                                        className="px-3 py-2 text-[11px] sm:text-xs whitespace-nowrap border-l border-zinc-200/60 dark:border-white/10 last:border-l-0"
                                    >
                                        {renderTableCell(cell)}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export function FormattedChatMessage({
    content,
    role,
    suggestedButtons,
    onButtonClick,
    showSuggestedButtons = true,
    isStreaming = false,
    tables = [],
    showShareButton = false,
    onShare,
    sharing = false,
    latencyMs,
    userQuery
}: FormattedChatMessageProps) {
    content = stripEnvironmentLeak(sanitizeUiLabel(content));
    suggestedButtons = suggestedButtons?.map(button => stripEnvironmentLeak(sanitizeUiLabel(button))).filter(Boolean);
    if (/environment_details|Current time:|Working directory:|Workspace root folder:/i.test(content)) content = "";
    const [copiedText, setCopiedText] = useState(false);
    const [savingToPortfolio, setSavingToPortfolio] = useState(false);
    const [portfolioFeedback, setPortfolioFeedback] = useState<{
        ok: boolean;
        message: string;
        isQuotaReached?: boolean;
        requiresAuth?: boolean;
        stocks?: Array<{ symbol: string; quantity: number; price: number | null }>;
    } | null>(null);

    const handleSaveToPortfolio = async () => {
        if (savingToPortfolio || !content) return;
        setSavingToPortfolio(true);
        setPortfolioFeedback(null);
        try {
            const res = await fetch("/api/portfolio", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "extract_and_save", text: content, userQuery: userQuery || undefined, suggestedButtons: suggestedButtons || undefined }),
            });
            const data = await res.json();
            if (res.status === 401 || data.requiresAuth) {
                setPortfolioFeedback({
                    ok: false,
                    requiresAuth: true,
                    message: data.message || "يجب تسجيل الدخول أولاً لإضافة الأسهم إلى محفظتك الشخصية.",
                });
            } else {
                setPortfolioFeedback(data);
            }
        } catch {
            setPortfolioFeedback({
                ok: false,
                message: "تعذر الاتصال بالسيرفر لحفظ الأسهم. يرجى المحاولة مرة أخرى.",
            });
        } finally {
            setSavingToPortfolio(false);
        }
    };
    const mermaidContainerRef = useRef<HTMLDivElement>(null);

    const mermaidMatch = !isStreaming ? content.match(/```mermaid\s+([\s\S]*?)```/g) : null;
    const mermaidCode = mermaidMatch ? mermaidMatch[1].trim() : null;

    useEffect(() => {
        if (!isStreaming && mermaidCode && mermaidContainerRef.current) {
            const isDark = document.documentElement.classList.contains("dark");
            import("mermaid").then((mermaid) => {
                mermaid.default.initialize({
                    startOnLoad: false,
                    theme: isDark ? "dark" : "default",
                    securityLevel: "loose",
                });
                const id = "mermaid-" + Math.random().toString(36).substring(2, 9);
                mermaid.default.render(id, mermaidCode).then(({ svg }) => {
                    if (mermaidContainerRef.current) {
                        mermaidContainerRef.current.innerHTML = svg;
                    }
                }).catch((err) => {
                    console.error("Mermaid Render Error:", err);
                });
            });
        }
    }, [mermaidCode, isStreaming]);

    if (role === "user") {
        return (
            <div className="space-y-1 text-right" dir="rtl">
                <div className="dir-auto whitespace-pre-wrap text-zinc-900 dark:text-zinc-100 break-words overflow-wrap-anywhere text-xs sm:text-sm leading-relaxed">{content}</div>
                <div className="flex justify-start pt-0.5">
                    <button
                        type="button"
                        onClick={() => {
                            navigator.clipboard.writeText(content);
                            setCopiedText(true);
                            setTimeout(() => setCopiedText(false), 2000);
                        }}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-zinc-100 hover:bg-zinc-200 dark:bg-black dark:hover:bg-zinc-900 text-zinc-500 dark:text-zinc-200 dark:border dark:border-white/20 font-bold text-xs transition-all shadow-sm active:scale-95 cursor-pointer"
                        title="نسخ رسالتك"
                    >
                        {copiedText ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                        <span className="font-sans">{copiedText ? "Copied!" : "Copy"}</span>
                    </button>
                </div>
            </div>
        );
    }

    const blocks: ContentBlock[] = parseContentBlocks(content).filter(block => {
        if (block.type !== "table") return true;
        return !tables.some(table => JSON.stringify(table.headers) === JSON.stringify(block.headers));
    });
    const renderFormattedText = (text: string, isLastBlock: boolean) => {
        let cleanText = text.replace(/```mermaid\s+[\s\S]*?```/g, "").trim();
        const lines = cleanText.split("\n");

        return lines.map((line, idx) => {
            const isLastLine = isLastBlock && idx === lines.length - 1;
            const isTableLine = line.trim().startsWith("|") && line.trim().endsWith("|");

            if (!line.trim() && !isLastLine) {
                return <div key={idx} className="h-2" />;
            }

            const trimmedLine = line.trim();

            // Headings
            let isHeading = false;
            let headingLevel = 0;
            let headingContent = line;

            if (trimmedLine.startsWith("#### ")) {
                isHeading = true;
                headingLevel = 4;
                headingContent = trimmedLine.substring(5);
            } else if (trimmedLine.startsWith("### ")) {
                isHeading = true;
                headingLevel = 3;
                headingContent = trimmedLine.substring(4);
            } else if (trimmedLine.startsWith("## ")) {
                isHeading = true;
                headingLevel = 2;
                headingContent = trimmedLine.substring(3);
            } else if (trimmedLine.startsWith("# ")) {
                isHeading = true;
                headingLevel = 1;
                headingContent = trimmedLine.substring(2);
            }

            if (isHeading) {
                const headingClass = headingLevel === 1 
                    ? "text-base sm:text-lg font-extrabold text-zinc-950 dark:text-white my-3 border-b border-zinc-200 dark:border-white/20 pb-1"
                    : headingLevel === 2
                    ? "text-sm sm:text-base font-bold text-zinc-900 dark:text-white my-2"
                    : "text-xs sm:text-sm font-bold text-emerald-600 dark:text-emerald-400 my-2";
                
                const HeadingTag = `h${headingLevel}` as "h1" | "h2" | "h3" | "h4";
                
                return (
                    <HeadingTag key={idx} className={headingClass} dir="rtl">
                        {headingContent.split(/(\*\*.*?\*\*)/g).map((boldPart, bpIdx) => {
                            const isBold = boldPart.startsWith("**") && boldPart.endsWith("**");
                            const cleanBold = isBold ? boldPart.substring(2, boldPart.length - 2) : boldPart;
                            if (isBold) {
                                return <strong key={bpIdx} className="font-extrabold">{cleanBold}</strong>;
                            }
                            return cleanBold;
                        })}
                    </HeadingTag>
                );
            }

            // Bullet check
            const isBullet = trimmedLine.startsWith("- ") || trimmedLine.startsWith("* ") || trimmedLine.startsWith("• ") || trimmedLine.startsWith("•");
            let lineContent = line;
            if (isBullet) {
                if (trimmedLine.startsWith("- ") || trimmedLine.startsWith("* ") || trimmedLine.startsWith("• ")) {
                    lineContent = trimmedLine.substring(2);
                } else if (trimmedLine.startsWith("•")) {
                    lineContent = trimmedLine.substring(1);
                }
            }

            const parseTextSpans = (textStr: string) => {
                const linkRegex = /(\[[^\]]+\]\(https?:\/\/[^\s\)]+\)|https?:\/\/[^\s<>]+)/g;
                const linkParts = textStr.split(linkRegex);
                return linkParts.map((linkPart, linkIdx) => {
                    if (!linkPart) return null;
                    const mdMatch = linkPart.match(/^\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)$/);
                    if (mdMatch) {
                        const [, label, href] = mdMatch;
                        return (
                            <a
                                key={`link-${linkIdx}`}
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline font-semibold text-blue-700 underline decoration-blue-400 underline-offset-2 hover:text-blue-500 dark:text-sky-400 dark:hover:text-sky-300"
                            >
                                {label}
                            </a>
                        );
                    }

                    const rawUrl = /^https?:\/\//i.test(linkPart) ? linkPart : null;
                    if (rawUrl) {
                        const trailingPunctuation = rawUrl.match(/[)،.!?؟:;]+$/)?.[0] || "";
                        const href = trailingPunctuation ? rawUrl.slice(0, -trailingPunctuation.length) : rawUrl;
                        return (
                            <React.Fragment key={`link-${linkIdx}`}>
                                <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    dir="ltr"
                                    className="inline break-all font-medium text-blue-700 underline decoration-blue-400 underline-offset-2 hover:text-blue-500 dark:text-sky-400 dark:hover:text-sky-300"
                                >
                                    {href}
                                </a>
                                {trailingPunctuation}
                            </React.Fragment>
                        );
                    }

                    const boldParts = linkPart.split(/(\*\*.*?\*\*)/g);
                    return boldParts.map((part, bIdx) => {
                        const isBold = part.startsWith("**") && part.endsWith("**");
                        const cleanPart = isBold ? part.substring(2, part.length - 2) : part;

                        const subParts = cleanPart.split(/(\d+(?:[,.]\d+)*|\b[A-Z0-9_]{2,10}\b|\$\d+(?:[,.]\d+)*)/g);
                        const renderedSubParts = subParts.map((sub, sIdx) => {
                            const upper = sub.toUpperCase();
                            const isStockSymbol = KNOWN_STOCK_SYMBOLS.has(upper) || /^EGX:\w+/i.test(sub);
                            const isNumericCurrency = /^(\d+(?:[,.]\d+)*|\$\d+(?:[,.]\d+)*|EGP)$/.test(sub);

                            if (isStockSymbol) {
                                return (
                                    <span 
                                        key={sIdx} 
                                        dir="ltr" 
                                        className="inline-block px-1.5 py-0.5 font-mono font-bold text-amber-700 dark:text-amber-300 bg-amber-500/10 dark:bg-black border border-amber-500/20 dark:border-white/30 rounded text-[11px] sm:text-xs mx-0.5"
                                        style={{ unicodeBidi: "isolate" }}
                                    >
                                        {sub}
                                    </span>
                                );
                            } else if (isNumericCurrency) {
                                return (
                                    <span 
                                        key={sIdx} 
                                        dir="ltr" 
                                        className="inline-block px-1 py-0.5 font-mono font-semibold text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 dark:bg-black dark:border dark:border-emerald-500/30 rounded text-[11px] sm:text-xs mx-0.5"
                                        style={{ unicodeBidi: "isolate" }}
                                    >
                                        {sub}
                                    </span>
                                );
                            }
                            return sub;
                        });

                        if (isBold) {
                            return <strong key={`${linkIdx}-${bIdx}`} className="font-extrabold text-zinc-950 dark:text-white">{renderedSubParts}</strong>;
                        }
                        return <React.Fragment key={`${linkIdx}-${bIdx}`}>{renderedSubParts}</React.Fragment>;
                    });
                });
            };

            return (
                <div 
                    key={idx} 
                    className={`leading-relaxed text-xs sm:text-sm break-words overflow-wrap-anywhere my-1 dir-auto text-zinc-900 dark:text-zinc-100 ${isBullet ? 'flex items-start gap-2 pr-2' : ''} ${isTableLine ? 'font-mono text-[11px] bg-zinc-100/80 dark:bg-black dark:border dark:border-white/20 p-1 rounded overflow-x-auto' : ''}`}
                >
                    {isBullet && <span className="text-emerald-600 dark:text-emerald-400 font-bold mt-1">•</span>}
                    <span className="flex-1">
                        {parseTextSpans(lineContent)}

                        {isStreaming && isLastLine && (
                            <span 
                                className="inline-block w-2 text-amber-500 font-bold animate-pulse mr-1 select-none" 
                                title="جاري الكتابة..."
                                aria-hidden="true"
                            >
                                ▌
                            </span>
                        )}
                    </span>
                </div>
            );
        });
    };

    const actionButtons = (suggestedButtons && suggestedButtons.length > 0)
        ? suggestedButtons
        : ["قارن بـ COMI", "هل في تجميع مؤسسي؟", "شبه ده حصل امتى؟", "قد إيه بعيد عن الحد؟"];

    return (
        <div className="space-y-3 w-full max-w-full min-w-0 text-right overflow-hidden" dir="rtl">
            {tables.map((table) => (
                <div key={`${table.id}-${table.data_time || ""}`} className="space-y-1">
                    <div className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                        {table.title}{table.data_time ? ` (${String(table.data_time).slice(0, 10)})` : ""}
                    </div>
                    <ExportableTable headers={table.headers} rows={table.rows} />
                </div>
            ))}
            {blocks.map((block, bIdx) => {
                const isLastBlock = bIdx === blocks.length - 1;
                if (block.type === "text") {
                    return (
                        <div key={bIdx} className="space-y-1 break-words overflow-wrap-anywhere text-xs sm:text-sm leading-relaxed">
                            {renderFormattedText(block.content, isLastBlock)}
                        </div>
                    );
                } else if (block.type === "table") {
                    return (
                        <div key={bIdx} className="space-y-1">
                            <ExportableTable headers={block.headers} rows={block.rows} />
                            {isStreaming && isLastBlock && (
                                <span className="inline-block w-2 text-amber-500 font-bold animate-pulse mr-1 select-none">▌</span>
                            )}
                        </div>
                    );
                } else if (block.type === "raw_pipe_table") {
                    const headers = ["السهم", "درجة التجميع", "نسبة السيولة", "RSI", "الحالة", "أيام التوالي"];
                    const rows = block.items.map(item => {
                        let signalText = item.signal;
                        if (item.signal.includes("strong accumulation") || item.signal.includes("strong_accumulation")) {
                            signalText = "تجميع قوي 📈";
                        } else if (item.signal.includes("accumulation")) {
                            signalText = "تجميع 📈";
                        } else if (item.signal.includes("strong distribution") || item.signal.includes("strong_distribution")) {
                            signalText = "تصريف قوي 📉";
                        } else if (item.signal.includes("distribution")) {
                            signalText = "تصريف 📉";
                        }
                        
                        return [
                            item.symbol,
                            `${item.score}/100`,
                            `${Number(item.val2).toFixed(2)}x`,
                            Number(item.val4).toFixed(1),
                            signalText,
                            `${item.days} أيام`
                        ];
                    });
                    
                    return (
                        <div key={bIdx} className="space-y-1">
                            <ExportableTable headers={headers} rows={rows} />
                            {isStreaming && isLastBlock && (
                                <span className="inline-block w-2 text-amber-500 font-bold animate-pulse mr-1 select-none">▌</span>
                            )}
                        </div>
                    );
                } else if (block.type === "stock_cards") {
                    return (
                        <div key={bIdx} className="my-4 space-y-3">
                            <div 
                                className={`${
                                    block.stocks.length === 1 
                                        ? "w-full max-w-xl mx-auto" 
                                        : "grid grid-cols-1 md:grid-cols-2 gap-4"
                                }`}
                            >
                                {block.stocks.map((stock, sIdx) => (
                                    <StockCard 
                                        key={sIdx} 
                                        stock={stock} 
                                        onSymbolClick={(symbol) => {
                                            if (onButtonClick) {
                                                onButtonClick(`تحليل سهم ${symbol}`);
                                            }
                                        }}
                                        onNewsClick={(symbol) => {
                                            if (onButtonClick) {
                                                onButtonClick(`أخبار سهم ${symbol}`);
                                            }
                                        }}
                                        onAddToPortfolio={(symbol) => {
                                            if (onButtonClick) {
                                                onButtonClick(`أضف سهم ${symbol} لمحفظتي`);
                                            }
                                        }}
                                    />
                                ))}
                            </div>
                            {block.tableData && (
                                <details className="mt-2 text-xs text-zinc-500 group">
                                    <summary className="cursor-pointer font-bold hover:text-amber-500 dark:hover:text-amber-400 transition-colors inline-flex items-center gap-1.5 py-1 px-2.5 rounded-lg bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-white/10 select-none">
                                        <span>📊 عرض جدول البيانات والأرقام الكاملة ({block.tableData.rows.length} صف / تصدير إكسيل)</span>
                                    </summary>
                                    <div className="mt-2">
                                        <ExportableTable headers={block.tableData.headers} rows={block.tableData.rows} />
                                    </div>
                                </details>
                            )}
                        </div>
                    );
                } else if (block.type === "stock_card") {
                    return (
                        <div key={bIdx} className="my-4 w-full max-w-xl mx-auto space-y-2">
                            <StockCard 
                                stock={block.stock} 
                                onSymbolClick={(symbol) => {
                                    if (onButtonClick) {
                                        onButtonClick(`تحليل سهم ${symbol}`);
                                    }
                                }}
                                onNewsClick={(symbol) => {
                                    if (onButtonClick) {
                                        onButtonClick(`أخبار سهم ${symbol}`);
                                    }
                                }}
                                onAddToPortfolio={(symbol) => {
                                    if (onButtonClick) {
                                        onButtonClick(`أضف سهم ${symbol} لمحفظتي`);
                                    }
                                }}
                            />
                            {block.tableData && (
                                <details className="mt-2 text-xs text-zinc-500 group">
                                    <summary className="cursor-pointer font-bold hover:text-amber-500 dark:hover:text-amber-400 transition-colors inline-flex items-center gap-1.5 py-1 px-2.5 rounded-lg bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-white/10 select-none">
                                        <span>📊 عرض جدول البيانات الكامل ({block.tableData.rows.length} صف / تصدير إكسيل)</span>
                                    </summary>
                                    <div className="mt-2">
                                        <ExportableTable headers={block.tableData.headers} rows={block.tableData.rows} />
                                    </div>
                                </details>
                            )}
                        </div>
                    );
                }
                return null;
            })}

            {mermaidCode && (
                <div className="my-4 p-4 bg-zinc-100 dark:bg-black border border-zinc-200 dark:border-white/20 rounded-xl overflow-x-auto shadow-sm max-w-full">
                    <div className="text-xs font-bold text-emerald-600 dark:text-emerald-400 mb-2 flex items-center gap-1">
                        📊 رسم بياني تفاعلي (Diagram)
                    </div>
                    <div ref={mermaidContainerRef} className="flex justify-center items-center min-h-[120px]" />
                </div>
            )}

            {role === "assistant" && !isStreaming && (
                <div className="pt-2 flex flex-wrap gap-1.5 justify-start items-center">
                    <button
                        type="button"
                        onClick={() => {
                            const tableText = tables.map(table => [
                                `${table.title}${table.data_time ? ` (${String(table.data_time).slice(0, 10)})` : ""}`,
                                table.headers.join("\t"),
                                ...table.rows.map(row => row.join("\t"))
                            ].join("\n")).join("\n\n");
                            navigator.clipboard.writeText([tableText, content].filter(Boolean).join("\n\n"));
                            setCopiedText(true);
                            setTimeout(() => setCopiedText(false), 2000);
                        }}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-zinc-100 hover:bg-zinc-200 dark:bg-black dark:hover:bg-zinc-900 text-zinc-900 dark:text-zinc-200 border border-zinc-300 dark:border-white/20 font-bold text-xs transition-all shadow-xs active:scale-95 cursor-pointer"
                        title="نسخ الرد"
                    >
                        {copiedText ? <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        <span className="font-sans">{copiedText ? "Copied!" : "Copy"}</span>
                    </button>

                    {/* 💼 1-Click Save to Portfolio powered by LLM */}
                    <button
                        type="button"
                        onClick={handleSaveToPortfolio}
                        disabled={savingToPortfolio}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-900 dark:text-amber-300 border border-amber-500/40 font-bold text-xs transition-all shadow-xs active:scale-95 cursor-pointer disabled:opacity-60"
                        title="استخراج الأسهم المذكورة وإضافتها لمحفظتك الاستثمارية فوراً بالذكاء الاصطناعي"
                    >
                        {savingToPortfolio ? (
                            <>
                                <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-600 dark:text-amber-400" />
                                <span>جاري الحفظ بالذكاء الاصطناعي...</span>
                            </>
                        ) : (
                            <>
                                <Briefcase className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                                <span>حفظ في محفظتي</span>
                            </>
                        )}
                    </button>

                    {typeof latencyMs === "number" && latencyMs > 0 && (
                        <span
                            className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-emerald-500/10 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 font-mono font-bold text-xs shadow-xs"
                            title={`زمن الرد الإجمالي: ${latencyMs} ملي ثانية (${(latencyMs / 1000).toFixed(2)} ثانية)`}
                        >
                            <Zap className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                            <span>{(latencyMs / 1000).toFixed(2)}s</span>
                        </span>
                    )}

                    {showShareButton && onShare && (
                        <button
                            type="button"
                            onClick={onShare}
                            disabled={sharing}
                            className="flex items-center gap-1 border-2 border-black bg-[#67E8F9] px-3 py-1.5 text-xs font-black text-black shadow-[2px_2px_0_0_#000] transition-all hover:translate-x-0.5 hover:translate-y-0.5 hover:shadow-none disabled:cursor-wait disabled:opacity-60"
                            title="نشر آخر سؤال وإجابته في المدونة"
                        >
                            <Share2 className="h-3.5 w-3.5" />
                            {sharing ? "جاري إنشاء الرابط..." : "شير في المدونة"}
                        </button>
                    )}

                    {onButtonClick && showSuggestedButtons && actionButtons.map((btnText, bIdx) => (
                        <button
                            key={bIdx}
                            type="button"
                            onClick={() => onButtonClick(btnText)}
                            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-50 hover:bg-amber-100/90 text-amber-950 border-2 border-amber-400 font-black text-xs transition-all shadow-xs active:scale-95 cursor-pointer dark:bg-black dark:hover:bg-zinc-900 dark:text-amber-300 dark:border-amber-400/40"
                        >
                            <Sparkles className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
                            <span>{btnText}</span>
                        </button>
                    ))}
                {portfolioFeedback && (
                        <div className="w-full mt-2">
                            {portfolioFeedback.ok ? (
                                <div className="p-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-500/40 text-emerald-900 dark:text-emerald-200 text-xs flex flex-wrap items-center justify-between gap-2 shadow-xs animate-in fade-in duration-200">
                                    <div className="flex items-center gap-1.5 min-w-0">
                                        <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                                        <span>{portfolioFeedback.message}</span>
                                        {portfolioFeedback.stocks && portfolioFeedback.stocks.length > 0 && (
                                            <span className="font-mono font-bold text-emerald-800 dark:text-emerald-300">
                                                ({portfolioFeedback.stocks.map((s: any) => `${s.symbol} ${s.quantity ? `[${s.quantity}]` : ''}`).join(", ")})
                                            </span>
                                        )}
                                    </div>
                                    <a
                                        href="/profile#portfolio"
                                        className="shrink-0 px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg transition-all text-[11px] shadow-xs"
                                    >
                                        عرض محفظتي ↗
                                    </a>
                                </div>
                            ) : portfolioFeedback.requiresAuth ? (
                                <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-500/40 text-blue-900 dark:text-blue-200 text-xs flex flex-wrap items-center justify-between gap-2 shadow-xs animate-in fade-in duration-200">
                                    <div className="flex items-center gap-1.5 min-w-0">
                                        <Lock className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
                                        <span>{portfolioFeedback.message}</span>
                                    </div>
                                    <a
                                        href="/auth/login?returnUrl=/profile"
                                        className="shrink-0 px-2.5 py-1 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg transition-all text-[11px] shadow-xs"
                                    >
                                        تسجيل الدخول
                                    </a>
                                </div>
                            ) : portfolioFeedback.isQuotaReached ? (
                                <div className="p-3 rounded-xl bg-gradient-to-r from-amber-500/10 via-yellow-500/10 to-amber-500/10 border-2 border-amber-400 text-amber-950 dark:text-amber-200 text-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 shadow-xs animate-in fade-in duration-200">
                                    <div className="flex items-center gap-2">
                                        <Crown className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                                        <span>{portfolioFeedback.message}</span>
                                    </div>
                                    <a
                                        href="/pricing"
                                        className="shrink-0 px-3 py-1 bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-600 hover:to-yellow-500 text-black font-black rounded-lg transition-all text-xs border border-black shadow-[2px_2px_0_0_#000]"
                                    >
                                        ترقية إلى Pro (عرض المؤسسين 100 ج.م) 👑
                                    </a>
                                </div>
                            ) : (
                                <div className="p-2.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-500/30 text-amber-900 dark:text-amber-200 text-xs flex items-center gap-1.5 animate-in fade-in duration-200">
                                    <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                                    <span>{portfolioFeedback.message}</span>
                                </div>
                            )}
                        </div>
                    )}
                    </div>
            )}
        </div>
    );
}
