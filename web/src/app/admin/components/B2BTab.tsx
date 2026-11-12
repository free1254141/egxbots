"use client";

import { useEffect, useState, useMemo } from "react";
import { toast } from "sonner";
import {
  Bot,
  Plus,
  RefreshCw,
  Search,
  Pause,
  Play,
  Calendar,
  Trash2,
  Edit3,
  Copy,
  ExternalLink,
  ShieldCheck,
  Zap,
  TrendingUp,
  MessageSquare,
  Users,
  CheckCircle2,
  AlertTriangle,
  X,
  Loader2,
} from "lucide-react";

interface B2BLicense {
  id: string;
  owner_user_id: string | null;
  owner_email?: string;
  order_id?: string;
  telegram_chat_id: number | null;
  group_title: string | null;
  group_username?: string | null;
  invite_link?: string | null;
  tier: "b2b_starter" | "b2b_pro" | "b2b_enterprise";
  daily_limit: number;
  daily_used: number;
  last_used_date: string | null;
  custom_signature: string | null;
  status: "active" | "expired" | "paused";
  starts_at: string;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

interface Stats {
  total_licenses: number;
  active_licenses: number;
  total_daily_used: number;
  total_daily_limit: number;
  estimated_mrr_egp: number;
  today_date: string;
}

const TIER_META = {
  b2b_starter: {
    label: "Starter B2B (150 عضو)",
    price: 1000,
    color: "bg-blue-100 text-blue-900 border-blue-500 dark:bg-blue-950/50 dark:text-blue-300",
  },
  b2b_pro: {
    label: "Pro VIP B2B (500 عضو)",
    price: 1500,
    color: "bg-emerald-100 text-emerald-900 border-emerald-500 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  b2b_enterprise: {
    label: "Enterprise B2B (1,500 عضو)",
    price: 2500,
    color: "bg-purple-100 text-purple-900 border-purple-500 dark:bg-purple-950/50 dark:text-purple-300",
  },
};

export default function B2BTab() {
  const [licenses, setLicenses] = useState<B2BLicense[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterTier, setFilterTier] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingLicense, setEditingLicense] = useState<B2BLicense | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  // Create form state
  const [createForm, setCreateForm] = useState({
    tier: "b2b_pro",
    group_title: "",
    telegram_chat_id: "",
    custom_signature: "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS",
    duration_days: 30,
    daily_limit: 120,
    owner_email: "",
  });

  const fetchLicenses = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/b2b");
      const data = await res.json();
      if (data.ok) {
        setLicenses(data.licenses || []);
        setStats(data.stats || null);
      } else {
        toast.error(`فشل تحميل التراخيص: ${data.error}`);
      }
    } catch (err: any) {
      toast.error(`خطأ في جلب البيانات: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLicenses();
  }, []);

  const handleTogglePause = async (lic: B2BLicense) => {
    try {
      setActionBusy(true);
      const res = await fetch("/api/admin/b2b", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "toggle_pause",
          license_id: lic.id,
          current_status: lic.status,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success(lic.status === "paused" ? "تم تفعيل الترخيص بنجاح" : "تم إيقاف الترخيص مؤقتاً");
        fetchLicenses();
      } else {
        toast.error(data.error);
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleExtend = async (lic: B2BLicense, days = 30) => {
    try {
      setActionBusy(true);
      const res = await fetch("/api/admin/b2b", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "extend",
          license_id: lic.id,
          days,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success(`تم تمديد الترخيص ${days} يوماً بنجاح!`);
        fetchLicenses();
      } else {
        toast.error(data.error);
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleDelete = async (lic: B2BLicense) => {
    if (!confirm(`هل أنت متأكد من حذف رخصة الجروب "${lic.group_title || lic.id}" نهائياً؟`)) return;
    try {
      setActionBusy(true);
      const res = await fetch("/api/admin/b2b", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "delete",
          license_id: lic.id,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success("تم حذف الترخيص بنجاح");
        fetchLicenses();
      } else {
        toast.error(data.error);
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setActionBusy(true);
      const res = await fetch("/api/admin/b2b", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "create",
          ...createForm,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success("تم إنشاء الترخيص بنجاح!");
        setShowCreateModal(false);
        setCreateForm({
          tier: "b2b_pro",
          group_title: "",
          telegram_chat_id: "",
          custom_signature: "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS",
          duration_days: 30,
          daily_limit: 120,
          owner_email: "",
        });
        fetchLicenses();
      } else {
        toast.error(data.error);
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingLicense) return;
    try {
      setActionBusy(true);
      const res = await fetch("/api/admin/b2b", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "update",
          license_id: editingLicense.id,
          group_title: editingLicense.group_title,
          custom_signature: editingLicense.custom_signature,
          daily_limit: editingLicense.daily_limit,
          tier: editingLicense.tier,
          telegram_chat_id: editingLicense.telegram_chat_id,
          status: editingLicense.status,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        toast.success("تم تحديث بيانات الترخيص بنجاح!");
        setEditingLicense(null);
        fetchLicenses();
      } else {
        toast.error(data.error);
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setActionBusy(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`تم نسخ ${label}`);
  };

  const filteredLicenses = useMemo(() => {
    return licenses.filter((lic) => {
      const matchSearch =
        !search ||
        (lic.group_title && lic.group_title.toLowerCase().includes(search.toLowerCase())) ||
        (lic.owner_email && lic.owner_email.toLowerCase().includes(search.toLowerCase())) ||
        (lic.telegram_chat_id && String(lic.telegram_chat_id).includes(search)) ||
        (lic.custom_signature && lic.custom_signature.toLowerCase().includes(search.toLowerCase()));

      const matchTier = filterTier === "all" || lic.tier === filterTier;
      const matchStatus = filterStatus === "all" || lic.status === filterStatus;

      return matchSearch && matchTier && matchStatus;
    });
  }, [licenses, search, filterTier, filterStatus]);

  return (
    <div className="space-y-6" dir="rtl">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-5 shadow-[5px_5px_0px_#000] dark:shadow-[5px_5px_0px_#fff]">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 border-2 border-black bg-emerald-400 text-black font-black">
              <Bot className="w-6 h-6" />
            </span>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-zinc-950 dark:text-white">
                إدارة تراخيص بوت التليجرام للشركات والقنوات (B2B Channels)
              </h1>
              <p className="text-xs text-zinc-600 dark:text-zinc-400 font-bold mt-0.5">
                متابعة استهلاك الجروبات المفعلة، توقيع القنوات، والتحكم الفوري في الكوتة اليومية
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 border-2 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black font-black px-4 py-2.5 text-xs uppercase shadow-[2px_2px_0px_#000] active:translate-y-0.5 transition-all"
          >
            <Plus className="w-4 h-4" />
            منح ترخيص يدوي لجروب
          </button>
          <button
            onClick={fetchLicenses}
            disabled={loading}
            className="flex items-center gap-1.5 border-2 border-black dark:border-white bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-black dark:text-white font-black px-3 py-2.5 text-xs shadow-[2px_2px_0px_#000] active:translate-y-0.5"
            title="تحديث البيانات"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="border-4 border-black dark:border-white bg-amber-300 text-black p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-wider">الرخص النشطة</span>
            <Users className="w-5 h-5" />
          </div>
          <div className="text-2xl sm:text-3xl font-black mt-2">
            {stats?.active_licenses ?? 0} <span className="text-xs font-bold">جروب مفعل</span>
          </div>
          <div className="text-[10px] font-bold mt-1 opacity-80">
            من إجمالي {stats?.total_licenses ?? 0} رخصة مسجلة
          </div>
        </div>

        <div className="border-4 border-black dark:border-white bg-emerald-400 text-black p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-wider">الإيراد الشهري B2B (MRR)</span>
            <TrendingUp className="w-5 h-5" />
          </div>
          <div className="text-2xl sm:text-3xl font-black mt-2">
            {(stats?.estimated_mrr_egp ?? 0).toLocaleString()} <span className="text-xs font-bold">ج.م / شهر</span>
          </div>
          <div className="text-[10px] font-bold mt-1 opacity-80">
            هامش ربح تشغيلي &gt; 97%
          </div>
        </div>

        <div className="border-4 border-black dark:border-white bg-cyan-300 text-black p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-wider">استهلاك اليوم (Queries)</span>
            <Zap className="w-5 h-5" />
          </div>
          <div className="text-2xl sm:text-3xl font-black mt-2">
            {stats?.total_daily_used ?? 0} <span className="text-xs font-bold">/ {stats?.total_daily_limit ?? 0}</span>
          </div>
          <div className="text-[10px] font-bold mt-1 opacity-80">
            يتجدد العداد 12:00 ص بتوقيت القاهرة
          </div>
        </div>

        <div className="border-4 border-black dark:border-white bg-fuchsia-300 text-black p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-wider">الحماية والـ Fair Use</span>
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div className="text-2xl sm:text-3xl font-black mt-2">
            مفعّلة ⚡
          </div>
          <div className="text-[10px] font-bold mt-1 opacity-80">
            كولد داون 90 ثانية • كوتة 15 لعضو الجروب
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-4 shadow-[4px_4px_0px_#000] dark:shadow-[4px_4px_0px_#fff] flex flex-col md:flex-row gap-3 items-center justify-between">
        <div className="relative w-full md:w-96">
          <Search className="w-4 h-4 absolute right-3 top-3.5 text-zinc-400" />
          <input
            type="text"
            placeholder="بحث باسم القناة، الإيميل، أو معرف Chat ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 pr-9 pl-3 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-emerald-500 text-zinc-950 dark:text-white"
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0">
          <select
            value={filterTier}
            onChange={(e) => setFilterTier(e.target.value)}
            className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-xs font-black outline-none text-zinc-950 dark:text-white"
          >
            <option value="all">كل الباقات</option>
            <option value="b2b_starter">Starter (1,000 ج.م)</option>
            <option value="b2b_pro">Pro VIP (1,500 ج.م)</option>
            <option value="b2b_enterprise">Enterprise (2,500 ج.م)</option>
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="border-2 border-black dark:border-white bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-xs font-black outline-none text-zinc-950 dark:text-white"
          >
            <option value="all">كل الحالات</option>
            <option value="active">نشط فقط</option>
            <option value="paused">موقوف مؤقتاً</option>
            <option value="expired">منتهي الصلاحية</option>
          </select>
        </div>
      </div>

      {/* Table of Licenses */}
      <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 shadow-[6px_6px_0px_#000] dark:shadow-[6px_6px_0px_#fff] overflow-hidden">
        {loading ? (
          <div className="p-12 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
            <span className="text-xs font-bold text-zinc-500">جاري تحميل تراخيص القنوات...</span>
          </div>
        ) : filteredLicenses.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Bot className="w-12 h-12 mx-auto text-zinc-400" />
            <h3 className="text-base font-black text-zinc-800 dark:text-zinc-200">
              لا توجد تراخيص مطابقة للبحث
            </h3>
            <p className="text-xs text-zinc-500 font-bold max-w-md mx-auto">
              يمكنك منح أول ترخيص تجريبي أو حقيقي لأي قناة بالضغط على زر &quot;منح ترخيص يدوي لجروب&quot; بالأعلى.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="border-b-4 border-black dark:border-white bg-zinc-100 dark:bg-zinc-800 font-black text-zinc-900 dark:text-zinc-100 uppercase">
                <tr>
                  <th className="p-3.5">القناة / الجروب</th>
                  <th className="p-3.5">المالك / الطلب</th>
                  <th className="p-3.5">الباقة</th>
                  <th className="p-3.5">استهلاك اليوم</th>
                  <th className="p-3.5">التوقيع المخصص</th>
                  <th className="p-3.5">الصلاحية</th>
                  <th className="p-3.5">الحالة</th>
                  <th className="p-3.5 text-center">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y-2 divide-zinc-200 dark:divide-zinc-800 font-bold">
                {filteredLicenses.map((lic) => {
                  const meta = TIER_META[lic.tier] || TIER_META.b2b_pro;
                  const isExpired = new Date(lic.expires_at) <= new Date();
                  const remainingDays = Math.max(
                    0,
                    Math.ceil((new Date(lic.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
                  );
                  const usagePct = Math.min(100, Math.round(((lic.daily_used || 0) / (lic.daily_limit || 1)) * 100));

                  return (
                    <tr key={lic.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors">
                      {/* Group Title & Chat ID & Direct Link */}
                      <td className="p-3.5">
                        <div className="font-black text-sm text-zinc-900 dark:text-white flex items-center gap-1.5 flex-wrap">
                          <Bot className="w-4 h-4 text-emerald-500 shrink-0" />
                          <span>{lic.group_title || "مجموعة غير مسماة"}</span>
                          {lic.invite_link && (
                            <a
                              href={lic.invite_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-emerald-500 bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 text-[10px] font-black hover:bg-emerald-100 transition-colors"
                              title="فتح المجموعة / القناة في تليجرام"
                            >
                              <ExternalLink className="w-3 h-3" />
                              <span>دخول الجروب</span>
                            </a>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-[11px] font-mono text-zinc-500 flex-wrap">
                          {lic.telegram_chat_id ? (
                            <>
                              <span>Chat ID: {lic.telegram_chat_id}</span>
                              <button
                                onClick={() => copyToClipboard(String(lic.telegram_chat_id), "Chat ID")}
                                className="hover:text-emerald-500"
                                title="نسخ"
                              >
                                <Copy className="w-3 h-3" />
                              </button>
                              {lic.invite_link && (
                                <button
                                  onClick={() => copyToClipboard(lic.invite_link!, "رابط الجروب")}
                                  className="text-emerald-600 hover:underline flex items-center gap-0.5 text-[10px]"
                                  title="نسخ رابط الدعوة"
                                >
                                  <Copy className="w-2.5 h-2.5" />
                                  <span>نسخ الرابط</span>
                                </button>
                              )}
                            </>
                          ) : (
                            <span className="text-amber-600 dark:text-amber-400 font-bold">
                              ⏳ بانتظار تفعيل البوت في الجروب
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Owner Email / Order */}
                      <td className="p-3.5">
                        <div className="text-zinc-800 dark:text-zinc-200 font-mono text-xs">
                          {lic.owner_email || lic.owner_user_id || "غير معروف"}
                        </div>
                        {lic.order_id && (
                          <div className="text-[10px] font-mono text-zinc-400 mt-0.5">
                            Order: {lic.order_id}
                          </div>
                        )}
                      </td>

                      {/* Tier Badge */}
                      <td className="p-3.5">
                        <span className={`inline-block border-2 px-2 py-0.5 text-[10px] font-black uppercase ${meta.color}`}>
                          {meta.label}
                        </span>
                      </td>

                      {/* Daily Quota Progress */}
                      <td className="p-3.5 min-w-[140px]">
                        <div className="flex items-center justify-between text-[11px] font-mono mb-1">
                          <span className="font-black">{lic.daily_used || 0}</span>
                          <span className="text-zinc-400">/ {lic.daily_limit} استفسار</span>
                        </div>
                        <div className="w-full bg-zinc-200 dark:bg-zinc-700 h-2 border border-black dark:border-white overflow-hidden">
                          <div
                            className={`h-full ${
                              usagePct >= 90 ? "bg-red-500" : usagePct >= 70 ? "bg-amber-400" : "bg-emerald-500"
                            }`}
                            style={{ width: `${usagePct}%` }}
                          />
                        </div>
                        <div className="text-[10px] text-zinc-400 mt-0.5 font-mono">{usagePct}% مستهلك</div>
                      </td>

                      {/* Custom Signature Preview */}
                      <td className="p-3.5 max-w-[200px]">
                        <div className="bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 p-1.5 text-[11px] text-zinc-700 dark:text-zinc-300 line-clamp-2 italic">
                          {lic.custom_signature || "لا يوجد توقيع"}
                        </div>
                      </td>

                      {/* Expiry and Remaining Days */}
                      <td className="p-3.5">
                        <div className="text-xs font-mono font-bold">
                          {new Date(lic.expires_at).toLocaleDateString("ar-EG")}
                        </div>
                        <div className="text-[10px] text-zinc-500 font-bold mt-0.5">
                          {isExpired ? (
                            <span className="text-red-600 font-black">منتهي الصلاحية</span>
                          ) : (
                            <span>متبقي {remainingDays} يوماً</span>
                          )}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="p-3.5">
                        {lic.status === "paused" ? (
                          <span className="inline-flex items-center gap-1 border-2 border-amber-600 bg-amber-100 dark:bg-amber-950/50 text-amber-800 dark:text-amber-300 px-2 py-0.5 text-[10px] font-black">
                            <Pause className="w-3 h-3" /> موقوف مؤقتاً
                          </span>
                        ) : isExpired ? (
                          <span className="inline-flex items-center gap-1 border-2 border-red-600 bg-red-100 dark:bg-red-950/50 text-red-800 dark:text-red-300 px-2 py-0.5 text-[10px] font-black">
                            <AlertTriangle className="w-3 h-3" /> منتهي
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 border-2 border-emerald-600 bg-emerald-100 dark:bg-emerald-950/50 text-emerald-800 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-black">
                            <CheckCircle2 className="w-3 h-3" /> نشط
                          </span>
                        )}
                      </td>

                      {/* Action Buttons */}
                      <td className="p-3.5 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          {/* Pause / Resume */}
                          <button
                            onClick={() => handleTogglePause(lic)}
                            disabled={actionBusy}
                            className={`p-1.5 border border-black dark:border-white text-xs font-black ${
                              lic.status === "paused"
                                ? "bg-emerald-400 hover:bg-emerald-500 text-black"
                                : "bg-amber-300 hover:bg-amber-400 text-black"
                            }`}
                            title={lic.status === "paused" ? "تفعيل" : "إيقاف مؤقت"}
                          >
                            {lic.status === "paused" ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                          </button>

                          {/* Extend +30 Days */}
                          <button
                            onClick={() => handleExtend(lic, 30)}
                            disabled={actionBusy}
                            className="p-1.5 border border-black dark:border-white bg-blue-300 hover:bg-blue-400 text-black text-xs font-black"
                            title="تمديد 30 يوماً إضافية"
                          >
                            <Calendar className="w-3.5 h-3.5" />
                          </button>

                          {/* Edit Details */}
                          <button
                            onClick={() => setEditingLicense(lic)}
                            className="p-1.5 border border-black dark:border-white bg-zinc-200 hover:bg-zinc-300 dark:bg-zinc-700 dark:hover:bg-zinc-600 text-black dark:text-white"
                            title="تعديل الإعدادات والتوقيع"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>

                          {/* Delete */}
                          <button
                            onClick={() => handleDelete(lic)}
                            disabled={actionBusy}
                            className="p-1.5 border border-black dark:border-white bg-red-400 hover:bg-red-500 text-black"
                            title="حذف الترخيص"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* CREATE MODAL */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" dir="rtl">
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 max-w-lg w-full shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
              <h2 className="text-lg font-black text-zinc-900 dark:text-white flex items-center gap-2">
                <Plus className="w-5 h-5 text-emerald-500" />
                منح ترخيص B2B يدوي لجروب أو شريك
              </h2>
              <button onClick={() => setShowCreateModal(false)} className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs font-bold">
              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">اسم القناة / الجروب *</label>
                <input
                  type="text"
                  required
                  placeholder="مثلاً: قناة توصيات الخبراء 📊"
                  value={createForm.group_title}
                  onChange={(e) => setCreateForm({ ...createForm, group_title: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-zinc-700 dark:text-zinc-300 mb-1">نوع الباقة *</label>
                  <select
                    value={createForm.tier}
                    onChange={(e) => {
                      const t = e.target.value;
                      const limits: Record<string, number> = { b2b_starter: 50, b2b_pro: 120, b2b_enterprise: 250 };
                      setCreateForm({ ...createForm, tier: t, daily_limit: limits[t] || 120 });
                    }}
                    className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                  >
                    <option value="b2b_starter">Starter (150 عضو - 50 سؤال/يوم)</option>
                    <option value="b2b_pro">Pro VIP (500 عضو - 120 سؤال/يوم)</option>
                    <option value="b2b_enterprise">Enterprise (1,500 عضو - 250 سؤال/يوم)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-zinc-700 dark:text-zinc-300 mb-1">الحد اليومي للاستفسارات</label>
                  <input
                    type="number"
                    min="10"
                    max="1000"
                    value={createForm.daily_limit}
                    onChange={(e) => setCreateForm({ ...createForm, daily_limit: Number(e.target.value) })}
                    className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">
                  معرف الجروب الرقمي (Telegram Chat ID) - اختياري
                </label>
                <input
                  type="text"
                  placeholder="مثلاً: -100189234857 (يمكن تركه فارغاً لربطه لاحقاً)"
                  value={createForm.telegram_chat_id}
                  onChange={(e) => setCreateForm({ ...createForm, telegram_chat_id: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none font-mono"
                  dir="ltr"
                />
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">
                  إيميل المالك في المنصة (اختياري لربط الترخيص بحسابه)
                </label>
                <input
                  type="email"
                  placeholder="user@example.com"
                  value={createForm.owner_email}
                  onChange={(e) => setCreateForm({ ...createForm, owner_email: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none font-mono"
                  dir="ltr"
                />
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">
                  نص التوقيع المخصص (Custom Signature)
                </label>
                <textarea
                  rows={2}
                  maxLength={150}
                  placeholder="سطر ترويجي يظهر أسفل كل رد للبوت في الجروب..."
                  value={createForm.custom_signature}
                  onChange={(e) => setCreateForm({ ...createForm, custom_signature: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                />
                <span className="text-[10px] text-zinc-400">الحد الأقصى 150 حرفاً</span>
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">مدة الترخيص (بالأيام)</label>
                <input
                  type="number"
                  min="1"
                  max="365"
                  value={createForm.duration_days}
                  onChange={(e) => setCreateForm({ ...createForm, duration_days: Number(e.target.value) })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-200 dark:border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="border-2 border-black dark:border-white px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={actionBusy}
                  className="border-2 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black px-6 py-2 font-black shadow-[2px_2px_0px_#000]"
                >
                  {actionBusy ? "جاري الحفظ..." : "إنشاء الترخيص"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT MODAL */}
      {editingLicense && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" dir="rtl">
          <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 max-w-lg w-full shadow-[8px_8px_0px_#000] dark:shadow-[8px_8px_0px_#fff] space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b-2 border-zinc-200 dark:border-zinc-800 pb-3">
              <h2 className="text-lg font-black text-zinc-900 dark:text-white flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-emerald-500" />
                تعديل إعدادات وتوقيع الجروب
              </h2>
              <button onClick={() => setEditingLicense(null)} className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="space-y-4 text-xs font-bold">
              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">اسم القناة / الجروب</label>
                <input
                  type="text"
                  required
                  value={editingLicense.group_title || ""}
                  onChange={(e) => setEditingLicense({ ...editingLicense, group_title: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-zinc-700 dark:text-zinc-300 mb-1">نوع الباقة</label>
                  <select
                    value={editingLicense.tier}
                    onChange={(e: any) => setEditingLicense({ ...editingLicense, tier: e.target.value })}
                    className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                  >
                    <option value="b2b_starter">Starter (50 سؤال/يوم)</option>
                    <option value="b2b_pro">Pro VIP (120 سؤال/يوم)</option>
                    <option value="b2b_enterprise">Enterprise (250 سؤال/يوم)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-zinc-700 dark:text-zinc-300 mb-1">الحد اليومي للاستفسارات</label>
                  <input
                    type="number"
                    min="10"
                    max="1000"
                    value={editingLicense.daily_limit}
                    onChange={(e) => setEditingLicense({ ...editingLicense, daily_limit: Number(e.target.value) })}
                    className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">Telegram Chat ID</label>
                <input
                  type="text"
                  value={editingLicense.telegram_chat_id ? String(editingLicense.telegram_chat_id) : ""}
                  onChange={(e) =>
                    setEditingLicense({
                      ...editingLicense,
                      telegram_chat_id: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none font-mono"
                  dir="ltr"
                />
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">
                  نص التوقيع المخصص (Custom Signature)
                </label>
                <textarea
                  rows={2}
                  maxLength={150}
                  value={editingLicense.custom_signature || ""}
                  onChange={(e) => setEditingLicense({ ...editingLicense, custom_signature: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                />
                <span className="text-[10px] text-zinc-400">الحد الأقصى 150 حرفاً</span>
              </div>

              <div>
                <label className="block text-zinc-700 dark:text-zinc-300 mb-1">حالة الترخيص</label>
                <select
                  value={editingLicense.status}
                  onChange={(e: any) => setEditingLicense({ ...editingLicense, status: e.target.value })}
                  className="w-full border-2 border-black dark:border-white p-2.5 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-white outline-none"
                >
                  <option value="active">نشط (Active)</option>
                  <option value="paused">موقوف مؤقتاً (Paused)</option>
                  <option value="expired">منتهي الصلاحية (Expired)</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-zinc-200 dark:border-zinc-800">
                <button
                  type="button"
                  onClick={() => setEditingLicense(null)}
                  className="border-2 border-black dark:border-white px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={actionBusy}
                  className="border-2 border-black dark:border-white bg-emerald-500 hover:bg-emerald-600 text-black px-6 py-2 font-black shadow-[2px_2px_0px_#000]"
                >
                  {actionBusy ? "جاري التحديث..." : "حفظ التعديلات"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
