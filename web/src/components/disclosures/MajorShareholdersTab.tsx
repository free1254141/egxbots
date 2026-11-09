"use client";

import React, { useState } from "react";
import { CompanyOwnershipStructure, getSymbolSector } from "@/lib/disclosures-analytics";
import { Users, Search, ArrowUpRight, ArrowDownRight, Minus, FileText, Sparkles, Layers } from "lucide-react";
import StockLogo from "@/components/StockLogo";

interface MajorShareholdersTabProps {
  companies: CompanyOwnershipStructure[];
  isAr: boolean;
  onOpenPdfModal?: (item: any) => void;
  onSelectSymbol?: (symbol: string) => void;
}

export default function MajorShareholdersTab({
  companies,
  isAr,
  onSelectSymbol,
}: MajorShareholdersTabProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [changeFilter, setChangeFilter] = useState<"all" | "increase" | "decrease">("all");

  const filteredCompanies = companies.filter((comp) => {
    const matchesSearch =
      searchTerm.trim() === "" ||
      comp.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      comp.company_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      comp.shareholders.some((sh) => sh.party_name.toLowerCase().includes(searchTerm.toLowerCase()));

    if (!matchesSearch) return false;

    if (changeFilter === "increase") {
      return comp.shareholders.some((sh) => sh.change_direction === "increase");
    }
    if (changeFilter === "decrease") {
      return comp.shareholders.some((sh) => sh.change_direction === "decrease");
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Search and Filter Controls */}
      <div className="rounded-none border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-4 sm:p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors">
        <div className={`flex flex-col md:flex-row md:items-center md:justify-between gap-4 ${isAr ? "md:flex-row-reverse text-right" : ""}`}>
          <div>
            <div className="flex items-center gap-2">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-none bg-[#FFE600] text-black border-2 border-black shadow-[2px_2px_0px_#000]">
                <Users className="h-5 w-5" />
              </div>
              <h3 className="text-base sm:text-lg font-black text-black dark:text-white">
                {isAr ? "سجل كبار المساهمين والمؤسسين (نماذج المادة 30)" : "Major Shareholders & Ownership Registry (Article 30)"}
              </h3>
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1 font-bold">
              {isAr
                ? "تتبع ملكيات المؤسسين، الصناديق الاستثمارية، وكبار الملاك (5% فأكثر) ونسب التداول الحر للشركات المقيدة"
                : "Track stakes of founders, institutional funds, 5%+ holders, and corporate free float"}
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            {/* Search Input */}
            <div className="relative min-w-[240px]">
              <Search className={`absolute top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 ${isAr ? "right-3" : "left-3"}`} />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder={isAr ? "ابحث باسم المساهم أو الشركة أو الرمز..." : "Search shareholder or symbol..."}
                className={`w-full py-2 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-white/20 text-xs font-bold text-black dark:text-white placeholder-zinc-500 focus:outline-none focus:bg-[#FFE600] focus:text-black transition-colors ${
                  isAr ? "pr-9 pl-3 text-right" : "pl-9 pr-3"
                }`}
              />
            </div>

            {/* Filter Buttons */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setChangeFilter("all")}
                className={`px-3 py-2 text-xs font-black border-2 border-black transition-all cursor-pointer ${
                  changeFilter === "all"
                    ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_#000]"
                    : "bg-white text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 hover:bg-[#FFE600] hover:text-black"
                }`}
              >
                {isAr ? "الكل" : "All"}
              </button>
              <button
                type="button"
                onClick={() => setChangeFilter("increase")}
                className={`px-3 py-2 text-xs font-black border-2 border-black transition-all flex items-center gap-1 cursor-pointer ${
                  changeFilter === "increase"
                    ? "bg-[#00FF66] text-black shadow-[2px_2px_0px_#000]"
                    : "bg-white text-emerald-800 dark:bg-zinc-900 dark:text-emerald-400 hover:bg-emerald-50"
                }`}
              >
                <ArrowUpRight className="w-3.5 h-3.5" />
                <span>{isAr ? "زيادة حصة" : "Increased"}</span>
              </button>
              <button
                type="button"
                onClick={() => setChangeFilter("decrease")}
                className={`px-3 py-2 text-xs font-black border-2 border-black transition-all flex items-center gap-1 cursor-pointer ${
                  changeFilter === "decrease"
                    ? "bg-[#FF3366] text-white shadow-[2px_2px_0px_#000]"
                    : "bg-white text-rose-800 dark:bg-zinc-900 dark:text-rose-400 hover:bg-rose-50"
                }`}
              >
                <ArrowDownRight className="w-3.5 h-3.5" />
                <span>{isAr ? "تخفيض حصة" : "Decreased"}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Companies List */}
      {filteredCompanies.length === 0 ? (
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-12 text-center text-zinc-500 font-bold text-sm shadow-[6px_6px_0px_0px_rgba(0,0,0,1)]">
          {isAr
            ? "لا توجد نتائج مطابقة لبحثك في سجل كبار المساهمين حالياً."
            : "No records matching your search in the major shareholders registry."}
        </div>
      ) : (
        <div className="space-y-5">
          {filteredCompanies.map((comp) => {
            return (
              <div
                key={comp.symbol}
                className="border-4 border-black dark:border-white bg-white dark:bg-zinc-950 p-5 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] dark:shadow-[6px_6px_0px_0px_rgba(255,255,255,0.3)] text-black dark:text-white transition-colors"
              >
                {/* Company Header */}
                <div className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b-2 border-black/15 dark:border-white/10 pb-4 mb-4 ${isAr ? "sm:flex-row-reverse text-right" : ""}`}>
                  <div className={`flex items-center gap-3 ${isAr ? "flex-row-reverse" : ""}`}>
                    <StockLogo symbol={comp.symbol} size="md" />
                    <div>
                      <div className="flex items-center gap-2">
                        {onSelectSymbol ? (
                          <button
                            type="button"
                            onClick={() => onSelectSymbol(comp.symbol)}
                            className="font-black text-base sm:text-lg text-black dark:text-white hover:text-amber-500 dark:hover:text-amber-400 underline decoration-2 cursor-pointer text-left"
                            title={isAr ? "اضغط لفتح بطاقة التحليل الشامل للسهم" : "Click to open deep-dive"}
                          >
                            {comp.symbol}
                          </button>
                        ) : (
                          <span className="font-black text-base sm:text-lg text-black dark:text-white">
                            {comp.symbol}
                          </span>
                        )}
                        <span className="px-2 py-0.5 text-[10px] font-black uppercase tracking-wider bg-[#FFE600] text-black border border-black shadow-[1px_1px_0px_#000]">
                          {isAr ? (comp.sector?.ar || getSymbolSector(comp.symbol).ar) : (comp.sector?.en || getSymbolSector(comp.symbol).en)}
                        </span>
                        <span className="text-zinc-700 dark:text-zinc-300 text-sm font-bold">
                          — {comp.company_name}
                        </span>
                      </div>
                      <span className="text-[11px] text-zinc-500 font-bold block mt-0.5">
                        {isAr ? `تاريخ الإفصاح المعتمد: ${comp.last_updated}` : `Filing Date: ${comp.last_updated}`}
                      </span>
                    </div>
                  </div>

                  <div className={`flex items-center gap-2.5 ${isAr ? "flex-row-reverse" : ""}`}>
                    {comp.free_float_pct != null && (
                      <div className={`flex flex-col ${isAr ? "items-start sm:items-end text-right" : "items-start text-left"} gap-1`}>
                        <span className="px-3 py-1 border-2 border-black bg-amber-300 text-black text-xs font-black shadow-[2px_2px_0px_#000]">
                          {isAr
                            ? `الأسهم الحرة: ${comp.free_float_pct}%${
                                comp.free_float_shares
                                  ? ` (${(comp.free_float_shares >= 1_000_000 ? (comp.free_float_shares / 1_000_000).toFixed(1) + "M سهم" : (comp.free_float_shares / 1000).toFixed(0) + "k سهم")})`
                                  : ""
                              }`
                            : `Free Float: ${comp.free_float_pct}%${
                                comp.free_float_shares
                                  ? ` (${(comp.free_float_shares >= 1_000_000 ? (comp.free_float_shares / 1_000_000).toFixed(1) + "M" : (comp.free_float_shares / 1000).toFixed(0) + "k")})`
                                  : ""
                              }`}
                        </span>
                        {comp.locked_pct != null && (
                          <span className="text-[10px] font-bold text-zinc-500">
                            {isAr
                              ? `مجمد للمؤسسين: ${comp.locked_pct}%`
                              : `Strategic Locked: ${comp.locked_pct}%`}
                          </span>
                        )}
                      </div>
                    )}

                    {onSelectSymbol && (
                      <button
                        type="button"
                        onClick={() => onSelectSymbol(comp.symbol)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-black border-2 border-black bg-black text-white dark:bg-white dark:text-black hover:bg-[#FFE600] hover:text-black dark:hover:bg-[#FFE600] dark:hover:text-black transition-colors cursor-pointer shadow-[2px_2px_0px_#000]"
                      >
                        <Layers className="w-3.5 h-3.5" />
                        <span>{isAr ? "تحليل شامل للسهم 🔍" : "Stock Deep-Dive 🔍"}</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Shareholders Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-right border-collapse">
                    <thead>
                      <tr className="border-b-2 border-black/20 dark:border-white/10 text-zinc-700 dark:text-zinc-400 font-black">
                        <th className="py-2.5 px-3">{isAr ? "اسم المساهم / الجهة" : "Shareholder / Entity"}</th>
                        <th className="py-2.5 px-3">{isAr ? "الصفة القانونية" : "Role"}</th>
                        <th className="py-2.5 px-3 text-center">{isAr ? "الحصة الحالية" : "Current Stake"}</th>
                        <th className="py-2.5 px-3 text-center">{isAr ? "الحصة السابقة" : "Prior Stake"}</th>
                        <th className="py-2.5 px-3 text-center">{isAr ? "التغير" : "Change"}</th>
                        <th className="py-2.5 px-3 text-center">{isAr ? "المستند" : "Filing"}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/10 dark:divide-white/5 font-bold">
                      {comp.shareholders.map((sh, idx) => {
                        const isInc = sh.change_direction === "increase";
                        const isDec = sh.change_direction === "decrease";

                        return (
                          <tr key={idx} className="hover:bg-zinc-100 dark:hover:bg-white/[0.03] transition-colors">
                            <td className="py-3 px-3 font-black text-black dark:text-white max-w-[220px] truncate" title={sh.party_name}>
                              {sh.party_name}
                            </td>
                            <td className="py-3 px-3 text-zinc-600 dark:text-zinc-400">
                              <span className="px-2 py-0.5 border border-black dark:border-white/20 bg-zinc-100 dark:bg-zinc-900 text-[10px]">
                                {sh.party_role || (isAr ? "مساهم رئيسي" : "Major Holder")}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-center font-mono font-black text-sm text-black dark:text-white">
                              {sh.stake_after != null ? `${sh.stake_after}%` : "-"}
                            </td>
                            <td className="py-3 px-3 text-center font-mono text-zinc-500">
                              {sh.stake_before != null ? `${sh.stake_before}%` : "-"}
                            </td>
                            <td className="py-3 px-3 text-center">
                              {isInc && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 border border-black bg-[#00FF66] text-black font-black text-[11px] shadow-[1px_1px_0px_#000]">
                                  <ArrowUpRight className="w-3 h-3" />
                                  <span>+{sh.change_amount_pct}%</span>
                                </span>
                              )}
                              {isDec && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 border border-black bg-[#FF3366] text-white font-black text-[11px] shadow-[1px_1px_0px_#000]">
                                  <ArrowDownRight className="w-3 h-3" />
                                  <span>-{sh.change_amount_pct}%</span>
                                </span>
                              )}
                              {!isInc && !isDec && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 border border-black dark:border-zinc-700 bg-zinc-200 dark:bg-zinc-900 text-zinc-800 dark:text-zinc-300 text-[10px]">
                                  <Minus className="w-3 h-3" />
                                  <span>{isAr ? "ثبات" : "Stable"}</span>
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-3 text-center">
                              {sh.source_url ? (
                                <a
                                  href={sh.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 px-2.5 py-1 border border-black bg-[#FFE600] text-black text-[11px] font-black shadow-[2px_2px_0px_#000] hover:bg-white transition-colors"
                                >
                                  <FileText className="w-3 h-3" />
                                  <span>PDF</span>
                                </a>
                              ) : (
                                <span className="text-zinc-500 text-[11px]">-</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Subtitle / Key Takeaway if available */}
                {comp.shareholders[0]?.title && (
                  <div className="mt-3.5 pt-3 border-t border-black/10 dark:border-white/10 text-[11px] font-bold text-zinc-600 dark:text-zinc-400 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                    <span>{comp.shareholders[0].title}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
