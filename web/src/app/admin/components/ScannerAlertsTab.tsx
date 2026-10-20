"use client";

import React, { useState, useEffect } from "react";
import { 
  Zap, 
  ArrowUpRight, 
  Target, 
  Star, 
  Newspaper, 
  Play, 
  Clock, 
  ShieldCheck, 
  AlertCircle, 
  RefreshCw, 
  CheckCircle2, 
  Send,
  Activity,
  Layers,
  History,
  Sparkles
} from "lucide-react";
import { toast } from "sonner";

interface AdminScannerConfig {
  is_active: boolean;
  interval_minutes: number;
  market_hours_only: boolean;
  scanners_enabled: {
    volume_surge: boolean;
    breakout: boolean;
    rsi_oversold: boolean;
    portfolio_watchlist: boolean;
    disclosures: boolean;
  };
  last_scan?: {
    timestamp: string;
    duration_ms: number;
    total_symbols_scanned: number;
    stage_results: {
      volume_surge: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }>;
      breakout: Array<{ symbol: string; close: number; change_pct: number; r_vol: number }>;
      rsi_oversold: Array<{ symbol: string; close: number; rsi_14: number; change_pct: number }>;
      disclosures: Array<{ id: string; title: string; symbol?: string; published_at?: string }>;
    };
    alerts_dispatched: number;
  };
  history?: Array<{
    timestamp: string;
    duration_ms: number;
    volume_count: number;
    breakout_count: number;
    oversold_count: number;
    disclosures_count: number;
    recipients_count: number;
    triggered_by: string;
  }>;
}

export default function ScannerAlertsTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningScan, setRunningScan] = useState(false);

  const [config, setConfig] = useState<AdminScannerConfig | null>(null);
  const [stats, setStats] = useState<{
    active_pro_subscribers: number;
    linked_telegram_subscribers: number;
    readiness_pct: number;
  }>({ active_pro_subscribers: 0, linked_telegram_subscribers: 0, readiness_pct: 0 });

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/admin/scanner-alerts");
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          setConfig(data.config);
          setStats(data.stats);
        }
      }
    } catch (e) {
      console.error(e);
      toast.error("فشل تحميل إعدادات الإسكانر");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSaveSettings = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const res = await fetch("/api/admin/scanner-alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "save_settings",
          ...config,
        }),
      });
      if (res.ok) {
        toast.success("تم حفظ إعدادات وتوقيت الإسكانر بنجاح!");
      } else {
        toast.error("تعذر حفظ الإعدادات");
      }
    } catch {
      toast.error("خطأ في الاتصال");
    } finally {
      setSaving(false);
    }
  };

  const handleRunScanNow = async () => {
    setRunningScan(true);
    try {
      const res = await fetch("/api/admin/scanner-alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "run_scan_now", force_dispatch: true }),
      });
      if (res.ok) {
        const data = await res.json();
        const dispatched = data.alerts_dispatched ?? 0;
        toast.success(`اكتمل الفحص في ${data.duration_ms} مللي ثانية وتم إرسال ${dispatched} تنبيه على تليجرام!`);
        fetchConfig();
      } else {
        toast.error("فشل تنفيذ الفحص الفوري");
      }
    } catch {
      toast.error("خطأ أثناء تشغيل الفحص");
    } finally {
      setRunningScan(false);
    }
  };

  if (loading || !config) {
    return (
      <div className="flex h-96 items-center justify-center">
        <RefreshCw className="h-8 w-8 animate-spin text-amber-500" />
      </div>
    );
  }

  const lastScan = config.last_scan;

  return (
    <div className="space-y-8 max-w-[1600px] mx-auto p-4 md:p-8 animate-in fade-in duration-300 pb-20" dir="rtl">
      {/* ── Top Readiness Banner ── */}
      <div className="border-4 border-black dark:border-white bg-[#FFE600] text-black p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-black text-[#FFE600] border-2 border-black shadow-[2px_2px_0px_rgba(0,0,0,1)]">
            <Send className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-black uppercase tracking-tight">
              نظام إدارة رادار الإسكانر وتنبيهات تليجرام الفورية (Telegram Alerts Engine)
            </h2>
            <p className="text-xs font-bold mt-1 text-black/80">
              تحكم كامل في مواعيد وتشغيل الفلاتر، قياس زمن التنفيذ بالمللي ثانية، ومتابعة وصول التنبيهات لمشتركي Pro.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 border-2 border-black bg-white px-4 py-2 font-mono text-xs font-black shrink-0 shadow-[2px_2px_0px_rgba(0,0,0,1)]">
          <div className="border-l-2 border-black/20 pl-3">
            <span className="text-zinc-500 block text-[10px]">وجهة البث المباشر:</span>
            <span className="text-purple-700 text-sm font-black flex items-center gap-1">
              ⭐ قناة VIP الرسمية
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block text-[10px]">المشتركون المتصلون بالبوت:</span>
            <span className="text-emerald-700 text-sm">
              {stats.linked_telegram_subscribers} من {stats.active_pro_subscribers} ({stats.readiness_pct}%)
            </span>
          </div>
        </div>
      </div>

      {/* ── Live Performance & Execution Station ── */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)]">
          <span className="text-zinc-500 text-[10px] font-black uppercase tracking-widest block">زمن الفحص الأخير</span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black text-black dark:text-white font-mono">
              {lastScan?.duration_ms ?? "—"}
            </span>
            <span className="text-xs font-bold text-zinc-500">مللي ثانية</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-emerald-600 bg-emerald-100 dark:bg-emerald-950/40 px-2 py-0.5 border border-emerald-500">
            ⚡ فائق السرعة والخفة
          </span>
        </div>

        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)]">
          <span className="text-zinc-500 text-[10px] font-black uppercase tracking-widest block">الأسهم المفحوصة</span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black text-black dark:text-white font-mono">
              {lastScan?.total_symbols_scanned ?? "—"}
            </span>
            <span className="text-xs font-bold text-zinc-500">سهم مدرج</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-blue-600 bg-blue-100 dark:bg-blue-950/40 px-2 py-0.5 border border-blue-500">
            تغطية شاملة للبورصة
          </span>
        </div>

        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)]">
          <span className="text-zinc-500 text-[10px] font-black uppercase tracking-widest block">استهلاك الموارد والتكلفة</span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-black text-emerald-600 font-mono">0$</span>
            <span className="text-xs font-bold text-zinc-500">0 Tokens</span>
          </div>
          <span className="inline-block mt-2 text-[10px] font-black text-purple-600 bg-purple-100 dark:bg-purple-950/40 px-2 py-0.5 border border-purple-500">
            فحص رياضي مباشر 100%
          </span>
        </div>

        <div className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-5 shadow-[4px_4px_0px_rgba(0,0,0,1)] flex flex-col justify-between">
          <div>
            <span className="text-zinc-500 text-[10px] font-black uppercase tracking-widest block">الفحص اليدوي المباشر</span>
            <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400 mt-1 block">تشغيل فوري الآن لاختبار المراحل</span>
          </div>
          <button
            type="button"
            onClick={handleRunScanNow}
            disabled={runningScan}
            className="w-full h-11 border-4 border-black bg-amber-400 hover:bg-amber-300 text-black font-black text-xs uppercase tracking-widest shadow-[3px_3px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none flex items-center justify-center gap-2 transition-all disabled:opacity-50 mt-3"
          >
            {runningScan ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-black" />}
            {runningScan ? "جاري الفحص..." : "تشغيل الفحص الفوري الآن"}
          </button>
        </div>
      </div>

      {/* ── Admin Configuration Station (التحكم في التوقيت والتشغيل) ── */}
      <section className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 md:p-8 shadow-[6px_6px_0px_rgba(0,0,0,1)] space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-4 border-black pb-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 border-4 border-black bg-purple-500 text-white flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)]">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-xl font-black text-black dark:text-white uppercase tracking-tight">
                إعدادات الجدولة والتوقيت والفلاتر الفعالة
              </h3>
              <p className="text-xs text-zinc-500 font-bold">حدد متى وكيف يتم فحص السوق وتوزيع الإشارات</p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleSaveSettings}
            disabled={saving}
            className="px-6 py-2.5 bg-emerald-400 hover:bg-emerald-300 text-black border-4 border-black font-black text-xs uppercase tracking-widest shadow-[3px_3px_0px_rgba(0,0,0,1)] active:translate-x-[1px] active:translate-y-[1px] transition-all disabled:opacity-50"
          >
            {saving ? "جاري الحفظ..." : "حفظ التغييرات"}
          </button>
        </div>

        {/* Global Controls Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
          {/* Master Switch */}
          <div className="border-4 border-black p-4 bg-zinc-50 dark:bg-zinc-800 shadow-[3px_3px_0px_rgba(0,0,0,1)] space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-black text-sm text-black dark:text-white">المفتاح العام للمنظومة</span>
              <button
                type="button"
                dir="ltr"
                onClick={() => setConfig({ ...config, is_active: !config.is_active })}
                className={`relative inline-flex h-7 w-14 border-4 border-black transition-colors ${
                  config.is_active ? "bg-emerald-400" : "bg-zinc-300 dark:bg-zinc-700"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform border-2 border-black bg-white transition duration-200 mt-0.5 ${
                    config.is_active ? "translate-x-7" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
            <p className="text-[11px] font-bold text-zinc-500">
              {config.is_active ? "🟢 المنظومة تعمل وترسل التنبيهات لمشتركي Pro" : "🔴 المنظومة متوقفة مؤقتاً"}
            </p>
          </div>

          {/* Interval */}
          <div className="border-4 border-black p-4 bg-zinc-50 dark:bg-zinc-800 shadow-[3px_3px_0px_rgba(0,0,0,1)] space-y-2">
            <span className="font-black text-sm text-black dark:text-white block">فترة تكرار الفحص الدوري</span>
            <select
              value={config.interval_minutes}
              onChange={(e) => setConfig({ ...config, interval_minutes: Number(e.target.value) })}
              className="w-full h-10 border-4 border-black px-3 font-mono font-bold text-xs bg-white dark:bg-zinc-900 text-black dark:text-white shadow-[2px_2px_0px_rgba(0,0,0,1)] outline-none"
            >
              <option value={5}>كل 5 دقائق (مكثف للمضاربة)</option>
              <option value={15}>كل 15 دقيقة (موصى به ومتوازن)</option>
              <option value={30}>كل 30 دقيقة</option>
              <option value={60}>كل ساعة</option>
            </select>
          </div>

          {/* Market hours only */}
          <div className="border-4 border-black p-4 bg-zinc-50 dark:bg-zinc-800 shadow-[3px_3px_0px_rgba(0,0,0,1)] space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-black text-sm text-black dark:text-white">ساعات جلسة التداول فقط</span>
              <button
                type="button"
                dir="ltr"
                onClick={() => setConfig({ ...config, market_hours_only: !config.market_hours_only })}
                className={`relative inline-flex h-7 w-14 border-4 border-black transition-colors ${
                  config.market_hours_only ? "bg-emerald-400" : "bg-zinc-300 dark:bg-zinc-700"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform border-2 border-black bg-white transition duration-200 mt-0.5 ${
                    config.market_hours_only ? "translate-x-7" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
            <p className="text-[11px] font-bold text-zinc-500">
              {config.market_hours_only ? "يعمل فقط من 10:00 ص إلى 02:30 م أيام الجلسات" : "يعمل 24/7 طوال الأسبوع"}
            </p>
          </div>
        </div>

        {/* 5 Scanners Admin Toggles */}
        <div className="border-t-2 border-black/10 pt-4">
          <span className="font-black text-xs uppercase tracking-wider text-zinc-500 block mb-3">
            الإسكانرات المسموح بتشغيلها حالياً في السيرفر:
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {[
              { id: "volume_surge" as const, name: "السيولة الذكية", icon: Zap },
              { id: "breakout" as const, name: "الاختراق والمقاومة", icon: ArrowUpRight },
              { id: "rsi_oversold" as const, name: "التشبع البيعي", icon: Target },
              { id: "portfolio_watchlist" as const, name: "تنبيهات المحافظ", icon: Star },
              { id: "disclosures" as const, name: "الإفصاحات الرسمية", icon: Newspaper },
            ].map((sc) => {
              const enabled = config.scanners_enabled[sc.id];
              return (
                <button
                  key={sc.id}
                  type="button"
                  onClick={() =>
                    setConfig({
                      ...config,
                      scanners_enabled: {
                        ...config.scanners_enabled,
                        [sc.id]: !enabled,
                      },
                    })
                  }
                  className={`p-3 border-4 border-black flex items-center justify-between text-xs font-black shadow-[2px_2px_0px_rgba(0,0,0,1)] transition-all ${
                    enabled ? "bg-amber-300 text-black" : "bg-zinc-200 dark:bg-zinc-800 text-zinc-500 opacity-60"
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <sc.icon className="w-4 h-4" />
                    {sc.name}
                  </span>
                  <span>{enabled ? "ON" : "OFF"}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Latest Scan Stage Results (نتائج كل مرحلة في الفحص الأخير) ── */}
      {lastScan && (
        <section className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] space-y-6">
          <div className="flex items-center justify-between border-b-4 border-black pb-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 border-4 border-black bg-emerald-400 text-black flex items-center justify-center shadow-[2px_2px_0px_rgba(0,0,0,1)]">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-xl font-black text-black dark:text-white uppercase tracking-tight">
                  الأسهم المرصودة في الفحص الأخير لكل مرحلة
                </h3>
                <span className="text-xs font-mono font-bold text-zinc-500">
                  تاريخ الفحص: {new Date(lastScan.timestamp).toLocaleTimeString("ar-EG")} | مدة التنفيذ: {lastScan.duration_ms}ms
                </span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Stage 1: Volume */}
            <div className="border-4 border-black p-4 bg-zinc-50 dark:bg-zinc-800 shadow-[3px_3px_0px_rgba(0,0,0,1)]">
              <div className="flex items-center justify-between border-b-2 border-black pb-2 mb-3">
                <span className="font-black text-xs flex items-center gap-1.5 text-amber-600">
                  <Zap className="w-4 h-4 fill-amber-500" />
                  رادار السيولة والتجميع
                </span>
                <span className="font-mono text-xs font-black bg-black text-amber-300 px-2 py-0.5">
                  {lastScan.stage_results.volume_surge.length} سهم
                </span>
              </div>
              <div className="space-y-2">
                {lastScan.stage_results.volume_surge.map((s, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs font-mono font-bold border-b border-zinc-300 dark:border-zinc-700 pb-1">
                    <span className="font-black text-black dark:text-white">{s.symbol}</span>
                    <span className="text-zinc-600 dark:text-zinc-400">{s.close} ج.م</span>
                    <span className="text-emerald-600">+{s.change_pct}%</span>
                    <span className="bg-amber-100 text-amber-800 px-1 border border-amber-300 text-[10px]">rVol: {s.r_vol}x</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Stage 2: Breakouts */}
            <div className="border-4 border-black p-4 bg-zinc-50 dark:bg-zinc-800 shadow-[3px_3px_0px_rgba(0,0,0,1)]">
              <div className="flex items-center justify-between border-b-2 border-black pb-2 mb-3">
                <span className="font-black text-xs flex items-center gap-1.5 text-emerald-600">
                  <ArrowUpRight className="w-4 h-4" />
                  ماسح الاختراقات
                </span>
                <span className="font-mono text-xs font-black bg-black text-emerald-300 px-2 py-0.5">
                  {lastScan.stage_results.breakout.length} سهم
                </span>
              </div>
              <div className="space-y-2">
                {lastScan.stage_results.breakout.map((s, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs font-mono font-bold border-b border-zinc-300 dark:border-zinc-700 pb-1">
                    <span className="font-black text-black dark:text-white">{s.symbol}</span>
                    <span className="text-zinc-600 dark:text-zinc-400">{s.close} ج.م</span>
                    <span className="text-emerald-600 font-black">+{s.change_pct}%</span>
                    <span className="text-zinc-500 text-[10px]">rVol: {s.r_vol}x</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Stage 3: Oversold Reversals */}
            <div className="border-4 border-black p-4 bg-zinc-50 dark:bg-zinc-800 shadow-[3px_3px_0px_rgba(0,0,0,1)]">
              <div className="flex items-center justify-between border-b-2 border-black pb-2 mb-3">
                <span className="font-black text-xs flex items-center gap-1.5 text-sky-600">
                  <Target className="w-4 h-4" />
                  التشبع البيعي (RSI &lt; 35)
                </span>
                <span className="font-mono text-xs font-black bg-black text-sky-300 px-2 py-0.5">
                  {lastScan.stage_results.rsi_oversold.length} سهم
                </span>
              </div>
              <div className="space-y-2">
                {lastScan.stage_results.rsi_oversold.map((s, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs font-mono font-bold border-b border-zinc-300 dark:border-zinc-700 pb-1">
                    <span className="font-black text-black dark:text-white">{s.symbol}</span>
                    <span className="text-zinc-600 dark:text-zinc-400">{s.close} ج.م</span>
                    <span className="text-blue-600 font-black">RSI: {Math.round(s.rsi_14)}</span>
                    <span className={s.change_pct >= 0 ? "text-emerald-600" : "text-rose-600"}>{s.change_pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ── Daily Historical Stages Ledger (سجل نتائج المراحل لكل يوم) ── */}
      <section className="border-4 border-black dark:border-white bg-white dark:bg-zinc-900 p-6 shadow-[6px_6px_0px_rgba(0,0,0,1)] space-y-4">
        <div className="flex items-center gap-3 border-b-4 border-black pb-3">
          <History className="w-5 h-5" />
          <h3 className="text-lg font-black text-black dark:text-white uppercase tracking-tight">
            سجل العمليات اليومية ونتائج المراحل (Execution Ledger)
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-right border-collapse">
            <thead>
              <tr className="border-b-4 border-black bg-zinc-100 dark:bg-zinc-800 text-black dark:text-white font-black">
                <th className="p-3">تاريخ ووقت الفحص</th>
                <th className="p-3">مدة الفحص</th>
                <th className="p-3">فرص السيولة</th>
                <th className="p-3">فرص الاختراق</th>
                <th className="p-3">التشبع البيعي</th>
                <th className="p-3">الإفصاحات</th>
                <th className="p-3">المستلمون</th>
                <th className="p-3">المشغّل</th>
              </tr>
            </thead>
            <tbody>
              {(!config.history || config.history.length === 0) ? (
                <tr>
                  <td colSpan={8} className="p-4 text-center font-bold text-zinc-500">
                    لا توجد عمليات مسح مسجلة في التاريخ بعد. اضغط "تشغيل الفحص الفوري" لتوليد أول سجل.
                  </td>
                </tr>
              ) : (
                config.history.map((h, idx) => (
                  <tr key={idx} className="border-b border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                    <td className="p-3 font-bold">{new Date(h.timestamp).toLocaleString("ar-EG")}</td>
                    <td className="p-3 text-emerald-600 font-bold">{h.duration_ms} ms</td>
                    <td className="p-3 text-amber-600 font-bold">{h.volume_count}</td>
                    <td className="p-3 text-emerald-600 font-bold">{h.breakout_count}</td>
                    <td className="p-3 text-sky-600 font-bold">{h.oversold_count}</td>
                    <td className="p-3 text-purple-600 font-bold">{h.disclosures_count}</td>
                    <td className="p-3 font-bold">
                      {h.recipients_count > 0 ? "قناة VIP ⭐" : "0 (تخطي)"}
                    </td>
                    <td className="p-3 text-zinc-500">{h.triggered_by}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
