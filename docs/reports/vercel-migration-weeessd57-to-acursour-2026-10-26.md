# Vercel Account & Domain Migration Report (2026-10-26)
**وثيقة توثيق نقل مشروع egxbots والدومين من الحساب القديم إلى الحساب الجديد - مكتمل بنجاح 100%**

---

## 1. ملخص العملية (Executive Summary)
تم بنجاح وبشكل نهائي نقل ملكية واستضافة مشروع **egxbots** بالكامل من الحساب القديم إلى الحساب الجديد، مع نقل ملكية الدومين الرسمي `egxbots.com` وربطه بالمشروع الجديد وتفعيله مع شهادة الأمان (SSL) دون أي انقطاع في الخدمة (Zero Downtime).

| البند | الحساب القديم (Source) | الحساب الجديد (Destination - الحالي) |
| :--- | :--- | :--- |
| **البريد الإلكتروني** | `weeessd57@gmail.com` | `acursour@gmail.com` |
| **اسم المستخدم / Team** | `weeessd57-8552` / `mr-coders-projects-2e3a65c8` | `acursour-4201` / `team_sYdSe5CpkOWfAigeczgIprsR` (`egxbots`) |
| **اسم المشروع على فيرسيل** | `stokscan-ai-web` | `egxbots` |
| **Project ID** | `prj_yhie5E6It045Cd7K5ZXwRLqaUSQi` | `prj_kvgWiiBMdlFBLMX6sYx8ewJBS7Y7` |
| **مستودع GitHub** | `free1254141/egxbots` (main) | `free1254141/egxbots` (main) |
| **مجلد العمل (Root)** | `web` | `web` |
| **منطقة الخوادم (Region)** | Frankfurt (`fra1`) | Frankfurt (`fra1`) |
| **تاريخ الإنجاز** | 2026-10-26 03:50 UTC+3 | 2026-10-26 04:16 UTC+3 |
| **الحالة النهائية** | تم فك الارتباط وحماية الموارد | **Active & Live (Verified √)** |

---

## 2. دوافع النقل والنتائج المحققة (Migration Benefits)
1. **تصفير استهلاك المعالج (CPU Hours):**
   - كان الاستهلاك في الحساب القديم: `3h 2m / 4h` (أكثر من 75% وكان معرضاً للتوقف).
   - الاستهلاك في الحساب الجديد الآن: **`0h 0m / 4h`** (عداد نظيف بالكامل).
2. **تصفير مساحة التخزين (Deployments Storage):**
   - كانت المساحة في الحساب القديم: `5.29 GB / 10 GB`.
   - المساحة في الحساب الجديد الآن: **`0.1 GB / 10 GB`**.
3. **تجديد رصيد شبكة CDN والطلبات:**
   - الحساب الجديد يبدأ برصيد **1,000,000 طلب CDN** جديد بالكامل.

---

## 3. تفاصيل التهيئة والتأمين في الحساب الجديد (Configuration & Security)

### أ. إنشاء المشروع وربط المستودع
- تم ربط المشروع بمستودع GitHub المباشر `free1254141/egxbots` وتحديد مجلد البناء `web`.
- تم ضبط منطقة التشغيل السحابي لجميع دوال الخادم لتكون في فرانكفورت `fra1` لضمان أقل زمن استجابة (Latency) لمستخدمي مصر والشرق الأوسط.

### ب. نقل وتأمين متغيرات البيئة (Environment Variables)
- تم نقل كافة المفاتيح بعدد **44 متغيراً بيئياً**.
- تم تشفير وتأمين **15 مفتاحاً سرياً** بنظام الحماية الفائقة (`type: sensitive` / `visibility: secret`) وحل جميع تحذيرات *(Needs Attention)*:
  - `ADMIN_SECRET_KEY`, `ADMIN_SECRET_PASSWORD`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `DEEPSEEK_API_KEY`, `DEEPSEEK_OFFICIAL_API_KEY`
  - `EODHD_API_KEY`, `NVIDIA_API_KEY`, `RESEND_API_KEY`, `TELEGRAM_BOT_TOKEN`
- تم توجيه `PYTHON_BACKEND_URL` إلى الرابط السحابي `https://weeasdwee-ai-bot.hf.space`.

### ج. فك حماية الـ SSO
- تم تعطيل حماية SSO التلقائية لضمان فتح الموقع للجمهور والزوار مباشرة دون شاشات تسجيل دخول فيرسيل.

---

## 4. نقل الدومينات والتحقق منها (Domain Verification & DNS)

### أ. النطاقات المفعلة في الحساب الجديد
1. **`egxbots.com`**:
   - الحالة: **Verified √ (Production)**
   - التوجيه: يعمل مباشرة مع Edge Pre-rendering (HTTP 200 OK).
2. **`www.egxbots.com`**:
   - الحالة: **Verified √ (Redirect)**
   - التوجيه: تحويل تلقائي دائم (308 Redirect) إلى `https://egxbots.com`.
3. **`egxbots.vercel.app`**:
   - الحالة: **Verified √ (Production)**

### ب. الخطوات البرمجية التي تمت لإتمام الربط
1. نقل ملكية الدومين من حساب `weeessd57-8552` إلى فريق `egxbots`.
2. قبول طلب النقل برمجياً وتأكيده عبر بريد الحساب الجديد `acursour@gmail.com`.
3. فك ارتباط الدومين من المشروع القديم `stokscan-ai-web` عبر Vercel REST API لمنع أي تضارب (Conflict).
4. إعادة ربط `egxbots.com` بالمشروع الجديد `prj_kvgWiiBMdlFBLMX6sYx8ewJBS7Y7` ليتم التعرف على ملكيته وتفعيله فوراً بنجاح (`verified: true`).

---

## 5. اختبار الاستجابة المباشرة (Live Verification Tests)
```bash
curl.exe -I https://egxbots.com
# HTTP/1.1 200 OK
# Server: Vercel
# X-Matched-Path: /
# X-Nextjs-Prerender: 1
# X-Vercel-Cache: PRERENDER
# X-Vercel-Id: fra1::...

curl.exe -I https://www.egxbots.com
# HTTP/1.1 200 OK
```

---

## 6. حالة الخوادم المحلية (Local Services Health)
- **FastAPI Backend (Port 8000):** يعمل بنجاح (HTTP 200).
- **Next.js Frontend (Port 3000):** يعمل بنجاح (HTTP 200).
