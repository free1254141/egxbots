# تقرير فحص وإصلاح نظام ترخيص مجموعات تليجرام (B2B System Audit & Status — Nov 2026)

> **التاريخ:** 2026-11-15  
> **النطاق:** البنية التحتية الكاملة لنظام **B2B Telegram Group Bot Licensing** (قاعدة البيانات Supabase، معالجة المدفوعات، بوت التليجرام، لوحة تحكم المالك والأدمن، وتكاليف الموارد/التوكن).

---

## 1. الحالة الراهنة في قاعدة البيانات (Live Database Snapshot)

- **الجداول والسياسات النشطة:**
  - `public.b2b_group_licenses`: الرخص (النشطة / الموقوفة / المنتهية).
  - `public.b2b_group_member_usage`: عداد الاستخدام اليومي والكولد-داون (90 ثانية / 15 استفسار للعضو يومياً).
  - `public.b2b_trial_chat_history`: سجل مجموعات التليجرام التي استهلكت الفترة التجريبية (لمنع تكرار التجارب المجانية بحسابات متعددة).
- **البيانات الفعلية المسجلة وقت التوثيق:**
  - إجمالي الرخص المسجلة: **1 رخصة تجريبية** (`id: 9af81f17-4e66-4af1-9470-841ad135cbcf`, `tier: b2b_pro`, `order_id: B2B-TRIAL-4OTBEP`).
  - حالة الربط: **غير مربوطة بمجموعة تليجرام بعد** (`telegram_chat_id IS NULL`) وانتهت صلاحيتها في `2026-11-14 20:45:35 UTC`.
  - مجموعات التفعيل المربوطة حالياً: **0 مجموعة**.

---

## 2. المشاكل والكسور والثغرات التي تم اكتشافها وإصلاحها

### أ. الكسور الحرجة في المدفوعات وتفعيل الباقات (Billing & Entitlements)
1. **انهيار الدفع الأوتوماتيكي لباقات B2B (`api/payment_common.py`):**
   - **الخلل السابق:** دالة `activate_subscription()` كانت تستدعي RPC `activate_easykash_subscription` أولاً لباقات `b2b_starter` و `b2b_pro` و `b2b_enterprise`، والتي ترفض أي خطة ليست ضمن `('pro','pro_6m','pro_1y','lifetime')` وترمي خطأ SQL (`Unsupported Pro plan`) قبل الوصول لكود B2B أصلاً! كما أن معالج B2B اللاحق كان غير ذري (non-idempotent) ويزود رخصة واحدة فقط لباقة `b2b_enterprise` بدلاً من **مجموعتين**.
   - **الإصلاح:** إضافة دالة RPC ذرية محمية بـ `pg_advisory_xact_lock` و `payment_entitlement_events` باسم `public.activate_b2b_group_license(p_user_id, p_tier, p_duration_days, p_payment_order_id)` تدعم:
     - تفعيل وترقية حتى **رخصتين منفصلتين** لباقة `b2b_enterprise` و**رخصة واحدة** لباقات `b2b_starter` / `b2b_pro`.
     - استبدال `order_id` التجريبي (`B2B-TRIAL-*`) برقم الطلب المدفوع وتمديد الصلاحية من `GREATEST(expires_at, NOW())`.
     - توجيه `activate_subscription()` مبكراً لخطط `b2b_*` نحو `activate_b2b_group_license` حصراً.
2. **معالجة ما بعد الدفع لطلبات B2B (`api/easykash_payments.py` & `api/direct_wallet_payments.py`):**
   - **الخلل السابق:** كلا المزودين كانا يبحثان في جدول `subscriptions` ويحاولان توليد رابط قناة Pro VIP وإرساله بعد التفعيل.
   - **الإصلاح:** عزل مسار `b2b_*` ليقرأ `expires_at` من `b2b_group_licenses` ويرجع `b2b_dashboard_url: "https://egxbots.com/b2b/dashboard"`.
3. **إصلاح عمولة الأفلييت في الدفع بالمحافظ (`api/direct_wallet_payments.py`):**
   - **الخلل السابق:** البحث عن `aff_val.get("affiliate_id")` بينما `validate_affiliate_code()` ترجع `"id"`، مما أسقط جميع العمولات والخصومات في الدفع المباشر بالمحافظ، دون منع الإحالة الذاتية.
   - **الإصلاح:** استخدام `aff_val.get("id") or aff_val.get("affiliate_id")` وإضافة حارس منع الإحالة الذاتية (`aff_owner == user_id`).

### ب. الثغرات الأمنية وتسريب البيانات (Security & RLS Leaks)
1. **تسريب بيانات الرخص والعملاء عبر RLS العام (`supabase`):**
   - **الخلل السابق:** سياسة `Allow public read of active licenses by chat id` سمحت لـ `anon` و `authenticated` بقراءة `b2b_group_licenses` (بما يشمل `id` و `order_id` و `telegram_chat_id`)، وسياسة `Allow owners to read and update their licenses` سمحت للمالك بتعديل أي عمود (`daily_limit`, `expires_at`, `status`) مباشرة عبر PostgREST.
   - **الإصلاح:** حصر السياسات السابقة على `service_role`، وإنشاء سياسة `Allow owners to read their licenses` (`SELECT` فقط لـ `owner_user_id = auth.uid()`)، مع حصر تنفيذ `check_and_consume_b2b_group_quota` و `activate_b2b_group_license` على `service_role` فقط (`REVOKE ALL ... FROM PUBLIC, anon, authenticated`).
2. **ثغرة ربط الرخص والاختطاف (`/activate` & `/api/b2b/license`):**
   - **الخلل السابق:**
     - كان يمكن إرسال `/activate a` ليطابق أي `order_id` يحتوي على حرف `a` (substring matching) دون التحقق من صلاحيات Admin في الجروب أو تاريخ الانتهاء أو ارتباط الرخصة بمجموعة أخرى.
     - لم تكن واجهة `/api/b2b/license` تتحقق من `auth.getUser()` (كانت تستخدم `getSession()`) وكانت تسمح بتمرير `telegram_chat_id` تعسفياً أو خطف رخص مملوكة لآخرين.
   - **الإصلاح:**
     - اشتراط كود بطول **8 أحرف على الأقل** ومطابقة تامة للـ UUID / البادئة / `order_id`.
     - التحقق من انتهاء الصلاحية (`expires_at > NOW()`) ومن عدم ارتباط الرخصة بمجموعة تليجرام أخرى مسبقاً.
     - التحقق في تليجرام عبر `getChatMember` بأن مرسل `/activate` هو `administrator` أو `creator` في المجموعة.
     - التحقق من الهوية عبر `getUser()` وتنفيذ التعديلات عبر `service_role` (`web/src/lib/b2b-server.ts`)، ومنع غير الأدمن من تغيير `telegram_chat_id` يدوياً مع إضافة إجراء `unlink` الآمن لفك ربط المجموعة.
3. **منع تعدد التجارب المجانية لنفس الجروب (`b2b_trial_chat_history`):**
   - **الخلل السابق:** إنشاء حسابات إيميل جديدة كان يتيح تفعيل تجربة 3 أيام جديدة لنفس جروب التليجرام بلا حد.
   - **الإصلاح:** تسجيل أول تجربة على مستوى `telegram_chat_id` ومنع إعادة ربط أي رخصة `B2B-TRIAL-*` أخرى على نفس الجروب.

### ج. استهلاك التوكن، دقة الوقت، وموارد السيرفر (Token & Resource Guards)
1. **توقيت تصفير الكوتة اليومي (`Africa/Cairo` vs UTC):**
   - **الخلل السابق:** دالة SQL استخدمت `CURRENT_DATE` (بتوقيت UTC) بينما ذاكرة Python تستخدم `Africa/Cairo`، مما سبّب فارق ساعتين عند منتصف الليل.
   - **الإصلاح:** توحيد الدالة لاستخدام `(NOW() AT TIME ZONE 'Africa/Cairo')::DATE`.
2. **منع استهلاك الكوتة على رسائل المساعدة أو الرد على بوتات أخرى (`api/telegram_b2b.py`):**
   - **الخلل السابق:**
     - كتابة `@egxbots_bot` بدون سؤال كانت تستهلك رصيداً من كوتة المجموعة وتُفعل الكولد-داون قبل عرض رسالة المساعدة.
     - الرد على أي بوت آخر في الجروب (مثل Rose أو GroupHelp) كان يُشغّل بوتنا ويستهلك كوتة وتوكن!
   - **الإصلاح:** فحص `reply_to_message.from.username` لتجاهل البوتات الأخرى، وتنفيذ دالة مساعدة للقراءة فقط قبل استهلاك الكوتة لرسائل `@egxbots_bot` الفارغة و `/help`.
3. **حارس التزامن (`_B2B_SEMAPHORE`) وجلسات المحادثة وروابط الدعوة:**
   - عند انتهاء مهلة `_B2B_SEMAPHORE.acquire(timeout=60)` (`not acquired`)، يعتذر البوت فوراً بدون استدعاء LLM أو استهلاك توكن.
   - توحيد `session_id` في `api/native_telegram_vip_chat.py` لكل مجموعة (`tg-b2b-group-{chat_id}`) بدلاً من إنشاء جلسة منفصلة لكل عضو.
   - تقليل حد التجربة المجانية (`web/src/lib/b2b-server.ts`) إلى **30 استفسار/يوم** لمدة 3 أيام (بدلاً من 120–250/يوم) لتفادي استنزاف التوكن في التجارب المجانية.
   - إزالة استدعاء `exportChatInviteLink` من `GET /api/admin/b2b` (كان يُبطل رابط الدعوة الأساسي للجروب مع كل فتح للوحة الأدمن!) وإضافة كاش مؤقت 5 دقائق لـ `getChat`.
4. **واجهة لوحة تحكم المالك (`web/src/app/b2b/dashboard/B2BDashboardClient.tsx`):**
   - تفعيل مبدّل المجموعات المتعددة لعملاء `b2b_enterprise` (لعرض وإدارة المجموعتين)، إضافة زر **فك الربط (Unlink)**، ودعم تبديل السوق (`useMarket()` لـ `EGX BOTS` / `TASI BOTS`).

### د. إصلاحات توجيه وربط المجموعات في تليجرام (`api/telegram_bot.py` & `api/telegram_vip_chat.py`)
1. **منع اختطاف أمر `/ask` والردود في المجموعات الخارجية (`api/telegram_vip_chat.py`):**
   - **الخلل السابق:** `is_vip_chat_update()` كانت تلتقط أي رسالة `/ask` أو `/vippanel` أو رد داخل أي مجموعة خارجية وتحولها لمسار `telegram_vip_chat` الفردي متجاوزةً رخصة B2B والكوتة والتوقيع المخصص!
   - **الإصلاح:** قصر `is_vip_chat_update()` على التوبيك الرسمي (`1680` في `DEFAULT_VIP_GROUP_ID`) والشات الخاص فقط، لتصل كافة رسائل وأوامر المجموعات الأخرى حصرياً إلى `handle_b2b_group_message()`.
2. **دعم كافة سيناريوهات ربط الجروبات دون أعطال (`api/telegram_b2b.py` & `api/telegram_bot.py` & `web/`):**
   - **الأدمن المتخفي (Anonymous Admin):** دعم رسائل المشرف المتخفي (`id: 1087968824` مع `sender_chat.id == chat_id`) لتنجح أوامر `/activate` و `/start@egxbots_bot` والاستفسارات في الجروبات المفعّل بها وضع الإخفاء.
   - **الجروبات ذات المواضيع (Forum Topics):** تمرير `message_thread_id` في كافة ردود `/activate` و `/start`.
   - **ترقية المجموعة لـ Supergroup (`migrate_to_chat_id`):** ترحيل `telegram_chat_id` تلقائياً في `b2b_group_licenses` و`b2b_trial_chat_history` عبر `handle_b2b_chat_migration()`.
   - **الترحيب التلقائي عند الإضافة اليدوية (`my_chat_member`):** إرسال تعليمات التفعيل (`/activate`) تلقائياً لمرة واحدة عندما يضيف المستخدم البوت يدوياً من تليجرام بدون رابط عميق.
   - **طلب صلاحية المشرف بالرابط العميق + إنقاذ الخاص:** إضافة `&admin=delete_messages+pin_messages` في روابط `startgroup=activate_...`، ومعالجة نقر رابط التفعيل في المحادثة الخاصة بإرسال زر مباشر لاختيار المجموعة، بالإضافة لدعم `caption` الصور وتجاهل الأوامر الموجهة لبوتات أخرى (`/help@MissRose_bot`).

---

## 3. الملفات المعدلة والمضافة

- **قاعدة البيانات (SQL):**
  - `supabase/migrations/20261115183000_fix_b2b_security_quota_and_enterprise.sql` (مطبّقة على `gfcmaxbtscmizsakarvc`).
  - `supabase/migrations/20261115200000_b2b_allow_recs_and_tg_portfolio.sql` (مطبّقة على `gfcmaxbtscmizsakarvc` — إضافة عمود `allow_recommendations` وعمود `portfolio_state JSONB`).
- **الخادم البايثون (`api/`):**
  - `api/payment_common.py`
  - `api/direct_wallet_payments.py`
  - `api/easykash_payments.py`
  - `api/telegram_bot.py`
  - `api/telegram_vip_chat.py`
  - `api/telegram_b2b.py`
  - `api/native_telegram_vip_chat.py`
  - `api/agentic_chat/pipeline.py`
  - `api/agentic_chat/tools_execution.py`
  - `api/agentic_chat/analysis_cache.py`
- **تطبيق الويب (`web/src/`):**
  - `web/src/lib/b2b-server.ts`
  - `web/src/app/api/b2b/trial/route.ts`
  - `web/src/app/api/b2b/license/route.ts`
  - `web/src/app/api/admin/b2b/route.ts`
  - `web/src/app/b2b/B2BLandingClient.tsx`
  - `web/src/app/b2b/dashboard/B2BDashboardClient.tsx`
  - `web/src/app/admin/components/B2BTab.tsx`
- **الاختبارات (`tests/`):**
  - `tests/test_telegram_b2b.py`
  - `tests/test_native_telegram_vip_chat.py`

---

## 4. نظام التحكم بالتوصيات والمحفظة الخاصة (Option 2 & Zero-Login TG Portfolio)

### أ. التحكم الكامل في قفل وتفعيل التوصيات لكل جروب (`allow_recommendations`):
1. **قفل افتراضي لحماية استراتيجيات الشركات:** قيمة `allow_recommendations` تكون `FALSE` تلقائياً لأي رخصة B2B جديدة (تحليل فني ومستويات ودعوم وقيمة عادلة فقط).
2. **التحكم التبادلي من 3 واجهات:**
   - من داخل جروب التليجرام لأدمن المجموعة: `/b2b_recs off|on` أو `/recs_off` / `/recs_on` (بدون استهلاك كوتة).
   - من لوحة تحكم المالك: زر تبديل فوري وحفظ مع التوقيع (`web/src/app/b2b/dashboard/B2BDashboardClient.tsx`).
   - من لوحة تحكم الأدمن: مبدّل حالة وتعديل مباشر في نافذة الرخص (`web/src/app/admin/components/B2BTab.tsx`).
3. **عزل ومنع تسريب الكاش والتوصيات:**
   - استبعاد دالة `get_recommendations` من أدوات النموذج وفرض حظر صارم عبر `_ALLOW_RECOMMENDATIONS_CTX`.
   - استبعاد كاش التوصيات الأسبوعية والمفتوحة (`vip_open_recommendations` و `vip_recs_*`) عبر `is_recommendation_cache_key`.
   - عزل كاش تحليل B2B عن كاش الويب/VIP العام عبر `resolve_scoped_cache_key` (`b2b_norecs:*`) لمنع تسرب التوصيات وروابط القنوات.
   - إخفاء إشارات `active_recommendation` من نتائج أداة `get_stock_levels` عند القفل وفصل كاش الأداة (`:rec=0|1`).

### ب. نظام المحفظة الخاصة في تليجرام بدون تسجيل على الموقع:
1. **توجيه فوري من الجروبات للخاص (0 توكن وحماية للخصوصية):**
   - أي استفسار أو أمر محفظة في الجروب (`/portfolio` أو محادثة) يتم الرد عليه بزر تحويل فوري للخاص: `https://t.me/egxbots_bot?start=b2b_portfolio`.
   - حظر أي استدعاء لأداة `manage_portfolio` داخل الجروبات عبر `_GROUP_PORTFOLIO_BLOCKED_CTX` وإرجاع `redirect_private` فوراً بدون مساس بجدول `positions`.
2. **حفظ وتحليل المحفظة في الشات الخاص بدون حساب ويب:**
   - حفظ المحفظة في عمود `portfolio_state JSONB` بجدول `telegram_vip_chat_state` معزولة برقم `telegram_user_id` وأقفال تزامن per-user lock.
   - إتاحة كافة عمليات الإضافة والحذف والتعديل وتعيين الكاش والبيع والتحليل بالكتابة أو سكرين شوت المحفظة مع تخصيص الردود (`personalize_cached_analysis`) تلقائياً.

---

## 5. التحقق والاختبارات (Verification)

- `python -m pytest tests/test_telegram_b2b.py tests/test_telegram_vip_chat.py tests/test_native_telegram_vip_chat.py tests/test_manage_portfolio_cash_and_watchlist.py tests/test_agentic_chat_auth_and_isolation.py tests/test_agentic_chat_optimization_and_cache.py -v` → **91 passed / 0 failed**.
- `cd web && npx tsc --noEmit` → **Exit code 0** بدون أي أخطاء نوعية أو واجهات مفقودة.
- فحص حي للبوت على Telegram API (`getMe` / `getWebhookInfo`): `@egxbots_bot` مفعّل بـ `can_join_groups: true` وWebhook نشط على `https://weeasdwee-ai-bot.hf.space` بدون أخطاء أو تحديثات معلّقة (`pending_update_count: 0`).
- فحص حي على قاعدة بيانات Supabase (`gfcmaxbtscmizsakarvc`): تطبيق المايجريشنين بنجاح (`20261115183000` و `20261115200000`).

---

## 6. ملاحظة التشغيل والنشر (Deployment Note)

- تعديلات Python (`api/*.py`) تحتاج مزامنتها مع Hugging Face Space (`weeasdwee/AI_BOT`) وفق قاعدة نشر البايثون فقط ليتم تفعيلها على بيئة الإنتاج (`weeasdwee-ai-bot.hf.space`).
- تعديلات الويب (`web/`) والمايجريشن (`supabase/migrations/`) جاهزة محلياً، ولم يتم تنفيذ أي `git push` التزاماً بقواعد المستودع.
