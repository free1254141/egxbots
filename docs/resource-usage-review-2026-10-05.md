# تقرير استهلاك موارد فيرسيل وسوبابيز ومنهجية التكييش الشاملة (Vercel & Supabase Resource Review)
**تاريخ التحديث والاعتماد:** 14 نوفمبر 2026 (2026-11-14)  
**الحالة:** المرجع التشغيلي الموحّد والمعتمد للمشروع (Canonical Production Reference)

---

## 1. التسلسل التاريخي للبنية التحتية وترحيل الحساب (Infrastructure Timeline)

1. **26 أكتوبر 2026 — ترحيل حساب فيرسيل والدومين (Zero-Downtime Migration):**
   * تم ترحيل مشروع الإنتاج وربط الدومين الرسمي `egxbots.com` و`www.egxbots.com` من الحساب القديم (`weeessd57-8552` / مشروع `stokscan-ai-web` / `prj_yhie5E6It045Cd7K5ZXwRLqaUSQi`) إلى فريق `egxbots` الحالي (`acursour-4201` / مشروع `egxbots` / `prj_kvgWiiBMdlFBLMX6sYx8ewJBS7Y7`) على منطقة **Frankfurt (`fra1`)** لتقليل زمن الاستجابة في مصر والشرق الأوسط.
   * > **ملاحظة تشغيلية:** عند مراجعة لوحة فيرسيل القديمة، أي طلبات متبقية على `stokscan-ai-web` ناتجة عن روابط قديمة أو زيارات للـ preview URL فقط، بينما الدومين الرسمي `egxbots.com` يخدم بالكامل من مشروع `egxbots`.

2. **30 أكتوبر 2026 — نقل المهام الثقيلة من فيرسيل إلى Hugging Face:**
   * تم إيقاف كرونات فيرسيل والمكالمات الثقيلة التي كانت تترك دوال Node.js في حالة انتظار (`Idle Wait`):
     * نقل تنبيهات الماسح اللحظي إلى بايثون (`api/scanner_alerts_scheduler.py` و`api/scanner_alerts_engine.py`).
     * نقل توليد تقارير السوشيال والنظرة اليومية إلى بايثون (`api/native_social_reports.py` و`api/daily_market_outlook.py`).
     * إزالة حزم ثقيلة (`tesseract.js`) من فرونت إند `web/` وتقليص حجم الدوال.
     * استمرار شات الذكاء الاصطناعي التفاعلي في البايثون (`api/agentic_chat/`) لتجنيب فيرسيل استهلاك Fluid Active CPU.

3. **6 – 9 نوفمبر 2026 — ضبط Edge Cache وحماية المسارات العامة (`d0cf1f67`):**
   * تفعيل ترويسات `Cache-Control` / `Vercel-CDN-Cache-Control` و`compress: true` في `web/next.config.js`.
   * منع Prefetch بالحروف الكبيرة (`/stocks/SYMBOL` 307 redirects) وتوحيد الروابط إلى lowercase مع `prefetch={false}`.
   * إنشاء مسار `/api/payment/public-config` المخزن على الحافة للزوار العامين، وإضافة `in-flight` deduplication لطلبات التوصيات في `AIScannerContext.tsx`.

4. **12 نوفمبر 2026 — كاش التجربة المجانية (`f7c74983`):**
   * إضافة `Cache-Control: private, max-age=300, stale-while-revalidate=600` لمسار `GET /api/subscription/trial` و`sessionStorage` cache في `TrialWelcomePrompt.tsx` (ما خفّض `/api/subscription/trial` من 402 إلى 61 طلباً، والـ CPU اليومي من `7m 36s` إلى `5m 8s`).

---

## 2. تدقيق 14 نوفمبر 2026: معمارية "صفر CPU في الويك إند وقابلية التوسع لـ 100 ألف زائر"

### أ) المشاكل المرصودة في لقطات Observability وSupabase Logs (13–14 نوفمبر 2026)
رغم انخفاض الزوار في إجازة البورصة (الجمعة 13 نوفمبر: **78 زائراً** فقط)، استهلكت الدوال **`5m 8s` Active CPU** وسُجّل **772 استدعاء** خلال 12 ساعة صباح السبت 14 نوفمبر، مع **935 طلب API Gateway** و**2.95 GB Egress** في Supabase، للأسباب الجذرية التالية:

1. **انتهاء صلاحية كاش 24 ساعة (`86400s`) في عطلة نهاية الأسبوع:** تغلق البورصة الخميس 2:30 عصراً وتفتح الأحد 10:00 صباحاً (~67 ساعة بدون تغيير في البيانات). الكاش ذو الـ 24 ساعة ينتهي مساء الجمعة والسبت، مما يجبر Edge PoPs على إعادة بناء الصفحات والـ APIs رغم توقف السوق.
2. **مسار `/api/ai_bot/recommendations` كان يخرج بترويسة `private` للجميع:** بما يشمل زوار الصفحة الرئيسية المجهولين والماسح العام (`46` استدعاء / `5s` CPU)، ما كان يمنع Edge CDN من تخزينه.
3. **ازدواج فحص الحصة والتجربة (`/api/user/quota` 79 استدعاء + `/api/subscription/trial` 61 استدعاء):** المكونات كانت تستدعي المسارين معاً أو بشكل متزامن عند التحميل الأول دون كاش موحد.
4. **استدعاءات غير لازمة عند كل تحميل صفحة (Global Mount Fetches):**
   * `NotificationContext.tsx`: استدعاء `/api/ai_bot/telegram/bot_username` في كل مرة رغم ثبات الاسم `egxbots_bot`.
   * `AppStateContext.tsx`: استدعاء `/api/symbols/inventory` و`/api/symbols/countries` تلقائياً للزوار العاديين رغم اقتصار الحاجة عليهما للأدمن أو حوار اختيار الدولة.
   * `PortfolioContext.tsx` و`WatchlistContext.tsx`: إعادة جلب بيانات المحفظة وقائمة المراقبة في كل Reload بدون `sessionStorage` cache.
5. **تسريب الباندويث الضخم في Supabase (`user_settings.app_state` — سبب الـ 2.95 GB Egress):** كان `AppStateContext.tsx` يكتب ويقرأ مصفوفات نتائج الفحص الكاملة (مئات الأسهم وتاريخ التوقعات) داخل JSONB في `user_settings.app_state` مع كل حركة مسح.
6. **عاصفة Prefetch في صفحة التقارير (`/reports/[date]/[kind]` — 53 استدعاء):** `<Link>` في `/reports` بدون `prefetch={false}` كان يوقظ عشرات الدوال تلقائياً بمجرد فتح صفحة الأرشيف.
7. **تخطي الكاش في `/api/payment/public-config` (`/payment/easykash/config` مع `cache: "no-store"`) و`/api/disclosures/pdf/[id]` (عميل غير مخبأ).**
8. **خطأ SQL في Supabase:** `42883: operator does not exist: text = uuid` داخل دالة `public.start_pro_trial(p_user_id uuid)` عند مقارنة `local_payment_orders.user_id` (`text`) مع `p_user_id` (`uuid`).

---

### ب) الإصلاحات الجذرية المنفذة بتاريخ 14 نوفمبر 2026

| المحور | الملفات المعدلة | الآلية والنتيجة المستهدفة |
|---|---|---|
| **1. كاش 7 أيام ضد الويك إند (On-Demand Revalidation)** | `web/src/lib/cache/daily.ts`, `web/next.config.js`, `web/src/app/stocks/[symbol]/page.tsx`, `web/src/app/page.tsx`, `web/src/app/reports/page.tsx`, `web/src/app/reports/[date]/[kind]/page.tsx`, `web/src/lib/social/public-reports.ts` | رفع `s-maxage` و`revalidate` لجميع البيانات العامة إلى **7 أيام (`604800s`)** مع `stale-while-revalidate=2592000` (30 يوماً) و`stale-if-error=2592000`. التحديث الفوري يتم حصراً عبر `POST /api/revalidate` بعد انتهاء مهام بايثون اليومية. وإضافة `prefetch={false}` لروابط `/reports`. |
| **2. فتح Edge CDN لـ Recommendations & Chart Markers** | `web/src/app/api/ai_bot/recommendations/route.ts`, `web/src/contexts/AIScannerContext.tsx`, `web/src/app/api/recommendations/chart-markers/route.ts`, `web/src/lib/api.ts` | استخدام `?scope=public` للزوار العامين والصفحة الرئيسية لإرجاع `dailyCacheHeaders(DAILY_CACHE_TAGS.recommendations)` (`public, s-maxage=604800`) وتجاوز فحص الجلسة، مع كاش `sessionStorage` لمدة 30 دقيقة للتوصيات وin-memory `Map` لمدة 30 دقيقة لمؤشرات الشارت. |
| **3. كاش أبدي للـ PDF وإعدادات الدفع العامة** | `web/src/app/api/disclosures/pdf/[id]/route.ts`, `web/src/app/api/payment/public-config/route.ts` | استخدام `getSupabaseClient()` وترويسات `immutable` (`s-maxage=2592000`) لملفات الإفصاحات؛ استبدال `no-store` بـ `next: { revalidate: 86400 }` وترويسة CDN 7 أيام لإعدادات الدفع. |
| **4. توحيد وتخفيف فحص الحصة والتجربة** | `web/src/lib/user-quota-client.ts` (جديد), `web/src/app/api/user/quota/route.ts`, `TrialWelcomePrompt.tsx`, `PricingClient.tsx`, `SupportChatContext.tsx`, `RecommendationsTable.tsx`, `ChatWidget.tsx` | دمج فحص التجربة المجانية (`trial_expires_at` + `trial_eligible`) داخل `/api/user/quota` عبر عميل موحّد `fetchUserQuotaCached()` يجمع `in-flight deduplication` مع `sessionStorage` 30 دقيقة (`egxbots_user_quota_v2:<uid>`). هذا يُنهي طلبات `GET /api/subscription/trial` تماماً (`61 -> 0`). |
| **5. إيقاف استدعاءات التحميل العالمية وسد تسريب Supabase Egress** | `NotificationContext.tsx`, `AppStateContext.tsx`, `PortfolioContext.tsx`, `WatchlistContext.tsx`, `LandingClient.tsx`, `UserActivityTracker.tsx`, `web/src/app/api/portfolio/route.ts` | حذف استدعاء `bot_username` على التحميل؛ قصر `refreshInventory` و`refreshCountries` على الأدمن مع كاش `localStorage` 24 ساعة؛ إزالة مصفوفات الفحص الضخمة من `user_settings.app_state` وتكييشه في `sessionStorage` 30 دقيقة؛ كاش `sessionStorage` 15 دقيقة للمحفظة وقائمة المراقبة وساعة لعناصر الهوم؛ تطبيع مسارات `UserActivityTracker` (`/stocks/[symbol]`) وتخفيفها بنافذة 6 ساعات في `localStorage`. |
| **6. إصلاح خطأ Postgres `text = uuid`** | `supabase/migrations/20261114103000_fix_start_pro_trial_text_uuid.sql` | إضافة `user_id::text = p_user_id::text` داخل `public.start_pro_trial(p_user_id uuid)` عند الاستعلام عن `local_payment_orders` و`subscriptions`، وتطبيق الهجرة على مشروع Supabase الإنتاجي. |

---

## 3. التكامل بين كاش سوبابيز (Supabase) وكاش فيرسيل (Vercel)

### أ) جدول `market_cache` ومصادر البيانات المجمعة
يحتوي جدول `market_cache` في سوبابيز على البيانات المجمعة المحسوبة يومياً عبر بايثون (Hugging Face) بعد إغلاق البورصة:
1. `market_status_Egypt`: ملخص السوق المصري ومؤشرات EGX30 و EGX100 وسعر الصرف.
2. `egx_inventory_eodhd`: حصر الأسهم النشطة وبيانات التداول.
3. `macro_correlation_*`: مصفوفات الارتباط مع الذهب والنفط والدولار.
4. `vip_stock_*` و`scanner_15m:*`: لقطات التحليل والفحص.

### ب) آلية Two-Tier Caching & On-Demand Revalidation
* **دور بايثون (Hugging Face):** ينفّذ الحسابات اليومية مرة واحدة بعد إغلاق الجلسة، يحدّث Supabase، ثم يرسل إشارة إبطال التاجات لـ `POST /api/revalidate` لتطهير الكاش المتأثر فقط (`DAILY_CACHE_TAGS`).
* **دور Vercel Edge & Next.js ISR:** يحتفظ بالصفحات والـ JSON العام لمدة **7 أيام (`604800s`)** في الـ Edge بدون إعادة توليد تلقائية أثناء الإجازات أو ارتفاع عدد الزوار.
* **البيانات الخاصة بالمستخدم:** لا تُخزَّن أبداً على Edge مشترك؛ بل تبقى محمية بـ `private` Headers وRLS، مع تقليل ضغطها بالـ `sessionStorage` قصير/متوسط الأجل (`15m–30m`) وتوحيد الطلبات المتزامنة (`in-flight deduplication`).

---

## 4. قواعد التشغيل والحوكمة للمطورين والوكلاء

1. **الاعتماد على Vercel Edge المباشر:** يمنع استخدام بروكسي كلاودفلير المجاني لتجنب حظر DPI لدى مزودي الإنترنت في مصر (WE / Vodafone).
2. **حماية لوجات واستعلامات Supabase:** يمنع استخدام `SELECT *` على الجداول الضخمة أو فحص لوجات سوبابيز (`query_logs`) في المراجعات الروتينية.
3. **منع الـ `app_state` Bloat:** لا يجوز تخزين نتائج الماسحات (`results`, `scanHistory`, `predictHistory`) داخل `user_settings.app_state` في Supabase.
4. **قاعدة الرفع لـ Git الصارمة:** يمنع تنفيذ `git push` تلقائياً دون طلب أو موافقة صريحة من المستخدم.
