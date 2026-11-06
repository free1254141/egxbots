# تفعيل التجربة المجانية وتحويلها إلى اشتراكات (Trial Activation & Conversion)

> **تاريخ التوثيق:** 6 نوفمبر 2026
> **الحالة:** منفّذ محليًا — لم يُنشر بعد (Vercel + HF Space)
> **النطاق:** الواجهة (`web/`)، باك-إند التسويق (`api/marketing_lifecycle.py`)، لوحة الأدمن

---

## 1. المشكلة التي حلّها هذا العمل

كانت التجربة المجانية (3 أيام Pro) تُفعّل من صفحة الأسعار ثم تتوقف عند **رسالة Toast فقط**:
لا تحويل للشات، لا أول سؤال، ولا بريد ترحيب. النتيجة أن نصف مستخدمي التجربة لم يرسلوا
رسالة واحدة، ومن لم يرسل رسالة لم يشترك أبدًا.

### البيانات التي بُني عليها القرار (6 نوفمبر 2026)

| المجموعة | العدد | اشتركوا | النسبة |
| :--- | ---: | ---: | ---: |
| أنهوا التجربة (17) — فتحوا الشات | 10 | 4 | **40%** |
| أنهوا التجربة (17) — لم يفتحوا الشات | 7 | 0 | **0%** |
| **إجمالي التجارب** | **20** | **4** | **20%** |
| تجارب نشطة وقت القياس | 3 | — | 2 منهم فعّلوا الشات |

**الاستنتاج:** السعر (100 ج.م) ومدة التجربة ليسا العائق؛ العائق هو **عدم استخدام المنتج**.
كل من اشترك استخدم الشات، ولم يشترك أي مستخدم لم يستخدمه.

> ملاحظة منهجية: العينة 20 تجربة. المؤشر قوي ومتسق مع طبيعة المنتج، لكنه ليس إثباتًا إحصائيًا نهائيًا.
> القياس بعد النشر سيحسم الفرق بين A/B.

---

## 2. ما تم تنفيذه

### 2.1 التفعيل التلقائي للشات (Onboarding)

| الملف | الدور |
| :--- | :--- |
| `web/src/lib/trial-onboarding.ts` | نية تفعيل لمرة واحدة + توزيع A/B ثابت لكل متصفح |
| `web/src/app/pricing/PricingClient.tsx` | بعد نجاح التجربة: تجهيز النية وإطلاق حدث `trial-autostart` |
| `web/src/components/ChatWidget.tsx` | يفتح الشات ويرسل أول سؤال تلقائيًا مرة واحدة (ويغطي حالة الـRefresh) |

**التدفق:**

```
ضغط "ابدأ التجربة"
  └─ POST /api/subscription/trial  (مع variant)
       ├─ start_pro_trial RPC
       ├─ insert user_activity_events(event_name='trial_started', metadata.variant)
       └─ response success
            └─ prepareTrialAutostart()  → sessionStorage (مرة واحدة)
                 └─ dispatch('trial-autostart')
                      └─ ChatWidget: open + sendMessage(prompt) مرة واحدة
```

**النسخ المستخدمة (A/B):**

| النسخة | السؤال الأول |
| :--- | :--- |
| A | «رشّح لي 3 أسهم عليها فرصة شراء النهارده، مع سعر الدخول ووقف الخسارة والهدف» |
| B | «حلّل لي سهم COMI فنياً وقولّي مناطق الدخول والخروج المناسبة» |

التوزيع يُخزَّن في `localStorage` تحت `egxbots_trial_variant_v1` حتى تبقى المقارنة بين مجموعتين متسقتين.
النية تُخزَّن في `sessionStorage` تحت `egxbots_trial_autostart_v1` وتُحذف بعد الاستهلاك أو عند فشل التفعيل
(`clearTrialAutostart`) حتى لا تُرسل رسالة غير مقصودة لاحقًا.

### 2.2 بريد Day 0 و Day 1

الملف: `api/marketing_lifecycle.py`

| الحملة | `message_type` | نافذة التوقيت | المحتوى |
| :--- | :--- | :--- | :--- |
| ترحيب بدء التجربة | `trial_welcome` | بدأت التجربة قبل 5 دقائق إلى 24 ساعة | «اسأل أول سؤال» + CTA يفتح الشات + مكافأة ربط تيليجرام (+10 رسائل) |
| تنشيط اليوم الأول | `trial_day1` | بدأت التجربة قبل 20–48 ساعة وتجربتها ما زالت نشطة | 3 أسئلة جاهزة + CTA يفتح الشات |
| قرب الانتهاء | `trial_expiring` | أقل من 24 ساعة على الانتهاء | (موجودة مسبقًا) تثبيت اشتراك Pro |

**الحواجز المطبّقة على الحملتين الجديدتين:**

- تخطي من لديه اشتراك Pro مدفوع نشط.
- تخطي من استلم نفس النوع خلال 30 يومًا (`marketing_message_log`).
- احترام إلغاء الاشتراك (`marketing_preferences`).
- الخضوع للحد اليومي `MARKETING_DAILY_EMAIL_CAP` (افتراضي 90).
- عزل الأخطاء لكل مستخدم على حدة.

### 2.3 قياس الفانل

| الحدث | يُسجَّل من | متى | الغرض |
| :--- | :--- | :--- | :--- |
| `trial_started` | `api/subscription/trial` (server-side) | نجاح RPC | لا يُفقد حتى لو أُغلقت الصفحة |
| `trial_first_message` | `web/src/app/api/ai-chat/route.ts` (server-side) | أول رسالة داخل نافذة التجربة | قياس التفعيل الحقيقي |

آلية «أول رسالة»: نافذة الحصة للمشترك تبدأ من `current_period_start`، لذا `monthlyUsed === 0`
تعني أول رسالة داخل التجربة. مع فحص وجود الحدث مسبقًا لمنع التكرار.

الجداول: `user_activity_events` (RLS + service_role فقط)، `ai_chat_messages`.

### 2.4 لوحة الأدمن

| الملف | الدور |
| :--- | :--- |
| `web/src/lib/trial-funnel.ts` | حساب القمع (دالة نقية قابلة للاختبار) |
| `web/src/app/api/admin/trials/funnel/route.ts` | `GET` أدمن فقط: يجمع trials + subscriptions + رسائل + أحداث |
| `web/src/app/admin/components/BillingTab.tsx` | كارت «قمع التجربة المجانية» داخل تبويب Billing |

**مخرجات القمع:**

- `total` / `active` / `finished`
- `activated` (أرسل رسالة واحدة على الأقل بعد بداية التجربة)
- `converted` (اشتراك مدفوع نشط بدأ في/بعد بداية التجربة)
- `activationRateFinished` / `conversionRateFinished`
- تفصيل A/B: بدأ / فعّل / اشترك

**تعريفات حاسمة:**

- **Activated:** رسالة مستخدم واحدة على الأقل بعد `trial.started_at` (سجل الرسائل الفعلي، لا جدول الحصص).
- **Paid/Converted:** صف في `subscriptions` بحالة `active`، خطة مدفوعة، وليس `provider='trial'`،
  وبدأ في/بعد `trial.started_at`. الاشتراك الملغى لا يُحتسب «مدفوعًا الآن».

---

## 3. الملفات المتأثرة

```
web/src/lib/trial-onboarding.ts                       (جديد)
web/src/lib/trial-funnel.ts                           (جديد)
web/src/lib/__tests__/trial-onboarding.test.ts        (جديد)
web/src/lib/__tests__/trial-funnel.test.ts            (جديد)
web/src/app/api/admin/trials/funnel/route.ts          (جديد)
web/src/app/api/subscription/trial/route.ts           (تسجيل trial_started + variant)
web/src/app/api/ai-chat/route.ts                      (تسجيل trial_first_message)
web/src/app/pricing/PricingClient.tsx                 (تفعيل تلقائي بعد التجربة)
web/src/components/ChatWidget.tsx                     (استقبال الحدث + أول سؤال)
web/src/app/admin/components/BillingTab.tsx           (كارت القمع)
api/marketing_lifecycle.py                            (trial_welcome + trial_day1)
docs/marketing-lifecycle-engine.md                    (تحديث الحملات)
```

---

## 4. التحقق

| الفحص | الأمر | النتيجة |
| :--- | :--- | :--- |
| TypeScript | `cd web && node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json` | ✅ 0 أخطاء |
| Jest (جديد + ChatWidget) | `node node_modules/jest/bin/jest.js src/components/__tests__/ChatWidget.test.tsx src/lib/__tests__/trial-*.test.ts` | ✅ 16/16 |
| Python compile | `python -m py_compile api/marketing_lifecycle.py` | ✅ |
| Marketing tests | `python -m pytest tests/test_marketing_tracking.py -q` | ✅ 4/4 |

> بيئة العمل الحالية ليس بها `web/node_modules`؛ استُخدم junction مؤقت إلى نسخة الـworktree الرئيسي
> لتشغيل Jest/tsc فقط (غير مرتبط بالـGit).

---

## 5. النشر والتشغيل

### المطلوب

1. **Vercel:** نشر تعديلات `web/` (الواجهة + API + لوحة الأدمن).
2. **HF Space:** نشر تعديلات `api/marketing_lifecycle.py` حتى تعمل حملتا Day 0/Day 1.

### بعد النشر — ماذا تراقب

| المؤشر | مكانه | التوقع |
| :--- | :--- | :--- |
| `trial_started` | `user_activity_events` | يزيد فور كل تفعيل |
| `trial_first_message` | `user_activity_events` | يجب أن يقترب من `trial_started` |
| القمع | `/admin` → Billing | Trials → Activated → Paid |
| A/B | نفس الكارت | مقارنة A و B بعد 7–14 يومًا |
| رسائل البريد | `marketing_message_log` | `trial_welcome`, `trial_day1`, `trial_expiring` |

### معايير نجاح مقترحة (7–14 يومًا)

- نسبة التفعيل (Activated / Finished) ≥ 80% بدل ~59% الحالية.
- معدل التحويل بين المفعّلين ≥ 40% (ثابت تقريبًا) → مضاعفة الاشتراكات بنفس عدد التجارب.
- اختيار النسخة الأعلى في A/B والاحتفاظ بها كافتراضي.

---

## 6. ملاحظات وقيود

1. **`FREE_CHAT_MESSAGES` غير مُستخدم حاليًا:** القيمة على HF Space هي `50`، لكن
   `web/src/lib/ai/plan-gate.ts` و`api/plan_limits.py` يثبّتان حد Free على **10**.
   أي تغيير لحد Free يتطلب تعديل كود، وليس متغير بيئة فقط.
2. **القياس تاريخيًا:** قبل نشر حدث `trial_first_message`، القمع يعتمد على سجل `ai_chat_messages`،
   لذا يعمل للبيانات القديمة أيضًا.
3. **`trial_started`** يسجّل variant؛ الأحداث القديمة قبله ستظهر بدون A/B (تظهر في `total` فقط).
4. **التجربة A/B** توزيع عشوائي 50/50 لكل متصفح، وليست على مستوى الحساب؛ مسح تخزين المتصفح يعيد التوزيع.
5. **لا يوجد تعديل على الأسعار أو مدة التجربة** في هذا العمل؛ التغيير كله في التفعيل والقياس.

---

## 7. أوامر مرجعية سريعة

```bash
# تشغيل حملات دورة الحياة يدويًا (بيئة السيرفر)
python -c "from api.marketing_lifecycle import MarketingLifecycleEngine; print(MarketingLifecycleEngine.run())"

# حملتا التجربة فقط
python -c "from api.marketing_lifecycle import process_trial_welcome, process_trial_day1; print(process_trial_welcome(), process_trial_day1())"
```

```bash
# اختبارات الواجهة
cd web
node node_modules/jest/bin/jest.js src/lib/__tests__/trial-onboarding.test.ts src/lib/__tests__/trial-funnel.test.ts
```
