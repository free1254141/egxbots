# كفاءة التشغيل اليومي ومرجع القياس (Daily Operations Efficiency & Benchmark)

> **تاريخ الإنشاء:** 2026-11-20 (توقيت القاهرة)
> **الغرض:** مرجع قياس عملي (Before / After) لتسريع التشغيل اليومي لجميع الأسواق وتقليل استهلاك CPU والشبكة على Hugging Face (`2 vCPU`) وSupabase، مع حسم قرار نسخة البايثون وOperations Research.
> **مراجع مرتبطة:** [المرجع التاريخي (14 أكتوبر)](daily-operation-reference.md) · [التشغيل الحالي (13 أكتوبر)](daily-operation-current.md) · [مراجعة الموارد](resource-usage-review-2026-10-05.md)

---

## 1. خط الأساس الفعلي المقاس (Baseline — جلسة `2026-11-19`)

جميع الأزمنة التالية **مقاسة فعلياً** من جدول `daily_job_runs` لآخر تشغيل مكتمل لكل نوع:

| التشغيل (`job_type`) | الزمن الكلي | أكبر 3 مستهلكين للوقت (مقاس) | الحالة |
|---|---:|---|---|
| **`daily_bot`** (إغلاق مصر) | **1028.1s** (`17.13m`) | `ml_scores_update` (**191.3s**) · `historical_similarity` (**54.9s**) · `update_positions` (**50.6s**) · تكرار `refresh_market_status` (**37.5s + 41.3s = 78.8s**) | مكتمل (مع تأخير انتظار `critical_recommendation_prices` الموازي) |
| **`daily_midday`** (منتصف مصر) | **834.5s** (`13.91m`) | `ml_scores_update` (**210.0s**) · `refresh_market_status_for_gate` (**37.6s**) · `short_swings_daily` (**25.3s**) | مكتمل |
| **`saudi_close`** (إغلاق السعودية + الخليج) | **1309.6s** (`21.83m`) | `gcc_metals_sync` (**428.7s**) · `saudi_systems_backtests` (**329.1s**) · `saudi_pipeline_bootstrap` (**283.7s**) · الأخبار (`81.0s + 68.8s = 149.8s`) | مكتمل |
| **`saudi_midday`** (منتصف السعودية + الخليج) | **751.5s** (`12.53m`) | `gcc_metals_sync` (**399.8s**) · `saudi_intraday_refresh` (**177.1s**) · `saudi_price_sync` (**89.4s**) · `saudi_news_sync` (**75.6s**) | مكتمل |
| **`metals_close`** (المعادن العالمية فقط) | **12.8s** (`0.21m`) | `gcc_metals_sync` (**12.8s** لرمزين `XAUUSD`, `XAGUSD`) | مكتمل |

---

## 2. القرار الهندسي: Operations Research ونسخة البايثون

### أ) هل نحتاج Operations Research (OR) في التشغيل اليومي؟
- **لا نحتاج مكتبات OR ثقيلة** (`ortools`, `pulp`, `scipy.optimize`) لجدولة خطوات التشغيل اليومي لأن عدد المراحل محدود (~10–25 مرحلة)، وإضافتها لا يحل عنق الزجاجة الحقيقي.
- **نعم نحتاج مفاهيم OR الخفيفة (DAG Scheduling + Critical Path + Bounded Concurrency)**:
  - **سبب البطء الحالي:** الخطوات الثقيلة في `saudi_close` و`saudi_midday` و`daily_bot` تعمل **بالتسلسل (Sequential)** رغم أن جزءاً كبيراً منها ينتظر I/O (شبكة Supabase / RSS / Yahoo / TradingView) ولا يستهلك الـ CPU لحظياً.
  - **ملاحظة الموارد:** سيرفر Hugging Face يعمل على **`2 vCPU`** (`OMP_NUM_THREADS=1` في [Dockerfile](../Dockerfile)), لذا التوازي الصحيح هو **توازي I/O محدود (`max_workers=3..4`)** مع فصل المهام الثقيلة CPU (`ml_scores_update`, `saudi_systems_backtests`) بحيث لا تتزاحم على المعالج في وقت واحد.
- **المكان الصحيح لـ OR الرياضي:** تحسين المحفظة (`Portfolio Optimization`) وتوزيع الأوزان للمستخدمين، وليس جدولة الـ cron.

### ب) هل نحدّث نسخة البايثون؟
- **النسخة الحالية:** [Dockerfile](../Dockerfile) يستخدم `python:3.12-slim` (والبيئة المحلية `Python 3.12.10`).
- **القرار:** **الإبقاء على `Python 3.12` حالياً وعدم الترقية إلى `3.13` الآن**:
  - الحزم الأساسية في [requirements.txt](../requirements.txt) (`stable-baselines3==2.3.2`, `gymnasium==0.29.1`, `lightgbm==4.3.0`, `xgboost==2.1.3`, `supabase==2.5.3`) مستقرة ومختبرة على `3.12`.
  - معظم زمن التشغيل (~75–85%) ضائع في **طلبات الشبكة المتكررة والرفع التسلسلي والتكرار المنطقي** وليس في سرعة مفسر بايثون؛ لذا تحسين الخوارزمية سيوفر دقائق فعلية، بينما الترقية لـ `3.13` لن تضيف سوى فرق هامشي (~3–5% CPU) مع مخاطرة كسر الاعتماديات.

---

## 3. خطة التحسين الخوارزمي المرتبة بالأولوية (Benchmark Tracker)

> يتم تحديث أعمدة **الزمن بعد** و**النتيجة المقاسة** فقط بعد تشغيل فعلي لكل تعديل.

| الأولوية | التحسين المستهدف | الملفات المعنية | الزمن قبل (مقاس) | الهدف التقديري | الزمن بعد (مقاس) | الحالة |
|---|---|---|---:|---:|---:|---|
| **P0** | **تسريع `gcc_metals_sync` (Delta Upload + توازي Storage بـ 6 workers + تقليل upsert اليومي إلى 15 يوماً بدل 260)** | `api/gcc_metals_sync.py` | `428.7s` (close) / `399.8s` (midday) | تقليل زمن خطوة الخليج/المعادن عبر التوازي وتخطي الملفات غير المتغيرة | — | ✅ مطبق محلياً (بانتظار القياس الحي) |
| **P0** | **تحويل مسار `saudi_close` و`saudi_midday` إلى DAG متوازي (`ThreadPoolExecutor(max_workers=2)` لأخبار وإفصاحات السعودية والخليج والمعادن بالتوازي مع الحسابات)** | `api/saudi_daily_runner.py` | `1309.6s` إجمالي `saudi_close` | تقليص المسار الحرج (Critical Path) ليقترب من زمن الحساب فقط | — | ✅ مطبق محلياً (بانتظار القياس الحي) |
| **P1** | **إزالة التكرار المزدوج في `daily_bot` (`refresh_market_status` يعيد استخدام نتيجة `refresh_market_status_for_gate` الناجحة في نفس التشغيل)** | `api/daily_bot_run.py` | `78.8s` (`37.5s + 41.3s`) للتكرار | إزالة حساب مكرر بالكامل | — | ✅ مطبق محلياً (بانتظار القياس الحي) |
| **P1** | **تقليل زمن `ml_scores_update` (EGX) و`saudi_pipeline_bootstrap` / `saudi_systems_backtests` عبر مشاركة لقطة التاريخ في الذاكرة + Batch Upsert + Vectorization** | `api/daily_bot_run.py`, `scripts/saudi_pipeline_bootstrap.py`, `scripts/saudi_backtest_and_systems.py` | `191.3s` (EGX ML) · `283.7s + 329.1s` (Saudi) | تقليل قراءات Supabase المتكررة وعمليات الحلقات الصفية | — | ⏳ مقترح |
| **P2** | **تقييد `ml_scores_update` في `daily_midday` أو استخدام Fast Inference للرموز المتغيرة فقط** | `api/daily_bot_run.py` | `210.0s` (EGX midday) | تقليل زمن تشغيل منتصف الجلسة | — | ⏳ مقترح |

---

## 4. بروتوكول القياس قبل وبعد أي تعديل

1. قبل تعديل أي مرحلة، يُسجَّل زمن آخر تشغيل مكتمل من `daily_job_runs` (عبر `started_at`, `completed_at`, و`steps[].timestamp`).
2. يُنفَّذ تعديل **واحد أو حزمة مترابطة** مع اختبارات unit offline.
3. بعد النشر وتشغيل الجلسة التالية، تُسجَّل الأرقام الجديدة في جدول القسم (3) ويُقارن:
   - الزمن الكلي للتشغيل (`total_seconds`).
   - زمن المرحلة المعدّلة فقط.
   - استقرار الذاكرة وعدم حدوث `scheduler recovery` أو فقدان نبض (`heartbeat`).
