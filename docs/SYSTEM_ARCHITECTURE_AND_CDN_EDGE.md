# دليل المعمارية السحابية وقواعد النطاق والـ DNS (Vercel Direct + Supabase + Hugging Face)
**إصدار الوثيقة:** 2.0.0  
**تاريخ التحديث:** 14 نوفمبر 2026  
**الحالة:** مرجع إنتاجي معتمد لجميع المطورين والوكلاء الذكيين (Agents)

---

## 1. التكوين المعماري المعتمد للنطاق والشبكة

يعتمد مشروع **Artoro (EGX BOTS)** على التوجيه المباشر عبر خوادم **Vercel Anycast Edge** للأسباب التقنية الجوهرية التالية:

```
                      [ زوار مصر والعالم ]
                               │
                               ▼
        ┌──────────────────────────────────────────────────────┐
        │         ⚡ VERCEL ANYCAST GLOBAL EDGE NETWORK        │
        │ - خوادم الأسماء (Nameservers):                       │
        │   • ns1.vercel-dns.com  • ns2.vercel-dns.com         │
        │ - عناوين الآي بي المباشرة:                           │
        │   • 76.76.21.21         • 216.198.79.1               │
        │ - التخزين المؤقت الطرفي (Weekend-Proof 7-Day Cache): │
        │   • s-maxage=604800, stale-while-revalidate=2592000  │
        │   • إبطال فوري انتقائي بعد الإغلاق عبر /api/revalidate│
        │   • إرجاع الكاش (x-vercel-cache: HIT / PRERENDER)    │
        └──────────────┬───────────────────────────────────────┘
                       │ (Miss/Auth/Admin only)
      ┌────────────────┴────────────────────────┐
      ▼                                         ▼
┌───────────────────────────────┐     ┌────────────────────────────────┐
│  🗄️ SUPABASE (قاعدة البيانات)  │     │ 🤖 HUGGING FACE (بايثون وبوتات)│
│ - استعلامات محددة ومخبأة      │     │ - محرك Agentic AI Chat (/api/  │
│ - محافظ المستخدمين والاشتراكات│     │   ai-chat -> FastAPI Python)   │
│ - جداول الأسهم ومخزن EOD      │     │ - تشغيل بوت التليجرام          │
│ - حماية RLS وتفضيلات خفيفة    │     │ - مهام نهاية اليوم وإبطال الكاش│
└───────────────────────────────┘     └────────────────────────────────┘
                                                       │
                                                       ▼
                                      ┌────────────────────────────────┐
                                      │ 📧 خدمات البريد (Resend)       │
                                      │ - توثيق DKIM و SPF             │
                                      │ - إرسال التقارير وتنبيهات VIP   │
                                      └────────────────────────────────┘
```

---

## 2. ⚠️ تنبيه حاسم لجميع الوكلاء: حظر بروكسي كلاودفلير في مصر (Egyptian ISP DPI Block)

> [!CAUTION]
> **ممنوع منعاً باتاً تفعيل بروكسي كلاودفلير (السحابة البرتقالية 🟠) أو تحويل الـ Nameservers الخاصة بالدومين إلى كلاودفلير.**

### سبب المشكلة:
1. مزودو خدمة الإنترنت في جمهورية مصر العربية (وعلى رأسهم شركة **WE / Telecom Egypt** و**فودافون مصر**) يطبقون فحص حزم عميق (Deep Packet Inspection - DPI).
2. يقوم هذا الجدار بحظر نطاقات الآي بي المجانية لكلاودفلير (`104.21.x.x` و`172.67.x.x`)، مما يسبب خطأ فوري للمستخدمين في مصر:
   `ERR_CONNECTION_TIMED_OUT`.

### الحل المعتمد:
* النطاق يعمل مباشرة عبر **Vercel DNS** (`ns1.vercel-dns.com`, `ns2.vercel-dns.com`).
* الحماية وتوفير كوتا المعالج وقاعدة البيانات تعتمد على **4 طبقات متكاملة**:
  1. **Vercel Edge CDN & Next.js ISR (7-Day Weekend-Proof TTL):**
     * الصفحات العامة (`/`, `/stocks/[symbol]`, `/reports`, `/reports/[date]/[kind]`, `/pricing`, `/fair-value`, `/sharia`, `/disclosures`, `/scanner/technical`, `/scanner/backtests`) ومسارات الـ API العامة (`dailyCacheHeaders` مع `?scope=public` للتوصيات ومؤشرات الشارت) تستخدم `s-maxage=604800` (7 أيام) و`stale-while-revalidate=2592000` (30 يوماً) كي لا تنتهي صلاحية الكاش من إغلاق الخميس إلى افتتاح الأحد أو في الإجازات الرسمية.
     * ملفات إفصاحات الـ PDF (`/api/disclosures/pdf/[id]`) مضبوطة كملفات ثابتة `immutable` لمدة 30 يوماً على الحافة.
  2. **On-Demand Tag Invalidation (`/api/revalidate`):**
     * يرسل خادم بايثون على Hugging Face إشارة إبطال للتاجات (`DAILY_CACHE_TAGS`) فور اكتمال بيانات الجلسة اليومية فقط، بدلاً من إهدار المعالج عبر انتهاء TTL يومي أعمى.
  3. **In-Memory Server & AI Tool Caching:**
     * تكييش نتائج أدوات الشات بوت العامة في بايثون و`web/src/lib/ai/tool-result-cache.ts` و`web/src/lib/cache/market-query-cache.ts` لكل يوم تداول بتوقيت القاهرة.
  4. **Client Session Deduplication & Storage Layer:**
     * توحيد فحص الحصة والتجربة في `web/src/lib/user-quota-client.ts` (`fetchUserQuotaCached`: `in-flight deduplication` + `sessionStorage` 30 دقيقة).
     * تكييش لقطة المحفظة وقائمة المراقبة (`15m`) وتفضيلات المستخدم الخفيفة (`30m`) في `sessionStorage` مع منع تخزين مصفوفات الفحص الضخمة في Supabase `user_settings.app_state`.
     * تعطيل `prefetch` التلقائي للروابط الأرشيفية (`prefetch={false}`) وتجميع تتبع الزيارات بنافذة 6 ساعات للمسار المطبّع (`/stocks/[symbol]`).

---

## 3. أدوار الخدمات الحالية

| الخدمة | الدور | بيئة التشغيل |
|---|---|---|
| **Vercel** | النطاق (`egxbots.com`)، الفرونت إند (Next.js 15)، والـ Edge Caching 7 أيام | حساب `egxbots` (`fra1` Frankfurt) |
| **Supabase** | PostgreSQL مع RLS، جداول الأسهم، محافظ واشتراكات المستخدمين، و`market_cache` | PostgreSQL السحابي (`eu-west-1`) |
| **Hugging Face** | خادم بايثون (FastAPI)، محرك AI Chat الوكيلي، بوت التليجرام، ومهام نهاية اليوم | `weeasdwee/AI_BOT` (Docker) |
| **Resend & ImprovMX** | إرسال الإيميلات الموثقة (DKIM/SPF) واستقبال الردود | سحابي |

للتفاصيل التشغيلية وسجل التحسينات القياسي راجع: [resource-usage-review-2026-10-05.md](file:///c:/Users/MR__CODER__/Desktop/stokscan_AI/docs/resource-usage-review-2026-10-05.md).
