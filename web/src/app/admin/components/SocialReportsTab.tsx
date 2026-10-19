"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
    Image as ImageIcon,
    RefreshCw,
    ExternalLink,
    Copy,
    Download,
    Eye,
    Check,
    Calendar,
    HardDrive,
    DollarSign,
    Layers,
    Search,
    Info,
    ChevronDown,
    ChevronUp,
    Sparkles,
    FileText,
    Share2,
    X,
} from "lucide-react";
import { toast } from "sonner";
import type { SocialReportImageItem } from "@/app/api/admin/social-reports/route";

const KIND_CONFIG: Record<
    string,
    { labelAr: string; labelEn: string; colorClass: string; badgeClass: string }
> = {
    stock: {
        labelAr: "تحليل سهم",
        labelEn: "Stock Report",
        colorClass: "neobrutal-bg-yellow text-black border-amber-400",
        badgeClass: "bg-amber-400 text-black font-black",
    },
    market: {
        labelAr: "وضع السوق",
        labelEn: "Market Status",
        colorClass: "neobrutal-bg-cyan text-black border-cyan-400",
        badgeClass: "bg-cyan-400 text-black font-black",
    },
    accumulation: {
        labelAr: "إشارات التجميع",
        labelEn: "Accumulation",
        colorClass: "neobrutal-bg-green text-black border-emerald-400",
        badgeClass: "bg-emerald-400 text-black font-black",
    },
    follow_up: {
        labelAr: "متابعة سابقة",
        labelEn: "Follow-up",
        colorClass: "neobrutal-bg-purple text-white border-purple-400",
        badgeClass: "bg-purple-600 text-white font-black",
    },
    unknown: {
        labelAr: "تقرير عام",
        labelEn: "General",
        colorClass: "bg-zinc-800 text-white border-zinc-700",
        badgeClass: "bg-zinc-700 text-white font-black",
    },
};

export default function SocialReportsTab() {
    const [loading, setLoading] = useState<boolean>(true);
    const [images, setImages] = useState<SocialReportImageItem[]>([]);
    const [dates, setDates] = useState<string[]>([]);
    const [stats, setStats] = useState<{
        total_images: number;
        total_bytes: number;
        total_mb: number;
        total_dates: number;
        latest_date: string | null;
    }>({
        total_images: 0,
        total_bytes: 0,
        total_mb: 0,
        total_dates: 0,
        latest_date: null,
    });

    const [selectedDate, setSelectedDate] = useState<string>("all");
    const [selectedKind, setSelectedKind] = useState<string>("all");
    const [searchQuery, setSearchQuery] = useState<string>("");
    const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
    const [activeLightboxImage, setActiveLightboxImage] = useState<SocialReportImageItem | null>(null);
    const [showCostExplainer, setShowCostExplainer] = useState<boolean>(true);

    const fetchSocialReports = async () => {
        setLoading(true);
        try {
            const res = await fetch("/api/admin/social-reports", { cache: "no-store" });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err?.detail || "فشل تحميل صور السوشيال");
            }
            const data = await res.json();
            setImages(data.images || []);
            setDates(data.dates || []);
            setStats(data.stats || {
                total_images: 0,
                total_bytes: 0,
                total_mb: 0,
                total_dates: 0,
                latest_date: null,
            });
        } catch (err: any) {
            toast.error(err?.message || "خطأ في الاتصال بالخادم");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSocialReports();
    }, []);

    const filteredImages = useMemo(() => {
        return images.filter((img) => {
            if (selectedDate !== "all" && img.session_date !== selectedDate) {
                return false;
            }
            if (selectedKind !== "all" && img.kind !== selectedKind) {
                return false;
            }
            if (searchQuery.trim()) {
                const q = searchQuery.trim().toLowerCase();
                const matchSymbol = img.symbol?.toLowerCase().includes(q);
                const matchName = img.name.toLowerCase().includes(q);
                const matchTitle = img.social_title?.toLowerCase().includes(q);
                if (!matchSymbol && !matchName && !matchTitle) return false;
            }
            return true;
        });
    }, [images, selectedDate, selectedKind, searchQuery]);

    const handleCopyUrl = async (url: string) => {
        try {
            await navigator.clipboard.writeText(url);
            setCopiedUrl(url);
            toast.success("تم نسخ رابط الصورة بنجاح!");
            setTimeout(() => setCopiedUrl(null), 2500);
        } catch {
            toast.error("فشل نسخ الرابط");
        }
    };

    const handleCopyCaption = async (caption: string | null) => {
        if (!caption) {
            toast.error("لا يوجد كابشن محفوظ لهذا التقرير");
            return;
        }
        try {
            await navigator.clipboard.writeText(caption);
            toast.success("تم نسخ نص المنشور بنجاح!");
        } catch {
            toast.error("فشل نسخ النص");
        }
    };

    const handleDownload = (img: SocialReportImageItem) => {
        const a = document.createElement("a");
        a.href = img.url;
        a.download = img.name;
        a.target = "_blank";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };

    return (
        <div className="p-4 md:p-8 max-w-[1920px] mx-auto space-y-6">
            {/* Header Section */}
            <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-6 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff]">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-xl bg-purple-600 border-2 border-black dark:border-white flex items-center justify-center text-white shadow-[3px_3px_0px_#000]">
                                <ImageIcon className="w-6 h-6" />
                            </div>
                            <div>
                                <h1 className="text-xl md:text-2xl font-black text-black dark:text-white tracking-wide uppercase">
                                    معرض صور السوشيال • Bucket: social-reports
                                </h1>
                                <p className="text-xs md:text-sm text-zinc-500 font-semibold mt-0.5">
                                    بطاقات التحليل اليومية الموثقة (1200×1200 PNG) المخزنة في Supabase Storage والمخصصة للنشر التلقائي
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-3 self-end md:self-auto">
                        <button
                            onClick={fetchSocialReports}
                            disabled={loading}
                            className="px-4 py-2.5 border-2 md:border-4 border-black dark:border-white bg-amber-400 hover:bg-amber-300 text-black font-black text-xs uppercase tracking-wider shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] active:translate-x-0.5 active:translate-y-0.5 transition-all flex items-center gap-2 disabled:opacity-50"
                        >
                            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                            تحديث الصور
                        </button>
                    </div>
                </div>

                {/* Metrics Bar */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t-2 border-dashed border-zinc-200 dark:border-zinc-800">
                    <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/60 p-4 rounded-lg">
                        <div className="flex items-center gap-2 text-zinc-500 text-xs font-bold uppercase">
                            <Layers className="w-4 h-4 text-purple-500" />
                            <span>إجمالي الصور</span>
                        </div>
                        <div className="text-2xl md:text-3xl font-black text-black dark:text-white mt-1">
                            {stats.total_images}{" "}
                            <span className="text-xs font-semibold text-zinc-400">صورة</span>
                        </div>
                    </div>

                    <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/60 p-4 rounded-lg">
                        <div className="flex items-center gap-2 text-zinc-500 text-xs font-bold uppercase">
                            <Calendar className="w-4 h-4 text-cyan-500" />
                            <span>الجلسات المسجلة</span>
                        </div>
                        <div className="text-2xl md:text-3xl font-black text-black dark:text-white mt-1">
                            {stats.total_dates}{" "}
                            <span className="text-xs font-semibold text-zinc-400">جلسة</span>
                        </div>
                        {stats.latest_date && (
                            <div className="text-[10px] text-zinc-500 font-mono mt-1">
                                أحدث جلسة: {stats.latest_date}
                            </div>
                        )}
                    </div>

                    <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/60 p-4 rounded-lg">
                        <div className="flex items-center gap-2 text-zinc-500 text-xs font-bold uppercase">
                            <HardDrive className="w-4 h-4 text-emerald-500" />
                            <span>حجم التخزين الفعلي</span>
                        </div>
                        <div className="text-2xl md:text-3xl font-black text-black dark:text-white mt-1">
                            {stats.total_mb}{" "}
                            <span className="text-xs font-semibold text-zinc-400">MB</span>
                        </div>
                        <div className="text-[10px] text-emerald-600 dark:text-emerald-400 font-bold mt-1">
                            ضمن باقة Supabase المجانية (1000 MB)
                        </div>
                    </div>

                    <div className="border-2 border-black dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/60 p-4 rounded-lg">
                        <div className="flex items-center gap-2 text-zinc-500 text-xs font-bold uppercase">
                            <DollarSign className="w-4 h-4 text-amber-500" />
                            <span>تكلفة التوليد الشهرية</span>
                        </div>
                        <div className="text-2xl md:text-3xl font-black text-emerald-500 mt-1">
                            $0.00{" "}
                            <span className="text-xs font-semibold text-zinc-400">مجاناً</span>
                        </div>
                        <div className="text-[10px] text-zinc-400 font-bold mt-1">
                            توليد محلي بالكامل (Python PIL)
                        </div>
                    </div>
                </div>
            </div>

            {/* Explanation / Cost Breakdown Box */}
            <div className="border-4 border-black dark:border-white bg-zinc-950 p-5 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff]">
                <div
                    className="flex items-center justify-between cursor-pointer select-none"
                    onClick={() => setShowCostExplainer(!showCostExplainer)}
                >
                    <div className="flex items-center gap-2.5">
                        <Info className="w-5 h-5 text-amber-400" />
                        <h2 className="text-sm md:text-base font-black uppercase tracking-wider text-white">
                            من الذي يصنع هذه الصور وكم تكلفنا؟ (التفاصيل والتقنية)
                        </h2>
                    </div>
                    <button className="text-zinc-400 hover:text-white transition-colors">
                        {showCostExplainer ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </button>
                </div>

                {showCostExplainer && (
                    <div className="mt-4 pt-4 border-t-2 border-zinc-800 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs leading-relaxed text-zinc-300">
                        <div className="p-3 bg-zinc-900/90 rounded border border-zinc-800 space-y-1.5">
                            <div className="font-black text-amber-400 flex items-center gap-1.5">
                                <Sparkles className="w-3.5 h-3.5" />
                                1. من ينشئ الصور؟
                            </div>
                            <p className="text-zinc-400">
                                يتم التوليد تلقائياً عبر البوت اليومي (<code className="text-zinc-200">daily_bot</code>) على خادم Hugging Face Spaces من الأحد إلى الخميس بعد إغلاق جلسة التداول مباشرة (~18:30 بتوقيت مصر).
                            </p>
                            <p className="text-zinc-400">
                                الكود المسؤول: <code className="text-purple-300">api/social_report_images.py</code>، ويقوم بإنشاء 4 بطاقات لكل جلسة: وضع السوق، إشارات التجميع، تحليل سهم مختار، ومتابعة سابقة.
                            </p>
                        </div>

                        <div className="p-3 bg-zinc-900/90 rounded border border-zinc-800 space-y-1.5">
                            <div className="font-black text-cyan-400 flex items-center gap-1.5">
                                <ImageIcon className="w-3.5 h-3.5" />
                                2. كيف يتم تصميمها؟
                            </div>
                            <p className="text-zinc-400">
                                لا نستخدم أي نموذج لتوليد الصور بالذكاء الاصطناعي (مثل DALL-E أو Midjourney). يتم رسم البطاقات كلياً في الذاكرة عبر مكتبة <strong className="text-white">Python Pillow (PIL)</strong> بدقة 1200×1200 بكسل.
                            </p>
                            <p className="text-zinc-400">
                                يُطبق خط Cairo العربي وشعار المنصة وألوان الهوية البصرية وجدول البيانات الموثقة المستخرجة مباشرة من مؤشرات الجلسة المنتهية.
                            </p>
                        </div>

                        <div className="p-3 bg-zinc-900/90 rounded border border-zinc-800 space-y-1.5">
                            <div className="font-black text-emerald-400 flex items-center gap-1.5">
                                <DollarSign className="w-3.5 h-3.5" />
                                3. كم تكلفنا؟
                            </div>
                            <ul className="list-disc list-inside space-y-1 text-zinc-400">
                                <li>
                                    <strong className="text-white">توليد الصور:</strong> <span className="text-emerald-400 font-bold">$0.00</span> (معالجة CPU محلية مجانية).
                                </li>
                                <li>
                                    <strong className="text-white">توليد النصوص:</strong> نستخدم DeepSeek-V3 لصياغة التقرير النصي اليومي، وتكلفته أقل من <span className="text-emerald-400 font-bold">$0.001</span> للجلسة (أقل من 3 سنت في الشهر).
                                </li>
                                <li>
                                    <strong className="text-white">التخزين:</strong> الصور (~110 KB لكل صورة) تستهلك ~9.5 MB شهرياً فقط من أصل 1000 MB مجانية على Supabase.
                                </li>
                            </ul>
                        </div>
                    </div>
                )}
            </div>

            {/* Filter and Control Bar */}
            <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] space-y-4">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    {/* Date Selector */}
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-black uppercase text-zinc-500">الجلسة:</span>
                        <select
                            value={selectedDate}
                            onChange={(e) => setSelectedDate(e.target.value)}
                            className="bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-white text-xs font-bold px-3 py-2 rounded-none text-black dark:text-white outline-none focus:ring-2 focus:ring-purple-500"
                        >
                            <option value="all">كل الجلسات ({dates.length} جلسة)</option>
                            {dates.map((d) => (
                                <option key={d} value={d}>
                                    جلسة {d} {d === stats.latest_date ? "• الأحدث" : ""}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Kind Pills */}
                    <div className="flex flex-wrap items-center gap-1.5">
                        <button
                            onClick={() => setSelectedKind("all")}
                            className={`px-3 py-1.5 border-2 border-black dark:border-white text-xs font-black uppercase tracking-wider transition-all ${
                                selectedKind === "all"
                                    ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_#888]"
                                    : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200"
                            }`}
                        >
                            الكل ({images.length})
                        </button>
                        {Object.entries(KIND_CONFIG).map(([k, cfg]) => {
                            if (k === "unknown") return null;
                            const count = images.filter((img) => img.kind === k).length;
                            const isActive = selectedKind === k;
                            return (
                                <button
                                    key={k}
                                    onClick={() => setSelectedKind(k)}
                                    className={`px-3 py-1.5 border-2 border-black dark:border-white text-xs font-black tracking-wider transition-all ${
                                        isActive
                                            ? `${cfg.colorClass} shadow-[2px_2px_0px_#000]`
                                            : "bg-zinc-100 dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-800"
                                    }`}
                                >
                                    {cfg.labelAr} ({count})
                                </button>
                            );
                        })}
                    </div>

                    {/* Search */}
                    <div className="relative min-w-[200px] max-w-xs">
                        <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                        <input
                            type="text"
                            placeholder="بحث برمز السهم (مثلاً COMI)..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full bg-zinc-100 dark:bg-zinc-900 border-2 border-black dark:border-white text-xs font-semibold pl-9 pr-3 py-2 text-black dark:text-white outline-none focus:border-purple-500 placeholder:text-zinc-500"
                        />
                    </div>
                </div>
            </div>

            {/* Images Grid */}
            {loading ? (
                <div className="min-h-[300px] flex flex-col items-center justify-center gap-3 border-4 border-black dark:border-white bg-zinc-950 p-12">
                    <RefreshCw className="w-8 h-8 text-purple-400 animate-spin" />
                    <p className="text-sm font-bold text-zinc-400">جاري قراءة الصور من البوكيت والبيانات...</p>
                </div>
            ) : filteredImages.length === 0 ? (
                <div className="min-h-[250px] flex flex-col items-center justify-center gap-3 border-4 border-black dark:border-white bg-zinc-950 p-12 text-center">
                    <ImageIcon className="w-10 h-10 text-zinc-600" />
                    <h3 className="text-base font-black text-white uppercase">لا توجد صور مطابقة</h3>
                    <p className="text-xs text-zinc-500">
                        جرب تغيير فلتر التاريخ أو نوع التقرير أو محو نص البحث.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {filteredImages.map((img) => {
                        const kindCfg = KIND_CONFIG[img.kind] || KIND_CONFIG.unknown;
                        const sizeKb = Math.round(img.size / 1024);

                        return (
                            <div
                                key={img.id}
                                className="group border-4 border-black dark:border-white bg-white dark:bg-zinc-950 flex flex-col justify-between shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] hover:-translate-y-1 hover:shadow-[8px_8px_0px_#000] dark:hover:shadow-[8px_8px_0px_#fff] transition-all"
                            >
                                {/* Top Image Preview */}
                                <div className="relative aspect-square bg-zinc-900 overflow-hidden border-b-4 border-black dark:border-white cursor-pointer"
                                     onClick={() => setActiveLightboxImage(img)}
                                >
                                    <img
                                        src={img.url}
                                        alt={img.social_title || img.name}
                                        loading="lazy"
                                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                                    />
                                    {/* Overlay on hover */}
                                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setActiveLightboxImage(img);
                                            }}
                                            className="p-2.5 bg-white text-black font-black rounded-lg border-2 border-black shadow-[2px_2px_0px_#000] hover:bg-amber-300 transition-all"
                                            title="معاينة كاملة"
                                        >
                                            <Eye className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleCopyUrl(img.url);
                                            }}
                                            className="p-2.5 bg-white text-black font-black rounded-lg border-2 border-black shadow-[2px_2px_0px_#000] hover:bg-cyan-300 transition-all"
                                            title="نسخ الرابط"
                                        >
                                            {copiedUrl === img.url ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                                        </button>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDownload(img);
                                            }}
                                            className="p-2.5 bg-white text-black font-black rounded-lg border-2 border-black shadow-[2px_2px_0px_#000] hover:bg-emerald-300 transition-all"
                                            title="تنزيل الصورة"
                                        >
                                            <Download className="w-4 h-4" />
                                        </button>
                                    </div>

                                    {/* Floating Badges */}
                                    <div className="absolute top-2 left-2 flex flex-col gap-1 pointer-events-none">
                                        <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider rounded border border-black shadow-[2px_2px_0px_#000] ${kindCfg.badgeClass}`}>
                                            {kindCfg.labelAr}
                                        </span>
                                        {img.symbol && (
                                            <span className="px-2 py-0.5 text-[10px] font-mono font-black bg-white text-black border border-black shadow-[2px_2px_0px_#000]">
                                                {img.symbol}
                                            </span>
                                        )}
                                    </div>

                                    <div className="absolute bottom-2 right-2 pointer-events-none">
                                        <span className="px-2 py-0.5 text-[9px] font-mono font-bold bg-black/80 text-white border border-zinc-700 backdrop-blur-sm">
                                            {sizeKb > 0 ? `${sizeKb} KB` : "PNG"}
                                        </span>
                                    </div>
                                </div>

                                {/* Content Info */}
                                <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
                                    <div>
                                        <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 font-bold mb-1">
                                            <span className="flex items-center gap-1">
                                                <Calendar className="w-3 h-3" />
                                                {img.session_date}
                                            </span>
                                            <span className="text-zinc-400">1200×1200</span>
                                        </div>

                                        <h4 className="text-xs md:text-sm font-black text-black dark:text-white line-clamp-1" title={img.social_title || img.name}>
                                            {img.social_title || img.name}
                                        </h4>

                                        {img.social_caption && (
                                            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 line-clamp-2 mt-1 leading-snug">
                                                {img.social_caption.slice(0, 140)}...
                                            </p>
                                        )}
                                    </div>

                                    {/* Action Bar */}
                                    <div className="pt-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-2">
                                        <button
                                            onClick={() => setActiveLightboxImage(img)}
                                            className="flex-1 py-1.5 px-2 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-black dark:text-white text-[11px] font-black border border-black dark:border-zinc-700 flex items-center justify-center gap-1 transition-colors"
                                        >
                                            <FileText className="w-3 h-3 text-purple-400" />
                                            التفاصيل والكابشن
                                        </button>
                                        <button
                                            onClick={() => handleCopyUrl(img.url)}
                                            className="p-1.5 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-black dark:text-white border border-black dark:border-zinc-700 transition-colors"
                                            title="نسخ الرابط المباشر"
                                        >
                                            {copiedUrl === img.url ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                                        </button>
                                        <button
                                            onClick={() => handleDownload(img)}
                                            className="p-1.5 bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-black dark:text-white border border-black dark:border-zinc-700 transition-colors"
                                            title="تنزيل"
                                        >
                                            <Download className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Lightbox / Details Modal */}
            {activeLightboxImage && (
                <div
                    className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 md:p-8 overflow-y-auto"
                    onClick={() => setActiveLightboxImage(null)}
                >
                    <div
                        className="relative w-full max-w-5xl border-4 border-black dark:border-white bg-zinc-950 p-6 shadow-[10px_10px_0px_#fff] text-white space-y-6 my-auto"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Close Button */}
                        <button
                            onClick={() => setActiveLightboxImage(null)}
                            className="absolute top-4 left-4 p-2 bg-zinc-900 hover:bg-zinc-800 border-2 border-white rounded-lg transition-colors z-10"
                        >
                            <X className="w-5 h-5" />
                        </button>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
                            {/* Full Image */}
                            <div className="border-2 border-zinc-800 bg-black rounded-lg overflow-hidden flex items-center justify-center">
                                <img
                                    src={activeLightboxImage.url}
                                    alt={activeLightboxImage.social_title || activeLightboxImage.name}
                                    className="w-full h-auto max-h-[600px] object-contain"
                                />
                            </div>

                            {/* Details & Actions */}
                            <div className="space-y-4">
                                <div>
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className={`px-2 py-0.5 text-xs font-black uppercase rounded ${KIND_CONFIG[activeLightboxImage.kind]?.badgeClass || "bg-zinc-700 text-white"}`}>
                                            {KIND_CONFIG[activeLightboxImage.kind]?.labelAr || activeLightboxImage.kind}
                                        </span>
                                        {activeLightboxImage.symbol && (
                                            <span className="px-2 py-0.5 text-xs font-mono font-black bg-white text-black rounded">
                                                {activeLightboxImage.symbol}
                                            </span>
                                        )}
                                        <span className="text-xs text-zinc-400 font-mono">
                                            جلسة {activeLightboxImage.session_date}
                                        </span>
                                    </div>
                                    <h3 className="text-lg md:text-xl font-black text-white">
                                        {activeLightboxImage.social_title || activeLightboxImage.name}
                                    </h3>
                                    <p className="text-xs text-zinc-500 font-mono mt-0.5">
                                        {activeLightboxImage.path} • {Math.round(activeLightboxImage.size / 1024)} KB
                                    </p>
                                </div>

                                {/* Action Buttons */}
                                <div className="flex flex-wrap items-center gap-2 pt-2">
                                    <button
                                        onClick={() => handleCopyUrl(activeLightboxImage.url)}
                                        className="px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white font-black text-xs border border-white flex items-center gap-1.5 shadow-[2px_2px_0px_#fff]"
                                    >
                                        <Copy className="w-3.5 h-3.5" />
                                        نسخ رابط الصورة المباشر
                                    </button>
                                    <button
                                        onClick={() => handleDownload(activeLightboxImage)}
                                        className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-black text-xs border border-white flex items-center gap-1.5 shadow-[2px_2px_0px_#fff]"
                                    >
                                        <Download className="w-3.5 h-3.5" />
                                        تنزيل الصورة (PNG)
                                    </button>
                                    <a
                                        href={activeLightboxImage.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-white font-black text-xs border border-zinc-600 flex items-center gap-1.5"
                                    >
                                        <ExternalLink className="w-3.5 h-3.5" />
                                        فتح في تبويب جديد
                                    </a>
                                </div>

                                {/* Caption Box */}
                                <div className="border border-zinc-800 bg-zinc-900/90 p-4 rounded-lg space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                                            <Share2 className="w-3.5 h-3.5" />
                                            نص المنشور الجاهز (Social Caption)
                                        </span>
                                        {activeLightboxImage.social_caption && (
                                            <button
                                                onClick={() => handleCopyCaption(activeLightboxImage.social_caption)}
                                                className="text-xs text-zinc-400 hover:text-white flex items-center gap-1 underline underline-offset-4"
                                            >
                                                <Copy className="w-3 h-3" />
                                                نسخ الكابشن
                                            </button>
                                        )}
                                    </div>
                                    <div className="text-xs text-zinc-300 whitespace-pre-line leading-relaxed max-h-[220px] overflow-y-auto pr-1">
                                        {activeLightboxImage.social_caption || "لا يوجد كابشن محفوظ لهذا التقرير."}
                                    </div>
                                </div>

                                {/* Hashtags */}
                                {activeLightboxImage.social_hashtags && activeLightboxImage.social_hashtags.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5">
                                        {activeLightboxImage.social_hashtags.map((tag) => (
                                            <span
                                                key={tag}
                                                className="px-2 py-0.5 bg-zinc-900 text-purple-400 border border-zinc-800 text-[11px] font-mono rounded"
                                            >
                                                {tag}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
