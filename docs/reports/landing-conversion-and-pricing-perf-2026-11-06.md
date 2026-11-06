# تحسين التحويل + سرعة صفحة التسعير — 2026-11-06

> **السياق:** 612 زائر / 7 أيام، 52% Bounce، **7 تسجيلات فقط** يوم 5 نوفمبر (~4.7% تحويل)،
> و`/pricing` عليها 97 زائر لكنها كانت تعرض شاشة تحميل في كل مرة.
> **الإعلانات المدفوعة لم تكن تعمل** (مراجعة + شهادة Financial Services مطلوبة)،
> فالمصدر الفعلي للزيارات كان حملة الإيميل (143 رسالة / 41 فتح / 19 كليك).

---

## 1. لماذا كانت `/pricing` "تحمّل في كل مرة"

قياس فعلي على الإنتاج:

| الطلب | النتيجة |
| --- | --- |
| الأول | `cache=PRERENDER`, TTFB **1107ms** |
| الثاني | `cache=HIT`, TTFB **242ms** |
| الثالث | `cache=HIT`, TTFB **280ms** |

الـ HTML مكاش فعلاً — المشكلة كانت في العميل:

1. `PricingClient` يبدأ بـ `loading = true` ولا يعرض أي سعر قبل وصول الإعدادات.
2. الإعدادات تأتي من `/api/payment/easykash/config` التي تحلّ جلسة Supabase لكل طلب،
   لذلك تفرض `Cache-Control: no-store` و**تُنفّذ دالة في كل زيارة** (CDN = MISS دائماً).
3. المتصفح لا يستطيع إعادة استخدام الرد (`no-store`)، فحتى الرجوع للخلف يعيد التحميل.

### الحل المنفَّذ
- مسار جديد `GET /api/payment/public-config` — إعدادات عامة بدون مصادقة،
  `Vercel-CDN-Cache-Control: public, s-maxage=300, stale-while-revalidate=3600`.
- `PricingClient` يستخدم المسار العام للزائر غير المسجل، والمسار الخاص فقط
  بعد تسجيل الدخول (لأن سعر `is_grandfathered_renewal` يخص المستخدم).
- **لم نُلغِ الخصوصية:** المسار الخاص باقٍ كما هو لجميع المستخدمين المسجلين.

**النتيجة المقاسة:** الطلب الثاني على المسار العام صار `HIT` في **157ms** بدل ~1.6 ثانية.

---

## 2. كاش صفحة الهبوط (24 ساعة)

| الملف | التغيير |
| --- | --- |
| `web/src/app/page.tsx` | Server Component صغير: `export const revalidate = 86400` |
| `web/src/app/LandingClient.tsx` | محتوى الصفحة + تعديلات التحويل |
| `web/src/app/api/market/proof/route.ts` | 24 ساعة: Data Cache + CDN `s-maxage=86400` + تاق `daily-recommendations` |

`/api/scan/news` و`/api/scan/similarity/published` كانا **بالفعل** يستخدمان
`dailyCacheHeaders` — لم يُغيَّرا. `/api/market/status` بقي على 300 ثانية عن قصد:
يعرض حالة السوق اللحظية (مفتوح/مغلق/اتجاه) وكاش يوم كامل كان سيعرض حالة خاطئة.

**التحقق:** `.next/prerender-manifest.json` → `"/": initialRevalidateSeconds = 86400`.

---

## 3. تغييرات صفحة الهبوط (التحويل)

| # | التغيير | الملف |
| --- | --- | --- |
| 1 | **زر أساسي مباشرة تحت الوعد**: «ابدأ مجاناً — بدون كارت» + ثانوي «شوف توصيات النهاردة» | `LandingClient.tsx` |
| 2 | **سطر إثبات حقيقي**: `معدل نجاح 58% على 144 توصية مغلقة` من `/api/market/proof` | `LandingClient.tsx` |
| 3 | **حذف الشهادات المختلقة** واستبدالها بـ 4 أرقام موثقة (توصيات / مغلقة / معدل نجاح / مستخدمين) | `LandingClient.tsx` |
| 4 | **شريط CTA ثابت للموبايل** بعد 700px تمرير | `LandingClient.tsx` |
| 5 | **«متابعة بجوجل» أصبح الزر الأساسي** في صفحة التسجيل (كان تحت الفورم) | `signup/page.tsx` |
| 6 | **«ابدأ بجوجل» في الهيرو** (ضغطة واحدة، بدون المرور على الفورم) + نسخة أيقونة في الشريط الثابت | `LandingClient.tsx` |
| 7 | **قسم تسعير مختصر**: 3 مدد Pro (شهري / 6 أشهر / سنوي) بأسعار من الكونفيج العام المكاش، كل كارت → `/pricing?plan=<id>`؛ المقارنة الكاملة وباقة lifetime باقيين في صفحة التسعير | `LandingClient.tsx` |

### أحداث التتبع (GTM)
`pricing_view` · `checkout_login_required` · `signup_start` · `signup_complete` ·
`signup_google_start` · `hero_cta_click` · `sticky_cta_click` · `landing_pricing_click`

> روابط الإيميل كانت **بالفعل** deep links (`/pricing?plan=pro`, `/scanner/technical`,
> `/fair-value`) — لا حاجة لتعديلها.

---

## 4. ما لم يُنفَّذ (وسبب)

| البند | السبب |
| --- | --- |
| فصل صفحة الدفع في route مستقل | إعادة هيكلة كبيرة لـ `PricingClient` (1900 سطر) ومخاطرة على مسار دفع حقيقي |
| رندر السوق والأخبار على السيرفر (ISR) | يتطلب تفكيك `LandingClient` إلى Server + Client؛ مكسب أقل من المخاطرة |
| باقة lifetime في قسم الهبوط | لإبقاء القسم خفيفاً — موجودة في صفحة التسعير |

---

## 5. التحقق

| الفحص | النتيجة |
| --- | --- |
| `npx tsc --noEmit` | ✅ 0 أخطاء |
| `npx jest --testPathPattern="recommendation"` | ✅ 40/40 |
| `npx jest pricing-entitlement-refresh` | ✅ 1/1 |
| `npm run build` | ✅ نجاح (exit 0) |
| `/api/market/proof` | 1121ms → **114ms** (CDN HIT) |
| `/pricing` | 716ms → **185ms** (CDN HIT) |
| صفحة الهبوط (DOM حقيقي) | زر جوجل + «معدل نجاح 58% على 144 توصية مغلقة» ظاهرين ✅ |

### الخطوة التالية
قياس `pricing_view → landing_pricing_click → signup_complete` لمدة أسبوع بعد النشر.
