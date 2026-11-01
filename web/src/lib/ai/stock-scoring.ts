/**
 * EGX Stock Composite Deal Scoring Engine (0 - 100)
 * محرك السكور الرياضي المركب لتقييم صفقات وأسهم البورصة المصرية
 *
 * يعتمد على خوارزمية موزونة تدمج 5 محاور كمية وفنية وأساسية:
 * 1. الزخم والاتجاه الفني وموقع المتوسطات (30 نقطة)
 * 2. نموذج الذكاء الاصطناعي الكمي KING AI (25 نقطة)
 * 3. التقييم المالي والأساسي (P/E & EPS) (20 نقطة)
 * 4. تجميع وايكوف والنشاط الحجمي النسبي (15 نقطة)
 * 5. التوافق مع مؤشر الشريعة EGX33 وعمق التداول (10 نقاط)
 */

export interface StockScoreInput {
    symbol?: string;
    close?: number | null;
    change_pct?: number | null;
    rsi_14?: number | null;
    macd?: number | null;
    macd_signal?: number | null;
    macd_hist?: number | null;
    macd_histogram?: number | null;
    ema_50?: number | null;
    ema_200?: number | null;
    relative_volume?: number | null;
    r_vol?: number | null;
    king_ai_score?: number | null;
    egx_ai_score?: number | null;
    accumulation_score?: number | null;
    acc_score?: number | null;
    distribution_score?: number | null;
    dist_score?: number | null;
    wyckoff_phase?: string | null;
    consecutive_acc_days?: number | null;
    pe_ratio?: number | null;
    eps?: number | null;
    is_sharia_compliant?: boolean | null;
}

export type ScoreGrade = "A+" | "A" | "B" | "C" | "D";
export type ScoreBadgeColor = "emerald" | "purple" | "amber" | "rose";

export interface FactorBreakdown {
    score: number;
    maxScore: number;
    percentage: number;
    status: "ممتاز" | "إيجابي" | "حيادي" | "ضعيف" | "سلبي";
    notes: string;
}

export interface StockScoreResult {
    totalScore: number; // 0 - 100
    grade: ScoreGrade;
    verdictLabel: string;
    badgeColor: ScoreBadgeColor;
    hexColor: string;
    breakdown: {
        technicalMomentum: FactorBreakdown;  // max 30
        kingAiConfidence: FactorBreakdown;   // max 25
        financialValuation: FactorBreakdown; // max 20
        wyckoffAccumulation: FactorBreakdown;// max 15
        shariaAndLiquidity: FactorBreakdown; // max 10
    };
    summaryArabic: string;
    breakdownSummary: string;
}

/**
 * دالة حساب السكور المركب لتقييم سهم بالبورصة المصرية من 0 إلى 100
 */
export function calculateStockCompositeScore(input: StockScoreInput): StockScoreResult {
        const {
        close,
        rsi_14,
        macd,
        macd_signal,
        ema_50,
        ema_200,
        king_ai_score,
        consecutive_acc_days,
        pe_ratio,
        eps,
        is_sharia_compliant
    } = input;

    const macd_hist = input.macd_histogram ?? input.macd_hist;
    const relative_volume = input.r_vol ?? input.relative_volume;
    const accumulation_score = input.acc_score ?? input.accumulation_score;
    const distribution_score = input.dist_score ?? input.distribution_score;

    // ─────────────────────────────────────────────────────────────
    // 1. الزخم الفني والاتجاه (30 نقطة)
    // ─────────────────────────────────────────────────────────────
    let techScore = 0;
    const techNotes: string[] = [];

    // أ) موقع السعر من المتوسطات المتحركة (16 نقطة)
    if (close != null && close > 0) {
        if (ema_50 != null && ema_50 > 0) {
            if (close >= ema_50) {
                techScore += 8;
                techNotes.push("أعلى من EMA 50");
            } else {
                techNotes.push("أسفل EMA 50");
            }
        } else {
            techScore += 4; // محايد عند غياب المتوسط
        }

        if (ema_200 != null && ema_200 > 0) {
            if (close >= ema_200) {
                techScore += 8;
                techNotes.push("أعلى من EMA 200 (اتجاه رئيسي صاعد)");
            } else {
                techNotes.push("أسفل EMA 200");
            }
        } else {
            techScore += 4;
        }
    } else {
        techScore += 8;
    }

    // ب) مؤشر القوة النسبية RSI (7 نقاط)
    if (rsi_14 != null && !isNaN(rsi_14)) {
        if (rsi_14 >= 45 && rsi_14 <= 65) {
            techScore += 7;
            techNotes.push(`RSI صحي متوازن (${rsi_14.toFixed(1)})`);
        } else if (rsi_14 < 35) {
            techScore += 5; // تشبع بيعي ارتدادي
            techNotes.push(`RSI في نطاق تشبع بيعي ارتدادي (${rsi_14.toFixed(1)})`);
        } else if (rsi_14 > 70) {
            techScore += 2; // تشبع شرائي زائد عرضة لجني أرباح
            techNotes.push(`RSI في تشبع شرائي (${rsi_14.toFixed(1)})`);
        } else {
            techScore += 4;
            techNotes.push(`RSI عند ${rsi_14.toFixed(1)}`);
        }
    } else {
        techScore += 4;
    }

    // ج) مؤشر MACD والهيستوجرام (7 نقاط)
    const hist = macd_hist != null ? macd_hist : (macd != null && macd_signal != null ? macd - macd_signal : null);
    if (hist != null) {
        if (hist > 0) {
            techScore += 7;
            techNotes.push("MACD أعلى إشارته (زخم إيجابي)");
        } else if (hist >= -0.05) {
            techScore += 4; // ضغط بيعي خفيف جداً
            techNotes.push("MACD قريب من خط إشارته");
        } else {
            techScore += 1;
            techNotes.push("MACD سالب تحت إشارته");
        }
    } else {
        techScore += 4;
    }

    techScore = Math.min(30, Math.max(0, techScore));
    const techPercentage = Math.round((techScore / 30) * 100);

    // ─────────────────────────────────────────────────────────────
    // 2. نموذج الذكاء الاصطناعي الكمي KING AI (25 نقطة)
    // ─────────────────────────────────────────────────────────────
    let kingScore = 0;
    let kingNote = "غير متوفر";
    if (king_ai_score != null && !isNaN(king_ai_score)) {
        // إذا كانت القيمة كنسبة مئوية > 1 (مثل 67.2) نحولها لكسر
        const normKing = king_ai_score > 1 ? king_ai_score / 100 : king_ai_score;
        if (normKing >= 0.65) {
            kingScore = 25;
            kingNote = `ثقة صعود ممتازة (${(normKing * 100).toFixed(1)}%)`;
        } else if (normKing >= 0.58) {
            kingScore = 21;
            kingNote = `ثقة صعود إيجابية (${(normKing * 100).toFixed(1)}%)`;
        } else if (normKing >= 0.50) {
            kingScore = 15;
            kingNote = `حيادي يميل للإيجابية (${(normKing * 100).toFixed(1)}%)`;
        } else if (normKing >= 0.42) {
            kingScore = 9;
            kingNote = `ثقة صعود متحفظة (${(normKing * 100).toFixed(1)}%)`;
        } else {
            kingScore = 4;
            kingNote = `ثقة صعود ضعيفة (${(normKing * 100).toFixed(1)}%)`;
        }
    } else {
        kingScore = 13; // محايد عند عدم التوفر
        kingNote = "تقييم غير مسجل في اللقطة";
    }

    const kingPercentage = Math.round((kingScore / 25) * 100);

    // ─────────────────────────────────────────────────────────────
    // 3. التقييم الأساسي والربحية P/E & EPS (20 نقطة)
    // ─────────────────────────────────────────────────────────────
    let valScore = 0;
    const valNotes: string[] = [];

    // أ) مضاعف الربحية P/E (10 نقاط)
    if (pe_ratio != null && !isNaN(pe_ratio)) {
        if (pe_ratio > 0 && pe_ratio <= 9) {
            valScore += 10;
            valNotes.push(`مضاعف ربحية مغرٍ جداً (${pe_ratio.toFixed(1)}x)`);
        } else if (pe_ratio > 9 && pe_ratio <= 16) {
            valScore += 7;
            valNotes.push(`مضاعف ربحية عادل (${pe_ratio.toFixed(1)}x)`);
        } else if (pe_ratio > 16 && pe_ratio <= 25) {
            valScore += 4;
            valNotes.push(`مضاعف ربحية مرتفع (${pe_ratio.toFixed(1)}x)`);
        } else {
            valScore += 1;
            valNotes.push("تقييم متضخم أو خسائر");
        }
    } else {
        valScore += 5; // افتراضي عند غياب P/E
        valNotes.push("P/E غير متاح في اللقطة");
    }

    // ب) ربحية السهم EPS (10 نقاط)
    if (eps != null && !isNaN(eps)) {
        if (eps > 0) {
            valScore += 10;
            valNotes.push(`ربحية سهم موجبة (${eps.toFixed(2)} ج.م)`);
        } else {
            valScore += 0;
            valNotes.push("ربحية سهم سالبة (خسائر تشغيلية)");
        }
    } else {
        valScore += 5;
    }

    valScore = Math.min(20, Math.max(0, valScore));
    const valPercentage = Math.round((valScore / 20) * 100);

    // ─────────────────────────────────────────────────────────────
    // 4. تجميع وايكوف والنشاط النسبي (15 نقطة)
    // ─────────────────────────────────────────────────────────────
    let wyckScore = 0;
    const wyckNotes: string[] = [];

    // أ) درجة التجميع المؤسسي (8 نقاط)
    if (accumulation_score != null && !isNaN(accumulation_score)) {
        if (accumulation_score >= 80) {
            wyckScore += 8;
            wyckNotes.push(`تجميع مؤسسي قوي (${accumulation_score})`);
        } else if (accumulation_score >= 60) {
            wyckScore += 6;
            wyckNotes.push(`تجميع ملحوظ (${accumulation_score})`);
        } else if (accumulation_score >= 40) {
            wyckScore += 4;
            wyckNotes.push(`تجميع متوسط (${accumulation_score})`);
        } else {
            wyckScore += 2;
        }
    } else {
        wyckScore += 4;
    }

    // ب) أيام التجميع المتتالية (2 نقطة)
    if (consecutive_acc_days != null && consecutive_acc_days >= 2) {
        wyckScore += 2;
        wyckNotes.push(`${consecutive_acc_days} جلسات تجميع متتالية`);
    }

    // ج) النشاط الحجمي النسبي r_vol (5 نقاط)
    if (relative_volume != null && !isNaN(relative_volume)) {
        if (relative_volume >= 2.0) {
            wyckScore += 5;
            wyckNotes.push(`انفجار حجمي (${relative_volume.toFixed(1)}x)`);
        } else if (relative_volume >= 1.2) {
            wyckScore += 4;
            wyckNotes.push(`نشاط سيولة أعلى من المتوسط (${relative_volume.toFixed(1)}x)`);
        } else if (relative_volume >= 0.8) {
            wyckScore += 3;
            wyckNotes.push("حجم تداول طبيعي");
        } else {
            wyckScore += 1;
            wyckNotes.push("سيولة هادئة أقل من المتوسط");
        }
    } else {
        wyckScore += 3;
    }

    wyckScore = Math.min(15, Math.max(0, wyckScore));
    const wyckPercentage = Math.round((wyckScore / 15) * 100);

    // ─────────────────────────────────────────────────────────────
    // 5. التوافق الشرعي وعمق السوق (10 نقاط)
    // ─────────────────────────────────────────────────────────────
    let shariaScore = 4; // عمق سوق أساسي
    const shariaNotes: string[] = [];

    if (is_sharia_compliant === true) {
        shariaScore += 6;
        shariaNotes.push("متوافق مع الشريعة الإسلامية (EGX33)");
    } else if (is_sharia_compliant === false) {
        shariaScore += 0;
        shariaNotes.push("خارج مؤشر الشريعة EGX33");
    } else {
        shariaScore += 3;
    }

    shariaScore = Math.min(10, Math.max(0, shariaScore));
    const shariaPercentage = Math.round((shariaScore / 10) * 100);

    // ─────────────────────────────────────────────────────────────
    // النتيجة الإجمالية والتصنيف
    // ─────────────────────────────────────────────────────────────
    const totalScore = Math.min(100, Math.max(0, techScore + kingScore + valScore + wyckScore + shariaScore));

    let grade: ScoreGrade = "B";
    let verdictLabel = "حيادي للمراقبة المشروطة";
    let badgeColor: ScoreBadgeColor = "amber";
    let hexColor = "#f59e0b";

    if (totalScore >= 80) {
        grade = "A+";
        verdictLabel = "فرصة استثمارية ممتازة";
        badgeColor = "emerald";
        hexColor = "#10b981";
    } else if (totalScore >= 68) {
        grade = "A";
        verdictLabel = "إيجابي واعد للمتابعة";
        badgeColor = "purple";
        hexColor = "#a855f7";
    } else if (totalScore >= 52) {
        grade = "B";
        verdictLabel = "حيادي للمراقبة المشروطة";
        badgeColor = "amber";
        hexColor = "#f59e0b";
    } else if (totalScore >= 38) {
        grade = "C";
        verdictLabel = "حذر / أداء فني ضعيف";
        badgeColor = "rose";
        hexColor = "#f43f5e";
    } else {
        grade = "D";
        verdictLabel = "سلبي / مخاطرة مرتفعة";
        badgeColor = "rose";
        hexColor = "#e11d48";
    }

    const summaryArabic = `سكور تقييم السهم الإجمالي: ${totalScore}/100 (${grade} — ${verdictLabel}). زخم فني: ${techScore}/30، نموذج KING AI: ${kingScore}/25، تقييم مالي: ${valScore}/20، تجميع وايكوف: ${wyckScore}/15، والتوافق الشرعي: ${shariaScore}/10.`;

    const getStatus = (pct: number): "ممتاز" | "إيجابي" | "حيادي" | "ضعيف" | "سلبي" => {
        if (pct >= 80) return "ممتاز";
        if (pct >= 65) return "إيجابي";
        if (pct >= 45) return "حيادي";
        if (pct >= 30) return "ضعيف";
        return "سلبي";
    };

    return {
        totalScore,
        grade,
        verdictLabel,
        badgeColor,
        hexColor,
        breakdown: {
            technicalMomentum: {
                score: techScore,
                maxScore: 30,
                percentage: techPercentage,
                status: getStatus(techPercentage),
                notes: techNotes.join("، ") || "مستويات فنية طبيعية",
            },
            kingAiConfidence: {
                score: kingScore,
                maxScore: 25,
                percentage: kingPercentage,
                status: getStatus(kingPercentage),
                notes: kingNote,
            },
            financialValuation: {
                score: valScore,
                maxScore: 20,
                percentage: valPercentage,
                status: getStatus(valPercentage),
                notes: valNotes.join("، ") || "بيانات مالية قياسية",
            },
            wyckoffAccumulation: {
                score: wyckScore,
                maxScore: 15,
                percentage: wyckPercentage,
                status: getStatus(wyckPercentage),
                notes: wyckNotes.join("، ") || "نشاط تداول اعتيادي",
            },
            shariaAndLiquidity: {
                score: shariaScore,
                maxScore: 10,
                percentage: shariaPercentage,
                status: getStatus(shariaPercentage),
                notes: shariaNotes.join("، ") || "سيولة تداول عامة",
            },
        },
        summaryArabic,
        breakdownSummary: summaryArabic,
    };
}
