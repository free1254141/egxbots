# 🗄️ دليل النسخ الاحتياطي المحلي لقاعدة بيانات Supabase (Agent & Developer Reference)

هذا المستند موجه لأي **Agent مستقبلي** أو **مطور** يعمل على مشروع **StokScan AI** لفهم حالة النسخ الاحتياطي لقاعدة بيانات Supabase، ومكان حفظ الملفات، وكيفية تحديث النسخة أو استعادتها بأمان.

---

## ⚠️ 1. تنبيهات أمنية حرجة (يجب قراءتها قبل أي إجراء)

1. **مستودع GitHub الحالي عام (`Public`)**:
   - المستودع المرتبط بالمشروع (`https://github.com/free1254141/egxbots.git`) مضبوط حالياً على `"visibility": "public"`.
   - **يُمنع منعاً باتاً** رفع مجلد `backups/` أو أي ملف `.sql` أو `.sql.gz` أو `.dump` أو `.jsonl.gz` إلى GitHub.
   - تم تأمين ذلك في ملف [`.gitignore`](file:///c:/Users/MR__CODER__/Desktop/stokscan_AI/.gitignore) بإضافة `backups/`، `*.sql.gz`، و `*.dump`.
2. **حماية موارد Supabase (Strict Resource Guard)**:
   - لا تقم بتشغيل النسخ الاحتياطي الكامل (`--mode full`) داخل حلقات تكرارية أو مهام خلفية متقاربة لأن جدول `public.stock_prices` وحده يحتوي على أكثر من **111,000 صف**.
   - إذا كنت تحتاج فقط إلى أخذ نسخة سريعة قبل تعديل يخص المستخدمين أو الاشتراكات أو المحافظ، استخدم الوضع السريع (`--mode core`).

---

## 📂 2. هيكل ومكان النسخ الاحتياطية على الجهاز

يتم حفظ جميع النسخ الاحتياطية محلياً داخل المجلد:
`c:\Users\MR__CODER__\Desktop\stokscan_AI\backups\` (أو `backups/` في جذر المشروع).

### الملفات المرجعية الثابتة داخل `backups/`:
- [`backups/latest_backup.json`](file:///c:/Users/MR__CODER__/Desktop/stokscan_AI/backups/latest_backup.json): مؤشر سريع يوضح مسار أحدث نسخة احتياطية تم أخذها، تاريخها، عدد الجداول، إجمالي الصفوف، وحجم الملف وبصمة `SHA-256`.
- [`backups/latest_schema_snapshot.json`](file:///c:/Users/MR__CODER__/Desktop/stokscan_AI/backups/latest_schema_snapshot.json): نسخة مخزنة من تعريفات الـ Schema الكاملة (`DDL`) والـ Functions والـ Views والـ Triggers والـ RLS Policies الخاصة بمشروع Supabase (`gfcmaxbtscmizsakarvc` - PostgreSQL 17).

### محتويات كل مجلد نسخة احتياطية (`backups/supabase_full_YYYY-MM-DD_HHMMSS/`):
1. **`full_backup.sql`**:
   - ملف SQL قياسي متوافق تماماً مع `psql` / `pg_dump`.
   - يحتوي بالترتيب على:
     1. الـ `ENUMS` والـ `SEQUENCES`.
     2. هيكل جميع الجداول (`CREATE TABLE IF NOT EXISTS` + تفعيل `ROW LEVEL SECURITY`).
     3. بيانات حسابات المستخدمين (`auth.users` شاملة كلمات المرور المشفرة `encrypted_password` والـ metadata) وبيانات الهويات (`auth.identities`).
     4. بيانات جميع جداول `public` (57 جدولاً كاملاً بنظام `INSERT INTO ... ON CONFLICT DO NOTHING`).
     5. جميع القيود (`Constraints`، `Primary Keys`، `Foreign Keys`)، الفهارس (`150 Indexes`)، الدوال (`77 SQL Functions`)، العروض (`4 Views`)، المشغلات (`12 Triggers`)، وسياسات الحماية (`73 RLS Policies`).
2. **`full_backup.sql.gz`**:
   - نفس ملف `full_backup.sql` مضغوطاً بصيغة `GZIP` لتوفير المساحة (حوالي 10–15% من الحجم الأصلي).
3. **`tables/*.jsonl.gz`**:
   - كل جدول مفصول في ملف JSON Lines مضغوط خاص به (مثل `tables/public.profiles.jsonl.gz`، `tables/public.stock_prices.jsonl.gz`، `tables/auth.users.jsonl.gz`).
   - مفيد جداً إذا أراد أي Agent فحص أو استعادة جدول واحد فقط عبر Python بدون الحاجة لقراءة ملف الـ SQL الكامل.
4. **`backup_manifest.json`**:
   - تقرير تفصيلي بعدد الصفوف في كل جدول، المفتاح الأساسي المستخدم، زمن التحميل، وبصمة التحقق `SHA-256`.

---

## 🛠️ 3. كيفية تشغيل النسخ الاحتياطي (للـ Agents والمطورين)

تم بناء الأداة الرسمية في:
[`scripts/backup_supabase_local.py`](file:///c:/Users/MR__CODER__/Desktop/stokscan_AI/scripts/backup_supabase_local.py)

### أ) أخذ نسخة احتياطية كاملة (Full Backup - تشمل أسعار الأسهم التاريخية والفحوصات):
```powershell
.\venv\Scripts\python.exe scripts\backup_supabase_local.py --mode full
```

### ب) أخذ نسخة احتياطية سريعة للبيانات الحرجة فقط (Core Backup - بدون الجداول المليونية/التاريخية):
يشمل حسابات المستخدمين، المحافظ، الاشتراكات، المدفوعات، إعدادات البوت، ومحادثات الذكاء الاصطناعي (يستغرق بضع ثوانٍ فقط):
```powershell
.\venv\Scripts\python.exe scripts\backup_supabase_local.py --mode core
```

### ج) استخدام `pg_dump` الأصلي المباشر (اختياري):
إذا توفر binary أداة `pg_dump` على الجهاز وتمت إضافة `SUPABASE_DB_URL` (رابط اتصال Postgres المباشر بكلمة مرور قاعدة البيانات) داخل `.env`، فسيقوم السكريبت تلقائياً بتشغيل `pg_dump` الأصلي وحفظه في `native_pg_dump.sql` جنباً إلى جنب مع النسخة المهيكلة.

---

## 🔄 4. كيفية استعادة البيانات (Restore Guide)

### الحالة الأولى: استعادة قاعدة البيانات بالكامل إلى مشروع Supabase جديد أو محلي
باستخدام `psql`:
```powershell
psql "postgresql://postgres:<DB_PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres" -f backups\<BACKUP_FOLDER>\full_backup.sql
```

### الحالة الثانية: استعادة جدول واحد محدد فقط
بدلاً من تشغيل ملف الـ SQL الكامل، يمكنك قراءة ملف الجدول من `tables/public.<table_name>.jsonl.gz` عبر Python وإعادة رفعه بـ `upsert` عبر `SUPABASE_SERVICE_ROLE_KEY`:
```python
import gzip, json
from pathlib import Path

rows = [
    json.loads(line)
    for line in gzip.open("backups/<BACKUP_FOLDER>/tables/public.profiles.jsonl.gz", "rt", encoding="utf-8")
]
```

---

## 📊 5. ملخص بنية قاعدة البيانات (`gfcmaxbtscmizsakarvc`)

- **Region**: `eu-west-1`
- **PostgreSQL Engine**: `17.6.1.063`
- **Storage Buckets (4)**:
  - `ai-models` (Public)
  - `old-stock-data` (Private)
  - `chat-images` (Public)
  - `social-reports` (Public - PNG limit 5MB)
- **إجمالي الكائنات في `public`**:
  - `57` جدول (`Tables`)
  - `4` عروض (`Views`)
  - `77` دالة (`Functions`)
  - `73` سياسة أمان (`RLS Policies`)
  - `12` مشغل (`Triggers`)
  - `150` فهرس (`Indexes`)
