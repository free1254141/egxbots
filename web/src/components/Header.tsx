"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";
import { useTheme } from "@/contexts/ThemeContext";
import {
    Globe, BarChart2, Brain, Activity, Menu, X, User, ChevronDown, BadgeDollarSign,
    Search, Loader2, Sun, Moon, TrendingUp, Heart, Bot, FileText, Wallet, Sparkles, HelpCircle
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useMarket, type MarketMode } from "@/contexts/MarketContext";
import { POPULAR_TASI_STOCKS, SAUDI_STOCK_NAMES_AR, isSaudiSymbol } from "@/lib/saudi-stocks";
import { searchSymbols } from "@/lib/api";
import PortfolioHeaderChip from "@/components/PortfolioHeaderChip";
import QuickProfitGuideModal from "@/components/QuickProfitGuideModal";
import { EgyptFlag, SaudiFlag } from "@/components/MarketFlag";

type SearchResult = {
    symbol: string;
    name?: string;
    name_ar?: string;
    exchange?: string;
};

const POPULAR_EGX_STOCKS: SearchResult[] = [
    { symbol: "COMI", name: "Commercial International Bank", name_ar: "البنك التجاري الدولي", exchange: "EGX" },
    { symbol: "FWRY", name: "Fawry for Banking & Payment Technology", name_ar: "فوري لتكنولوجيا البنوك", exchange: "EGX" },
    { symbol: "TMGH", name: "Talaat Moustafa Group", name_ar: "مجموعة طلعت مصطفى", exchange: "EGX" },
    { symbol: "EAST", name: "Eastern Company", name_ar: "الشرقية للدخان", exchange: "EGX" },
    { symbol: "AALR", name: "General Co. for Land Reclamation", name_ar: "العامة لاستصلاح الأراضي", exchange: "EGX" },
];

function StockSearchRow({
    result,
    language,
    isSaudi,
    onSelect,
}: {
    result: SearchResult;
    language: string;
    isSaudi: boolean;
    onSelect: (symbol: string) => void;
}) {
    const baseSym = String(result.symbol || "").split(".")[0].toUpperCase();
    const exUpper = (result.exchange || "").toUpperCase();
    const isTasiItem =
        exUpper === "TADAWUL" ||
        exUpper === "TASI" ||
        isSaudi ||
        isSaudiSymbol(result.symbol);
    const badgeLabel = isTasiItem ? "TASI" : exUpper || "EGX";
    const displayName =
        language === "ar"
            ? result.name_ar || (isTasiItem ? SAUDI_STOCK_NAMES_AR[baseSym] : undefined) || result.name
            : result.name;

    return (
        <button
            onClick={() => onSelect(result.symbol)}
            className="flex items-center justify-between w-full px-4 py-2.5 rounded-none text-left border-b border-black/10 dark:border-white/10 last:border-b-0 hover:bg-[#FFE600] hover:text-black transition-none group/item text-black dark:text-white"
        >
            <div className="flex flex-col min-w-0">
                <span className="text-xs font-black text-black dark:text-white group-hover/item:text-black">
                    {result.symbol}
                </span>
                <span className="text-[10px] text-zinc-500 dark:text-zinc-400 font-semibold truncate max-w-[200px] sm:max-w-[260px] group-hover/item:text-black/80">
                    {displayName}
                </span>
            </div>
            <span
                className={`text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-none text-black border-2 border-black shrink-0 ${
                    isTasiItem ? "bg-emerald-400" : "bg-[#00FF66]"
                }`}
            >
                {badgeLabel}
            </span>
        </button>
    );
}

function MarketSwitcher({
    market,
    setMarket,
    language,
    variant = "bar",
}: {
    market: MarketMode;
    setMarket: (m: MarketMode) => void;
    language: string;
    variant?: "bar" | "drawer";
}) {
    const isSaudi = market === "tasi";

    if (variant === "drawer") {
        return (
            <div className="px-3 pt-3 pb-1">
                <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500 dark:text-zinc-400 px-1 mb-1.5">
                    {language === "ar" ? "تبديل السوق" : "Active Market"}
                </div>
                <div
                    role="group"
                    aria-label={language === "ar" ? "تبديل السوق" : "Switch Market"}
                    className="grid grid-cols-2 gap-1.5 p-1 rounded-xl border-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_0px_rgba(255,255,255,0.2)]"
                >
                    <button
                        type="button"
                        onClick={() => setMarket("egx")}
                        aria-pressed={!isSaudi}
                        className={`flex items-center justify-center gap-2 py-2.5 px-2.5 rounded-lg text-xs font-black transition-all cursor-pointer ${
                            !isSaudi
                                ? "bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] ring-2 ring-[#FFE600]/45"
                                : "text-zinc-700 dark:text-zinc-300 border-2 border-transparent hover:bg-zinc-200/70 dark:hover:bg-zinc-800 hover:text-black dark:hover:text-white"
                        }`}
                    >
                        <EgyptFlag className="w-5 h-3.5" />
                        <span>{language === "ar" ? "مصر EGX" : "Egypt EGX"}</span>
                    </button>
                    <button
                        type="button"
                        onClick={() => setMarket("tasi")}
                        aria-pressed={isSaudi}
                        className={`flex items-center justify-center gap-2 py-2.5 px-2.5 rounded-lg text-xs font-black transition-all cursor-pointer ${
                            isSaudi
                                ? "bg-emerald-400 text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] ring-2 ring-emerald-400/45"
                                : "text-zinc-700 dark:text-zinc-300 border-2 border-transparent hover:bg-zinc-200/70 dark:hover:bg-zinc-800 hover:text-black dark:hover:text-white"
                        }`}
                    >
                        <SaudiFlag className="w-5 h-3.5" />
                        <span>{language === "ar" ? "السعودية TASI" : "Saudi TASI"}</span>
                        <span className="px-1.5 py-0.5 rounded bg-black text-[#FFE600] text-[9px] font-black leading-none uppercase tracking-wider">
                            BETA
                        </span>
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div
            role="group"
            aria-label={language === "ar" ? "تبديل السوق" : "Switch Market"}
            className="inline-flex items-center gap-0.5 p-0.5 rounded-xl bg-zinc-100 dark:bg-zinc-900 border-3 border-black dark:border-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] dark:shadow-[2px_2px_0px_0px_rgba(255,255,255,0.3)] shrink-0"
        >
            <button
                type="button"
                onClick={() => setMarket("egx")}
                aria-pressed={!isSaudi}
                title={language === "ar" ? "السوق المصري (EGX)" : "Egyptian Market (EGX)"}
                className={`flex items-center gap-1.5 h-7 px-2 rounded-lg text-[11px] font-black tracking-tight transition-all cursor-pointer whitespace-nowrap ${
                    !isSaudi
                        ? "bg-[#FFE600] text-black border-2 border-black shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] ring-2 ring-[#FFE600]/45"
                        : "text-zinc-700 dark:text-zinc-300 border-2 border-transparent hover:bg-zinc-200/70 dark:hover:bg-zinc-800 hover:text-black dark:hover:text-white"
                }`}
            >
                <EgyptFlag className="w-4 h-3" />
                <span className="hidden xl:inline">
                    {language === "ar" ? "مصر EGX" : "Egypt EGX"}
                </span>
                <span className="xl:hidden">EGX</span>
            </button>
            <button
                type="button"
                onClick={() => setMarket("tasi")}
                aria-pressed={isSaudi}
                title={language === "ar" ? "السوق السعودي (تاسي TASI)" : "Saudi Market (Tadawul TASI)"}
                className={`flex items-center gap-1.5 h-7 px-2 rounded-lg text-[11px] font-black tracking-tight transition-all cursor-pointer whitespace-nowrap ${
                    isSaudi
                        ? "bg-emerald-400 text-black border-2 border-black shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] ring-2 ring-emerald-400/45"
                        : "text-zinc-700 dark:text-zinc-300 border-2 border-transparent hover:bg-zinc-200/70 dark:hover:bg-zinc-800 hover:text-black dark:hover:text-white"
                }`}
            >
                <SaudiFlag className="w-4 h-3" />
                <span className="hidden xl:inline">
                    {language === "ar" ? "السعودية TASI" : "Saudi TASI"}
                </span>
                <span className="xl:hidden">TASI</span>
                <span className="px-1 py-0.5 rounded bg-black text-[#FFE600] text-[8px] font-black leading-none uppercase tracking-wider">
                    BETA
                </span>
            </button>
        </div>
    );
}

function SearchDropdown({
    language,
    isSaudi,
    searchQuery,
    searching,
    searchResults,
    onSelect,
}: {
    language: string;
    isSaudi: boolean;
    searchQuery: string;
    searching: boolean;
    searchResults: SearchResult[];
    onSelect: (symbol: string) => void;
}) {
    if (!searchQuery.trim()) {
        const popularStocks = isSaudi ? POPULAR_TASI_STOCKS : POPULAR_EGX_STOCKS;
        const popularHeading = isSaudi
            ? language === "ar"
                ? "الأسهم السعودية الأكثر شعبية"
                : "Popular TASI Stocks"
            : language === "ar"
              ? "الأسهم المصرية الأكثر شعبية"
              : "Popular EGX Stocks";

        return (
            <div className="flex flex-col">
                <div className="px-4 py-2 text-[10px] font-black text-zinc-500 dark:text-zinc-400 uppercase tracking-widest border-b-2 border-black dark:border-white bg-zinc-100 dark:bg-zinc-900 select-none">
                    {popularHeading}
                </div>
                {popularStocks.map((result) => (
                    <StockSearchRow
                        key={result.symbol}
                        result={result}
                        language={language}
                        isSaudi={isSaudi}
                        onSelect={onSelect}
                    />
                ))}
            </div>
        );
    }

    if (searching) {
        return (
            <div className="flex items-center justify-center py-5 text-zinc-500 gap-1.5 text-[10px] font-bold uppercase tracking-wider">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                <span>{language === "ar" ? "جاري البحث..." : "Searching..."}</span>
            </div>
        );
    }

    if (searchResults.length > 0) {
        return (
            <div className="flex flex-col">
                {searchResults.map((result) => (
                    <StockSearchRow
                        key={result.symbol}
                        result={result}
                        language={language}
                        isSaudi={isSaudi}
                        onSelect={onSelect}
                    />
                ))}
            </div>
        );
    }

    return (
        <div className="text-center py-6 text-xs text-zinc-500 font-black uppercase tracking-widest border-t-2 border-black bg-zinc-50 dark:bg-zinc-900 dark:border-white">
            {language === "ar" ? "لا توجد نتائج" : "No symbols found"}
        </div>
    );
}

export default function Header() {
    const { language, setLanguage, t } = useLanguage();
    const { market, setMarket, isSaudi, country, exchange } = useMarket();
    const { theme, toggleTheme } = useTheme();
    const { user, signOut } = useAuth();
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const router = useRouter();
    const currentTab = searchParams.get("tab");

    const shellRef = useRef<HTMLDivElement>(null);
    const headerRef = useRef<HTMLElement>(null);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [searchModalOpen, setSearchModalOpen] = useState(false);
    const [accountMenuOpen, setAccountMenuOpen] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
    const [searching, setSearching] = useState(false);
    const [profitGuideOpen, setProfitGuideOpen] = useState(false);

    const updateHeaderOffset = useCallback(() => {
        const shell = shellRef.current;
        if (shell) {
            const bottom = shell.getBoundingClientRect().bottom;
            document.documentElement.style.setProperty("--header-h", `${Math.ceil(bottom)}px`);
            document.documentElement.style.setProperty("--header-offset", `${Math.ceil(bottom + 8)}px`);
            return;
        }
        const headerEl = headerRef.current;
        if (!headerEl) return;
        const bottom = headerEl.getBoundingClientRect().bottom;
        document.documentElement.style.setProperty("--header-h", `${Math.ceil(bottom)}px`);
        document.documentElement.style.setProperty("--header-offset", `${Math.ceil(bottom + 8)}px`);
    }, []);

    useEffect(() => {
        setMobileMenuOpen(false);
        setSearchModalOpen(false);
        setAccountMenuOpen(false);
    }, [pathname]);

    useEffect(() => {
        updateHeaderOffset();
        const target = shellRef.current || headerRef.current;
        if (!target) return;

        const handleResize = () => {
            if (window.innerWidth >= 768) {
                setMobileMenuOpen(false);
            }
            updateHeaderOffset();
        };

        const observer = new ResizeObserver(updateHeaderOffset);
        observer.observe(target);
        window.addEventListener("resize", handleResize);

        return () => {
            observer.disconnect();
            window.removeEventListener("resize", handleResize);
        };
    }, [updateHeaderOffset, user]);

    useEffect(() => {
        setSearchResults([]);
    }, [market]);

    useEffect(() => {
        if (!searchQuery.trim()) {
            setSearchResults([]);
            setSearching(false);
            return;
        }

        const controller = new AbortController();
        const delayDebounce = setTimeout(async () => {
            setSearching(true);
            try {
                const results = await searchSymbols(
                    searchQuery,
                    country,
                    50,
                    controller.signal,
                    undefined,
                    exchange
                );
                setSearchResults(results);
            } catch (err: any) {
                if (err?.name !== "AbortError") {
                    console.error("Error searching symbols:", err);
                }
            } finally {
                if (!controller.signal.aborted) {
                    setSearching(false);
                }
            }
        }, 350);

        return () => {
            clearTimeout(delayDebounce);
            controller.abort();
        };
    }, [searchQuery, country, exchange]);

    useEffect(() => {
        const openSearchModal = () => {
            setMobileMenuOpen(false);
            setSearchModalOpen(true);
            setTimeout(() => document.getElementById("global-stock-search-input")?.focus(), 40);
        };
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                openSearchModal();
            } else if (e.key === "/") {
                const active = document.activeElement?.tagName.toLowerCase();
                if (active !== "input" && active !== "textarea") {
                    e.preventDefault();
                    openSearchModal();
                }
            } else if (e.key === "Escape") {
                setSearchModalOpen(false);
                setSearchQuery("");
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, []);

    const allNavItems = [
        { href: "/scanner/backtests?tab=bots", label: t("nav.scanner.ai_trading"), icon: <Brain className="w-4 h-4 shrink-0" />, activePath: "/scanner/backtests" },
        { href: "/disclosures", label: language === "ar" ? "الإفصاحات" : "Disclosures", icon: <FileText className="w-4 h-4 shrink-0" />, activePath: "/disclosures", badge: "AI", egxOnly: true },
        { href: "/news", label: t("nav.scanner.news"), icon: <Globe className="w-4 h-4 shrink-0" />, activePath: "/news", badge: "NEW" },
        { href: "/scanner/technical", label: t("nav.scanner.tech"), icon: <Activity className="w-4 h-4 shrink-0" />, activePath: "/scanner/technical" },
        { href: "/scanner/market", label: t("nav.scanner.market"), icon: <Globe className="w-4 h-4 shrink-0" />, activePath: "/scanner/market" },
        { href: "/pricing", label: t("nav.pricing"), icon: <BadgeDollarSign className="w-4 h-4 shrink-0" />, activePath: "/pricing", badge: language === "ar" ? "بريميوم" : "PRO" },
    ];
    const navItems = isSaudi ? allNavItems.filter((item) => !item.egxOnly) : allNavItems;

    const checkActive = (href: string, activePath: string | null) => {
        if (href.includes("?tab=backtests")) {
            return pathname === "/scanner/backtests" && currentTab === "backtests";
        }
        if (href.includes("?tab=bots")) {
            return pathname === "/scanner/backtests" && currentTab === "bots";
        }
        if (href.includes("?tab=similarity")) {
            return pathname === "/scanner/backtests" && currentTab === "similarity";
        }
        return activePath ? pathname === activePath : pathname === href;
    };

    const handleSymbolSelect = (symbol: string) => {
        setSearchQuery("");
        setSearchModalOpen(false);
        setMobileMenuOpen(false);
        const baseSym = symbol.split('.')[0].toLowerCase();
        router.push(`/stocks/${baseSym}`);
    };

    if (pathname === "/antigrafity" || pathname?.startsWith("/antigrafity") || pathname === "/chat" || pathname?.startsWith("/chat")) {
        return null;
    }

    return (
        <>
        <header ref={headerRef} className="fixed top-0 left-0 right-0 z-[100] w-full border-b-4 border-black dark:border-white bg-white dark:bg-zinc-950 header-stable" dir="ltr">
            <div ref={shellRef} className="mx-auto max-w-[1800px] w-full px-3 sm:px-4 md:px-6 py-2.5 flex items-center justify-between gap-2 md:gap-3">
                {/* Brand */}
                <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                    {/* Hanging Palestine Watermelon Pennant next to site logo */}
                    <div
                        title={language === "ar" ? "في القلب يا فلسطين" : "Standing with Palestine"}
                        aria-label={language === "ar" ? "تضامناً مع إخوتنا في فلسطين" : "Standing in solidarity with Palestine"}
                        className="pointer-events-none select-none -mt-3 -mb-1 h-[54px] sm:h-[60px] w-6 sm:w-7 shrink-0 flex items-start drop-shadow-[0_3px_6px_rgba(0,0,0,0.28)]"
                    >
                        <img
                            src="/palestine-watermelon.svg?v=3"
                            alt={language === "ar" ? "فلسطين" : "Palestine"}
                            width={28}
                            height={60}
                            className="w-full h-full object-contain object-top block"
                        />
                    </div>
                    <Link href="/" className="group flex items-center gap-2 sm:gap-2.5 min-w-0">
                        <div className="relative bg-white p-1 rounded-none border-4 border-black dark:border-white transition-all duration-300 group-hover:scale-110 group-hover:rotate-6 flex-shrink-0 flex items-center justify-center shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.5)]">
                                <Image
                                    src="/favicon_io/apple-touch-icon.png"
                                    alt="EGX Bots logo"
                                    width={32}
                                    height={32}
                                    className="object-contain w-7 h-7 sm:w-8 sm:h-8"
                                    priority
                                />
                            </div>
                            <div className="hidden min-[420px]:flex flex-col shrink-0 header-title">
                                <span className="text-sm sm:text-base font-black tracking-tight text-black dark:text-white leading-tight truncate uppercase animate-in slide-in-from-left-2 duration-700">
                                    {t("app.title")}
                                </span>
                                <span className="text-[9px] sm:text-[10px] uppercase tracking-[0.18em] font-black text-black/70 dark:text-white/70 leading-none truncate hidden sm:block">
                                    {t("header.pro_analysis")}
                                </span>
                            </div>
                        </Link>
                    </div>

                    {/* Center: nav */}
                    <div className="flex-1 min-w-0 flex items-center justify-center overflow-x-auto no-scrollbar px-1">
                        <nav className="hidden md:flex items-center gap-1 py-1 px-1 rounded-xl shrink-0 animate-in fade-in duration-700 delay-200">
                            {navItems.map((item, idx) => {
                                const isActive = checkActive(item.href, item.activePath);
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={`relative flex items-center justify-center gap-1.5 rounded-lg px-2 lg:px-2.5 py-1.5 text-[10px] font-black uppercase tracking-wider transition-all duration-300 whitespace-nowrap border-3 animate-in fade-in duration-500 ${
                                            isActive
                                                ? "bg-black dark:bg-white !text-white dark:!text-black shadow-[4px_4px_0px_0px_rgba(0,0,0,0.3)] dark:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.5)] border-black dark:border-white scale-105"
                                                : "bg-white dark:bg-zinc-900 text-black dark:text-white border-black/30 dark:border-white/30 hover:scale-105 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,0.3)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.3)]"
                                        }`}
                                        title={item.label}
                                        style={{
                                            animationDelay: `${300 + idx * 50}ms`,
                                            color: isActive ? (theme === "dark" ? "#000000" : "#ffffff") : undefined
                                        }}
                                    >
                                        {item.icon}
                                        <span className="hidden 2xl:inline-flex items-center gap-1.5">
                                            {item.label}
                                            {item.badge && (
                                                <span className="px-1 py-0.5 rounded-[4px] bg-[#ff6b6b] text-white text-[8px] font-black uppercase tracking-normal border-2 border-black dark:border-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                                                    {item.badge}
                                                </span>
                                            )}
                                        </span>
                                        {isActive && (
                                            <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[#ff6b6b] dark:bg-[#4ecdc4] border-2 border-black dark:border-white animate-pulse" />
                                        )}
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 md:gap-1.5 shrink-0 animate-in fade-in duration-700 delay-300">
                        <MarketSwitcher
                            market={market}
                            setMarket={setMarket}
                            language={language}
                            variant="bar"
                        />

                        <button
                            id="header-global-search-btn"
                            type="button"
                            onClick={() => {
                                setMobileMenuOpen(false);
                                setSearchModalOpen(true);
                                setTimeout(() => document.getElementById("global-stock-search-input")?.focus(), 40);
                            }}
                            className="h-9 px-2.5 flex items-center justify-center gap-1.5 rounded-xl bg-white dark:bg-zinc-900 border-3 border-black dark:border-white text-black dark:text-white hover:bg-[#FFE600] hover:text-black hover:scale-105 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] transition-all duration-200 cursor-pointer shrink-0"
                            aria-label={language === "ar" ? "بحث عن سهم" : "Search stocks"}
                            title={language === "ar" ? "ابحث عن أي سهم (اختصار /)" : "Search stocks (Press /)"}
                        >
                            <Search className="h-4 w-4 shrink-0" />
                            <span className="hidden xl:inline text-[11px] font-black">
                                {language === "ar" ? "بحث" : "Search"}
                            </span>
                            <kbd className="hidden xl:inline px-1 py-0.2 rounded text-[9px] font-mono bg-black/10 dark:bg-white/10 border border-black/20 dark:border-white/20">
                                /
                            </kbd>
                        </button>

                        <button
                            type="button"
                            onClick={() => setProfitGuideOpen(true)}
                            className="hidden lg:flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-black bg-gradient-to-r from-amber-400 to-yellow-400 text-black border-3 border-black dark:border-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:scale-105 active:scale-95 transition-all cursor-pointer"
                            title={language === "ar" ? "دليل الربح في 60 ثانية" : "60s Profit Guide"}
                        >
                            <Sparkles className="h-3.5 w-3.5 fill-black shrink-0" />
                            <span>{language === "ar" ? "كيف أربح؟" : "How to Profit?"}</span>
                        </button>

                        <button
                            onClick={toggleTheme}
                            className="hidden md:flex items-center justify-center h-9 w-9 rounded-xl transition-all bg-white dark:bg-zinc-900 border-3 border-black dark:border-white text-black dark:text-white hover:scale-110 hover:rotate-12 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.3)] duration-200"
                            aria-label="Toggle theme"
                        >
                            {theme === "dark" ? <Sun className="h-4 w-4 animate-spin" style={{ animationDuration: '3s' }} /> : <Moon className="h-4 w-4" />}
                        </button>

                        <button
                            onClick={() => setLanguage(language === "ar" ? "en" : "ar")}
                            className="hidden md:flex items-center justify-center gap-1.5 h-9 px-2 rounded-xl text-xs font-black w-9 xl:w-[4.5rem] bg-white dark:bg-zinc-900 border-3 border-black dark:border-white text-black dark:text-white hover:scale-110 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[4px_4px_0px_0px_rgba(255,255,255,0.3)] transition-all duration-200"
                            title={language === "ar" ? "Switch to English" : "تغيير إلى العربية"}
                        >
                            <Globe className="h-4 w-4 shrink-0" />
                            <span className="hidden xl:inline">{language === "ar" ? "EN" : "AR"}</span>
                        </button>

                        {user ? (
                            <>
                                <PortfolioHeaderChip />
                                <div className="relative hidden md:block">
                                <button
                                    onClick={() => setAccountMenuOpen(!accountMenuOpen)}
                                    className={`h-9 px-2.5 rounded-xl transition-all ${
                                        accountMenuOpen ? "app-panel text-white" : "app-icon-button hover:text-white"
                                    } flex items-center gap-1.5`}
                                >
                                    <div className="w-5 h-5 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-800 flex items-center justify-center border border-white/10">
                                        <User className="h-3 w-3" />
                                    </div>
                                    <ChevronDown className={`h-3 w-3 transition-transform ${accountMenuOpen ? "rotate-180" : ""}`} />
                                </button>

                                {accountMenuOpen && (
                                    <div className="app-panel-strong absolute right-0 mt-2 w-56 p-1.5 rounded-2xl animate-in fade-in slide-in-from-top-2 duration-200 z-[110]">
                                        <div className="px-3 py-2 mb-1 border-b border-white/5">
                                            <p className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">{t("account.label")}</p>
                                            <p className="text-xs font-medium text-zinc-300 truncate">{user.email}</p>
                                        </div>
                                        <Link href="/profile" className="flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-zinc-400 hover:text-white hover:bg-white/5 rounded-xl transition-all">
                                            <User className="h-4 w-4" />
                                            {t("nav.profile")}
                                        </Link>
                                        <Link href="/profile#portfolio" onClick={() => setAccountMenuOpen(false)} className="flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-emerald-400 hover:text-white hover:bg-white/5 rounded-xl transition-all">
                                            <Wallet className="h-4 w-4 text-emerald-400" />
                                            {language === "ar" ? "المحفظة الاستثمارية" : "My Portfolio"}
                                        </Link>
                                        <Link href="/b2b/dashboard" onClick={() => setAccountMenuOpen(false)} className="flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-emerald-400 hover:text-white hover:bg-white/5 rounded-xl transition-all">
                                            <Bot className="h-4 w-4 text-emerald-400" />
                                            {language === "ar" ? "لوحة ترخيص البوت (B2B)" : "B2B Bot Dashboard"}
                                        </Link>
                                        <button
                                            onClick={() => { setAccountMenuOpen(false); void signOut(); }}
                                            className="flex w-full items-center gap-2 px-3 py-2.5 text-sm font-medium text-red-400 hover:bg-red-500/10 rounded-xl transition-all"
                                        >
                                            <X className="h-4 w-4" />
                                            {t("auth.logout")}
                                        </button>
                                    </div>
                                )}
                            </div>
                            </>
                        ) : (
                            <Link
                                href="/login"
                                className="app-primary-action hidden md:flex h-9 px-3 md:px-5 items-center rounded-xl text-[10px] md:text-xs font-bold uppercase tracking-wider transition-all whitespace-nowrap"
                            >
                                {t("auth.login")}
                            </Link>
                        )}

                        <button
                            onClick={() => {
                                setMobileMenuOpen(!mobileMenuOpen);
                                if (!mobileMenuOpen) {
                                    setSearchModalOpen(false);
                                }
                            }}
                            className="app-icon-button md:hidden h-9 w-9 flex items-center justify-center rounded-xl hover:bg-white/10 transition-all"
                            aria-label="Toggle menu"
                        >
                            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                        </button>
                    </div>

            </div>

            {/* Global Stock Search Dialog (Centered above page, never squished inside header) */}
            {searchModalOpen && (
                <div
                    className="fixed inset-0 z-[130] bg-black/70 backdrop-blur-sm flex items-start justify-center pt-16 sm:pt-24 px-4"
                    onClick={() => setSearchModalOpen(false)}
                    dir={language === "ar" ? "rtl" : "ltr"}
                >
                    <div
                        className="w-full max-w-xl bg-white dark:bg-zinc-950 border-4 border-black dark:border-white shadow-[8px_8px_0px_0px_#FFE600] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between px-4 py-2.5 bg-black text-white border-b-2 border-black dark:border-white/20">
                            <span className="text-xs font-black uppercase tracking-wider flex items-center gap-2 text-[#FFE600]">
                                <Search className="w-4 h-4" />
                                {language === "ar"
                                    ? isSaudi
                                        ? "البحث السريع في أسهم تداول السعودي"
                                        : "البحث السريع في أسهم البورصة المصرية"
                                    : isSaudi
                                      ? "Quick Search • TASI"
                                      : "Quick Search • EGX"}
                            </span>
                            <button
                                type="button"
                                onClick={() => setSearchModalOpen(false)}
                                className="p-1 text-zinc-300 hover:text-[#FFE600] cursor-pointer"
                                aria-label="Close search"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        <div className="p-3 sm:p-4">
                            <div className="relative flex items-center">
                                <Search className={`absolute ${language === "ar" ? "right-3.5" : "left-3.5"} w-4 h-4 text-zinc-500 pointer-events-none`} />
                                <input
                                    id="global-stock-search-input"
                                    type="text"
                                    placeholder={
                                        language === "ar"
                                            ? isSaudi
                                                ? "اكتب اسم الشركة أو رمز السهم السعودي (مثل 2222 أو الراجحي)..."
                                                : "اكتب اسم الشركة أو كود السهم المصري (مثل COMI أو فوري)..."
                                            : isSaudi
                                              ? "Type TASI symbol or company name (e.g. 2222)..."
                                              : "Type EGX symbol or company name (e.g. COMI, FWRY)..."
                                    }
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className={`h-12 w-full rounded-none ${language === "ar" ? "pr-10 pl-10" : "pl-10 pr-10"} text-sm font-black outline-none border-3 border-black bg-zinc-50 text-black dark:bg-zinc-900 dark:text-white dark:border-white focus:bg-[#FFE600] focus:text-black transition-none`}
                                    autoFocus
                                />
                                {searchQuery && (
                                    <button
                                        type="button"
                                        onClick={() => setSearchQuery("")}
                                        className={`absolute ${language === "ar" ? "left-3" : "right-3"} p-1 text-zinc-500 hover:text-black dark:hover:text-white cursor-pointer`}
                                    >
                                        <X className="w-4 h-4" />
                                    </button>
                                )}
                            </div>

                            <div className="mt-3 max-h-[55vh] overflow-y-auto custom-scrollbar border border-black/15 dark:border-white/15">
                                <SearchDropdown
                                    language={language}
                                    isSaudi={isSaudi}
                                    searchQuery={searchQuery}
                                    searching={searching}
                                    searchResults={searchResults}
                                    onSelect={handleSymbolSelect}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            )}

                {/* Mobile menu */}
                {mobileMenuOpen && (
                    <>
                        <div
                            className="md:hidden fixed inset-0 z-[90] bg-black/60 backdrop-blur-sm"
                            onClick={() => setMobileMenuOpen(false)}
                            aria-hidden="true"
                        />
                        <div className="md:hidden fixed top-0 left-0 right-0 z-[101] bg-white dark:bg-zinc-950 border-b-4 border-black dark:border-white animate-in slide-in-from-top-2 duration-200 overflow-hidden max-h-[85vh] overflow-y-auto">
                            {/* Mobile menu header */}
                            <div className="flex items-center justify-between px-4 py-3 border-b-2 border-zinc-200 dark:border-zinc-800">
                                <span className="text-sm font-black uppercase tracking-wider text-black dark:text-white">Menu</span>
                                <button
                                    onClick={() => setMobileMenuOpen(false)}
                                    className="h-10 w-10 flex items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-black dark:border-zinc-600 active:scale-95 transition-transform"
                                    aria-label="Close menu"
                                >
                                    <X className="h-5 w-5 text-black dark:text-white" />
                                </button>
                            </div>

                            <MarketSwitcher
                                market={market}
                                setMarket={setMarket}
                                language={language}
                                variant="drawer"
                            />

                            {/* Nav links */}
                            <div className="px-3 py-2 flex flex-col gap-1">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setMobileMenuOpen(false);
                                        setProfitGuideOpen(true);
                                    }}
                                    className="flex items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-black tracking-wide bg-gradient-to-r from-amber-400 to-yellow-400 text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:scale-95 transition-all text-right"
                                >
                                    <Sparkles className="w-4 h-4 fill-black shrink-0" />
                                    <span>{language === "ar" ? "كيف أربح؟ (دليل 60 ثانية)" : "How to Profit? (60s Guide)"}</span>
                                </button>
                                {navItems.map((item) => {
                                    const isActive = checkActive(item.href, item.activePath);
                                    return (
                                        <Link
                                            key={item.href}
                                            href={item.href}
                                            onClick={() => setMobileMenuOpen(false)}
                                            className={`flex items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-bold tracking-wide transition-all ${
                                                isActive 
                                                    ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-2 border-amber-500/30" 
                                                    : "text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border-2 border-transparent"
                                            }`}
                                        >
                                            {item.icon}
                                            <span className="flex items-center gap-2">
                                                {item.label}
                                                {item.badge && (
                                                    <span className="px-1.5 py-0.5 rounded-md bg-indigo-600 text-white text-[9px] font-black uppercase">
                                                        {item.badge}
                                                    </span>
                                                )}
                                            </span>
                                        </Link>
                                    );
                                })}
                            </div>

                            {/* Divider */}
                            <div className="h-px bg-zinc-200 dark:bg-zinc-800 mx-4" />

                            {/* Bottom actions */}
                            <div className="flex items-center gap-2 p-3">
                                <button onClick={toggleTheme} className="flex items-center justify-center h-11 w-11 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 active:scale-95 transition-transform" aria-label="Toggle theme">
                                    {theme === "dark" ? <Sun className="h-4 w-4 text-amber-500" /> : <Moon className="h-4 w-4 text-zinc-600" />}
                                </button>
                                <button
                                    onClick={() => setLanguage(language === "ar" ? "en" : "ar")}
                                    className="flex items-center gap-2 h-11 px-4 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-sm font-bold flex-1 justify-center text-black dark:text-white active:scale-95 transition-transform"
                                >
                                    <Globe className="h-4 w-4" />
                                    <span>{language === "ar" ? "English" : "العربية"}</span>
                                </button>
                                {!user ? (
                                    <Link href="/login" onClick={() => setMobileMenuOpen(false)} className="flex items-center justify-center h-11 px-5 rounded-xl bg-amber-500 text-black text-sm font-black uppercase flex-1 border-2 border-black active:scale-95 transition-transform shadow-[3px_3px_0px_0px_#000]">
                                        {t("auth.login")}
                                    </Link>
                                ) : (
                                    <>
                                        <Link href="/profile" onClick={() => setMobileMenuOpen(false)} className="flex items-center justify-center h-11 px-4 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-zinc-300 dark:border-zinc-700 text-sm font-bold flex-1 text-black dark:text-white active:scale-95 transition-transform">
                                            <User className="h-4 w-4" />
                                        </Link>
                                        <button onClick={() => signOut()} className="flex items-center justify-center h-11 px-4 rounded-xl bg-red-500/10 text-red-500 border-2 border-red-500/30 text-sm font-bold flex-1 active:scale-95 transition-transform">
                                            {t("auth.logout")}
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>
                    </>
                )}
        </header>
        <QuickProfitGuideModal
            isOpen={profitGuideOpen}
            onClose={() => setProfitGuideOpen(false)}
        />
        </>
    );
}
