"use client";

import { useState, useMemo } from "react";
import {
  X,
  DollarSign,
  Search,
  Copy,
  Check,
  CreditCard,
  Smartphone,
  Calendar,
  ShieldCheck,
  TrendingUp,
  Receipt,
  ExternalLink,
} from "lucide-react";
import { toast } from "sonner";

export interface ApprovedOrder {
  id: string;
  user_id: string;
  plan_id: string;
  amount_egp: number;
  net_egp: number;
  provider: string;
  customer_note?: string | null;
  created_at: string;
  email?: string | null;
  display_name?: string | null;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  orders: ApprovedOrder[];
  totalRevenue: number;
  totalPaidOrders: number;
  isAr?: boolean;
}

export default function RevenueDetailsModal({
  isOpen,
  onClose,
  orders = [],
  totalRevenue,
  totalPaidOrders,
  isAr = true,
}: Props) {
  const [search, setSearch] = useState("");
  const [selectedProvider, setSelectedProvider] = useState<string>("all");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const grossTotal = useMemo(() => {
    return orders.reduce((sum, o) => sum + (Number(o.amount_egp) || 0), 0);
  }, [orders]);

  const feeTotal = useMemo(() => {
    return Math.round((grossTotal - totalRevenue) * 100) / 100;
  }, [grossTotal, totalRevenue]);

  const filteredOrders = useMemo(() => {
    let list = orders;
    if (selectedProvider !== "all") {
      list = list.filter((o) => {
        const prov = (o.provider || "").toLowerCase();
        if (selectedProvider === "easykash") return prov.includes("easykash");
        if (selectedProvider === "vodafone_cash") return prov.includes("vodafone") || prov.includes("wallet");
        if (selectedProvider === "instapay") return prov.includes("insta");
        if (selectedProvider === "kashier") return prov.includes("kashier");
        return prov === selectedProvider;
      });
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((o) => {
        return (
          (o.email || "").toLowerCase().includes(q) ||
          (o.display_name || "").toLowerCase().includes(q) ||
          (o.id || "").toLowerCase().includes(q) ||
          (o.customer_note || "").toLowerCase().includes(q) ||
          (o.provider || "").toLowerCase().includes(q)
        );
      });
    }

    return list;
  }, [orders, selectedProvider, search]);

  const handleCopy = (id: string, text: string) => {
    try {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      toast.success(isAr ? "تم النسخ" : "Copied");
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error(isAr ? "فشل النسخ" : "Failed to copy");
    }
  };

  if (!isOpen) return null;

  const formatCairoDate = (dateStr: string) => {
    if (!dateStr) return "—";
    try {
      const d = new Date(dateStr);
      return new Intl.DateTimeFormat(isAr ? "ar-EG" : "en-US", {
        timeZone: "Africa/Cairo",
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d);
    } catch {
      return dateStr.slice(0, 16);
    }
  };

  const providerBadge = (provider: string) => {
    const p = (provider || "").toLowerCase();
    if (p.includes("easykash")) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200 border border-black font-black text-[10px]">
          <CreditCard className="w-3 h-3 text-blue-600" />
          EasyKash
        </span>
      );
    }
    if (p.includes("vodafone") || p.includes("wallet")) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200 border border-black font-black text-[10px]">
          <Smartphone className="w-3 h-3 text-rose-600" />
          فودافون كاش
        </span>
      );
    }
    if (p.includes("insta")) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-100 text-purple-900 dark:bg-purple-950 dark:text-purple-200 border border-black font-black text-[10px]">
          <Smartphone className="w-3 h-3 text-purple-600" />
          InstaPay
        </span>
      );
    }
    if (p.includes("kashier")) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200 border border-black font-black text-[10px]">
          <CreditCard className="w-3 h-3 text-emerald-600" />
          Kashier
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200 border border-black font-black text-[10px]">
        {provider || "أخرى"}
      </span>
    );
  };

  return (
    <div
      dir={isAr ? "rtl" : "ltr"}
      className="fixed inset-0 z-[10000] flex items-center justify-center p-3 sm:p-5 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-4xl bg-white dark:bg-zinc-950 border-4 border-black dark:border-white shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#10b981] overflow-hidden max-h-[92vh] flex flex-col">
        {/* Modal Header */}
        <div className="bg-gradient-to-r from-emerald-500 via-teal-500 to-emerald-600 text-black px-4 sm:px-6 py-4 border-b-4 border-black flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-black text-emerald-400 flex items-center justify-center border-2 border-black shadow-[2px_2px_0px_#000]">
              <DollarSign className="w-6 h-6" />
            </div>
            <div>
              <span className="inline-block px-2 py-0.5 bg-black text-emerald-400 text-[10px] font-black uppercase tracking-wider mb-0.5">
                {isAr ? "سجل الإيرادات المؤكدة" : "REVENUE LEDGER"}
              </span>
              <h2 className="text-lg sm:text-xl font-black text-black leading-tight">
                {isAr ? "تفاصيل الإيرادات والطلبات المؤكدة" : "Revenue & Confirmed Orders Details"}
              </h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 bg-black text-white hover:bg-zinc-800 flex items-center justify-center border-2 border-black transition-colors shadow-[2px_2px_0px_rgba(0,0,0,0.5)]"
            aria-label={isAr ? "إغلاق" : "Close"}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="p-4 sm:p-6 space-y-5 overflow-y-auto">
          {/* 4 Summary Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 shadow-[3px_3px_0px_#000]">
              <span className="text-[10px] font-black text-zinc-500 dark:text-zinc-400 uppercase tracking-wider block">
                {isAr ? "إجمالي المحصّل (Gross)" : "Gross Revenue"}
              </span>
              <div className="text-lg sm:text-xl font-black font-mono text-zinc-900 dark:text-white mt-0.5">
                {grossTotal.toLocaleString("en-US", { minimumFractionDigits: 2 })} <span className="text-xs font-normal">ج.م</span>
              </div>
            </div>

            <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border-2 border-black dark:border-zinc-700 shadow-[3px_3px_0px_#000]">
              <span className="text-[10px] font-black text-rose-600 dark:text-rose-400 uppercase tracking-wider block">
                {isAr ? "عمولة البوابات (-4%)" : "Gateway Fee (4%)"}
              </span>
              <div className="text-lg sm:text-xl font-black font-mono text-rose-700 dark:text-rose-300 mt-0.5">
                -{feeTotal.toLocaleString("en-US", { minimumFractionDigits: 2 })} <span className="text-xs font-normal">ج.م</span>
              </div>
            </div>

            <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border-2 border-emerald-600 dark:border-emerald-500 shadow-[3px_3px_0px_#059669]">
              <span className="text-[10px] font-black text-emerald-800 dark:text-emerald-300 uppercase tracking-wider block">
                {isAr ? "صافي الإيرادات (Net)" : "Net Revenue"}
              </span>
              <div className="text-lg sm:text-xl font-black font-mono text-emerald-950 dark:text-emerald-100 mt-0.5">
                {totalRevenue.toLocaleString("en-US", { minimumFractionDigits: 2 })} <span className="text-xs font-normal">ج.م</span>
              </div>
            </div>

            <div className="p-3 bg-blue-50 dark:bg-blue-950/40 border-2 border-black dark:border-zinc-700 shadow-[3px_3px_0px_#000]">
              <span className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-wider block">
                {isAr ? "الطلبات المؤكدة" : "Confirmed Orders"}
              </span>
              <div className="text-lg sm:text-xl font-black font-mono text-blue-900 dark:text-blue-200 mt-0.5">
                {orders.length} <span className="text-xs font-normal">{isAr ? "طلب مؤكد" : "orders"}</span>
              </div>
            </div>
          </div>

          {/* Search & Filter Bar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-zinc-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={isAr ? "ابحث بالبريد، الاسم، كود الطلب، وسيلة الدفع..." : "Search email, order ID, provider..."}
                className="w-full ps-9 pe-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-900 border-2 border-black dark:border-zinc-700 font-bold focus:outline-hidden"
              />
            </div>

            {/* Provider Filter Tabs */}
            <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
              {[
                { id: "all", label: isAr ? `الكل (${orders.length})` : `All (${orders.length})` },
                { id: "easykash", label: "EasyKash" },
                { id: "vodafone_cash", label: isAr ? "فودافون كاش" : "Vodafone Cash" },
                { id: "instapay", label: "InstaPay" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSelectedProvider(tab.id)}
                  className={`px-2.5 py-1.5 text-xs font-black border-2 border-black shrink-0 transition-all ${
                    selectedProvider === tab.id
                      ? "bg-black text-white dark:bg-white dark:text-black shadow-[2px_2px_0px_rgba(0,0,0,1)]"
                      : "bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Orders Table */}
          <div className="border-2 border-black dark:border-zinc-700 overflow-x-auto">
            <table className="w-full text-xs text-start border-collapse">
              <thead>
                <tr className="bg-zinc-100 dark:bg-zinc-900 border-b-2 border-black dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 font-black">
                  <th className="p-2.5 text-start">#</th>
                  <th className="p-2.5 text-start">{isAr ? "العميل" : "Customer"}</th>
                  <th className="p-2.5 text-start">{isAr ? "وسيلة الدفع" : "Provider"}</th>
                  <th className="p-2.5 text-start">{isAr ? "الخطة" : "Plan"}</th>
                  <th className="p-2.5 text-start">{isAr ? "التاريخ (بتوقيت مصر)" : "Date (Cairo)"}</th>
                  <th className="p-2.5 text-end">{isAr ? "المبلغ" : "Gross"}</th>
                  <th className="p-2.5 text-end">{isAr ? "الصافي (-4%)" : "Net (-4%)"}</th>
                  <th className="p-2.5 text-center">{isAr ? "كود الطلب / المرجع" : "Order ID"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {filteredOrders.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-zinc-400 font-bold">
                      {isAr ? "لا توجد طلبات تطابق البحث" : "No orders found"}
                    </td>
                  </tr>
                ) : (
                  filteredOrders.map((order, idx) => (
                    <tr
                      key={order.id || idx}
                      className="hover:bg-zinc-50 dark:hover:bg-zinc-900/60 font-bold transition-colors"
                    >
                      <td className="p-2.5 font-mono text-zinc-400">{idx + 1}</td>
                      <td className="p-2.5">
                        <div className="font-black text-zinc-900 dark:text-white">
                          {order.display_name || (order.email ? order.email.split("@")[0] : "عميل")}
                        </div>
                        {order.email && (
                          <div className="text-[11px] font-mono text-zinc-500 dark:text-zinc-400 truncate max-w-[180px]">
                            {order.email}
                          </div>
                        )}
                      </td>
                      <td className="p-2.5">{providerBadge(order.provider)}</td>
                      <td className="p-2.5">
                        <span className="inline-block px-1.5 py-0.5 bg-amber-400 text-black border border-black text-[10px] font-black uppercase">
                          {order.plan_id || "Pro"}
                        </span>
                      </td>
                      <td className="p-2.5 text-zinc-600 dark:text-zinc-400 whitespace-nowrap">
                        {formatCairoDate(order.created_at)}
                      </td>
                      <td className="p-2.5 text-end font-mono font-black text-zinc-900 dark:text-white whitespace-nowrap">
                        {Number(order.amount_egp).toLocaleString("en-US", { minimumFractionDigits: 2 })} ج.م
                      </td>
                      <td className="p-2.5 text-end font-mono font-black text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                        {Number(order.net_egp).toLocaleString("en-US", { minimumFractionDigits: 2 })} ج.م
                      </td>
                      <td className="p-2.5 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <code className="text-[10px] font-mono bg-zinc-100 dark:bg-zinc-800 px-1 py-0.5 border border-zinc-300 dark:border-zinc-700 truncate max-w-[90px]">
                            {order.id.slice(0, 8)}...
                          </code>
                          <button
                            onClick={() => handleCopy(order.id, order.id)}
                            className="p-1 hover:bg-zinc-200 dark:hover:bg-zinc-700 border border-black text-zinc-600 dark:text-zinc-300"
                            title={isAr ? "نسخ كود الطلب" : "Copy Order ID"}
                          >
                            {copiedId === order.id ? (
                              <Check className="w-3 h-3 text-emerald-600" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 sm:p-4 bg-zinc-100 dark:bg-zinc-900 border-t-4 border-black dark:border-white flex items-center justify-between shrink-0">
          <div className="text-xs font-bold text-zinc-500">
            {isAr
              ? `عرض ${filteredOrders.length} من إجمالي ${orders.length} طلب مؤكد`
              : `Showing ${filteredOrders.length} of ${orders.length} confirmed orders`}
          </div>
          <button
            onClick={onClose}
            className="px-5 py-1.5 bg-black text-white hover:bg-zinc-800 dark:bg-white dark:text-black font-black text-xs border-2 border-black shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-all"
          >
            {isAr ? "إغلاق" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
