# معمارية الشات بوت الوكيل المستقل على بايثون (Python Agentic Chatbot Engine)
> **تاريخ الاعتماد والتوثيق:** 10 نوفمبر 2026  
> **الحالة:** معتمدة رسمياً ودائماً للإنتاج (Official Permanent Production Architecture)  
> **المحرك الإنتاجي الدائم (Production Engine):** Hugging Face Space (`weeasdwee-ai-bot.hf.space/api/ai_chat`)  
> **المحرك المحلي (Local Development):** FastAPI on `http://127.0.0.1:8000/api/ai_chat`  
> **حالة مسار فيرسيل (Vercel Status):** ملغي تماماً (Zero Vercel CPU - مسار `web/src/app/api/ai-chat/route.ts` تحول إلى Lightweight Proxy فقط مع تفريغ المعالجة في `beforeFiles`)  
> **منهجية التوجيه:** Vercel/Next.js `beforeFiles` و `afterFiles` Rewrites الافتراضية دائماً إلى بايثون.

---

## 1. الدوافع والأهداف المعمارية (Architectural Motivation)

1. **القضاء على استهلاك Vercel Active CPU (Zero-Vercel-CPU Strategy):**
   - الشات بوت الوكيل يقوم باستدعاء أدوات متعددة بالتوازي، وقد يحتاج من دورة إلى ثلاث دورات (Multi-turn tool loop) لجمع البيانات وتنسيق الإجابة في بث لحظي (Streaming SSE).
   - تشغيل هذه الدورات الطويلة على دوال Vercel Serverless كان يستهلك دقائق من كوتة الـ Active CPU الثمينة (4 ساعات شهرياً في الحساب المجاني).
   - بنقل الشات بوت إلى خادم بايثون (محلياً أو على Hugging Face Space الدائم)، ينخفض استهلاك Vercel Active CPU إلى **0%**، حيث يقتصر دور فيرسيل على تمرير الـ Streaming فقط كـ Proxy شفاف.

2. **الانسجام التقني مع نماذج ومكتبات التحليل الفني (Python Native Ecosystem):**
   - مؤشرات المنصة، واستراتيجيات التجميع، ومكتبات التحليل المالي، وحسابات وايكوف مكتوبة بالفعل في بيئة Python.
   - تشغيل الشات بوت داخل نفس البيئة يتيح الوصول المباشر إلى الدوال الرياضية والتحليلية وخوارزميات الذكاء الاصطناعي دون الحاجة لتكرار برمجتها في TypeScript.

3. **الاعتمادية العالية وسياسة الـ Zero Downtime / Dual Engine:**
   - لم يتم حذف أو تغيير كود Vercel الأصلي في `web/src/lib/ai/` و `web/src/app/api/ai-chat/route.ts`.
   - كود Vercel يعمل كـ **Fallback دائم وتلقائي**؛ في حال تعطل سيرفر بايثون أو الحاجة لإجراء صيانة، يمكن إعادة التوجيه إلى Vercel بضغطة زر دون توقف الخدمة.

---

## 2. مخطط المعمارية والتدفق (System Architecture Flow)

```mermaid
flowchart TD
    User["👤 المستخدم (متصفح / موبايل)"] -->|طلب SSE /api/ai-chat| Next["⚡ Next.js Edge Gateway (Port 3000)"]
    
    Next -->|فحص CHATBOT_BACKEND| ConfigCheck{الوضع المختار؟}
    
    ConfigCheck -->|CHATBOT_BACKEND = local / hf| PythonEngine["🐍 Python Agentic Backend (FastAPI - Port 8000)"]
    ConfigCheck -->|CHATBOT_BACKEND = vercel أو تعذر البايثون| VercelFallback["▲ Vercel Edge Serverless Engine"]
    
    subgraph PythonEngineGraph ["منظومة بايثون الوكيلة (api/agentic_chat)"]
        PythonEngine --> AuthGuard["🛡️ auth_guard.py<br/>(JWT Verification + Quota Check + Anti-Injection)"]
        AuthGuard -->|فحص الرصيد والكوتة| SupabaseDB[("🗄️ Supabase PostgreSQL")]
        AuthGuard --> Pipeline["🧠 pipeline.py<br/>(Agentic Multi-Turn Loop)"]
        Pipeline -->|DeepSeek-V3 Function Calling| LLM["🤖 DeepSeek-V3 API<br/>(KV Prompt Cache)"]
        Pipeline --> Tools["⚙️ tools_execution.py<br/>(14 Financial & Technical Tools)"]
        Tools -->|استعلامات محددة Projections| SupabaseDB
        Pipeline -->|SSE Event Stream| Next
    end
    
    subgraph VercelFallbackGraph ["المنظومة الاحتياطية الأصيلة"]
        VercelFallback --> AgenticTS["web/src/lib/ai/agentic-pipeline.ts"]
        AgenticTS --> LLM
    end
```

---

## 3. تفاصيل مكونات المنظومة الجديدة (`api/agentic_chat/`)

| الملف | المسؤولية المعمارية والوظيفية |
| :--- | :--- |
| **`router.py`** | موجه مسارات FastAPI الرئيسية (`/api/ai_chat/stream`, `/sessions`, `/settings`, `/health`). يدير الـ SSE البث اللحظي، وحفظ الرسائل في الخلفية بدون حجب (`_persist_message_background`) داخل جدول `ai_chat_messages`. |
| **`auth_guard.py`** | - استخراج وتدقيق هوية المستخدم عبر Supabase JWT.<br/>- خصم رسائل الشات والتحقق من الكوتة اليومية عبر RPC `consume_chat_message` المعتمدة لمنع التلاعب وتطبيق باقات Free و Pro.<br/>- تطهير المدخلات (Input Sanitization) ومنع الـ Prompt Injection.<br/>- حماية عمليات المحفظة (`anti_injection_portfolio_check`). |
| **`pipeline.py`** | - المحرك الوكيل (Agentic Loop) الداعم لاستدعاء الأدوات حتى 3 جولات متتالية.<br/>- دعم الـ Prompt Caching بتثبيت التعليمات وتوقيت القاهرة في بادئة الرسائل.<br/>- بث التوكنز الفعلي الحقيقي (`{"type": "token"}`) دون تأخيرات مصطنعة.<br/>- إرسال أحداث الأدوات المستدعاة والجداول المنفذة. |
| **`tools_schema.py`** | تعريفات الـ 14 أداة المعيارية المتوافقة مع DeepSeek / OpenAI Function Calling مع توصيف دقيق باللغة العربية لشروط استدعاء كل أداة. |
| **`tools_execution.py`** | المنفذ الفعلي للأدوات (Dispatcher) مع التحويل غير المتزامن (`asyncio.to_thread`)، والالتزام الصارم بقواعد **Zero Log / DB Waste** وتحديد الحقول المستعلمة Projections بدقة. |
| **`prompts.py`** | برومبت النظام المعتمد (System Prompt)، وحوكمة الاستشارات المالية، وفرض الدقة الرقمية، وقواعد عرض الأسهم ومصادر البيانات. |

---

## 4. قائمة الأدوات الـ 14 المدعومة بالباك إند (Supported Tools)

1. **`get_stock`**: جلب السعر اللحظي، التغير اليومي، مؤشرات RSI و MACD، وحالة التوافق الشرعي، وسكورات King AI و EGX AI.
2. **`get_stock_levels`**: حساب مستويات الدعم والمقاومة (S1, S2, R1, R2)، ومنطقة الدخول المقترحة، والوقف (Stop Loss)، والمستهدفات (Targets).
3. **`get_market`**: نظرة عامة على مؤشر EGX30، مؤشر الشريعة EGX33، حجم وسيولة السوق، وقوائم الأسهم الرابحة والخاسرة والأنشط.
4. **`get_recommendations`**: استعراض التوصيات الفنية الحية المفتوحة (لحظية 15 دقيقة / سوينغ قصير / متوسط) مع دعم فلترة الأسهم المتوافقة مع الشريعة.
5. **`get_technical_scan`**: الماسح الفني لاكتشاف التباعدات الإيجابية والسلبية (Divergence) والاختراقات الفنية.
6. **`get_accumulation_stocks`**: رادار التجميع المؤسسي والسيولة الذكية بمنهجية وايكوف (Wyckoff).
7. **`get_news`**: آخر الأخبار والإفصاحات الرسمية للشركات المقيدة الصادرة في البورصة.
8. **`get_comparison`**: مقارنة تفصيلية متوازية بين شركتين أو أكثر بالبيانات الفنية والمالية.
9. **`get_fair_value`**: حساب القيمة العادلة، ومضاعفات الربحية (P/E)، ومكررات القيمة الدفترية، ومقارنتها بمتوسط القطاع.
10. **`get_sharia_cleanser`**: حاسبة التطهير الشرعي لحساب المبالغ الواجب إخراجها بدقة بناءً على نسب التطهير الرسمية وتوزيعات الكوبونات.
11. **`manage_portfolio`**: إدارة المحفظة الآمنة والمحصنة ضد الحقن (عرض المراكز، إضافة سهم، تعديل كمية/سعر، حذف، تصفية كاملة).
12. **`calculate_position`**: حساب الأرباح والخسائر ونسب العائد لمركز افتراضي لحظي دون حفظه في المحفظة.
13. **`enable_autonomous_recommendations`**: تفعيل وضع التوصيات الحرة المستقلة للذكاء الاصطناعي.
14. **`disable_autonomous_recommendations`**: إيقاف وضع التوصيات الحرة والعودة للوضع القياسي.

---

## 5. تكوين التوجيه في الواجهة (`web/next.config.js`)

تم إعداد التوجيه باستخدام مصفوفة `beforeFiles` في Next.js:

```javascript
// web/next.config.js
const chatbotBackend = (process.env.CHATBOT_BACKEND || "vercel").toLowerCase().trim();
const isPythonChatbot = chatbotBackend === "local" || chatbotBackend === "hf";

const pythonChatbotDestination = chatbotBackend === "local"
  ? "http://127.0.0.1:8000/api/ai_chat/:path*"
  : `${BACKEND_URL}/api/ai_chat/:path*`;

const pythonChatbotExact = chatbotBackend === "local"
  ? "http://127.0.0.1:8000/api/ai_chat"
  : `${BACKEND_URL}/api/ai_chat`;

const beforeFiles = isPythonChatbot
  ? [
      {
        source: '/api/ai-chat/:path*',
        destination: pythonChatbotDestination,
      },
      {
        source: '/api/ai-chat',
        destination: pythonChatbotExact,
      },
    ]
  : [];
```

---

## 6. التحصينات الدفاعية المضافة للفرونت إند

في ملف `web/src/components/chat/FormattedChatMessage.tsx`:
- تمت إضافة فحوصات أمان دفاعية متقدمة (`safeHeaders` و `safeRows`) لمعالجة تدفق الجداول أثناء الـ SSE Streaming.
- يمنع حدوث أخطاء الانهيار غير المعالجة (`TypeError: Cannot read properties of undefined (reading 'map')`) في حال وصول دفعة توكنز مجتزأة لجدول أثناء الصياغة.

---

## 7. بروتوكول التشغيل والتحقق (Verification & Health Protocol)

1. **فحص صحة الباك إند:**
   ```bash
   curl http://127.0.0.1:8000/api/ai_chat/health
   # النتيجة المتوقعة:
   # {"status":"healthy","service":"agentic_chat","engine":"deepseek-v3","mode":"async-streaming"}
   ```
2. **فحص الـ Streaming المباشر عبر البايثون:**
   ```bash
   python -c "import urllib.request, json; req = urllib.request.Request('http://127.0.0.1:8000/api/ai_chat/stream', data=json.dumps({'message':'سعر التجاري الدولي'}).encode('utf-8'), headers={'Content-Type':'application/json'}); res = urllib.request.urlopen(req); print(res.read(200).decode('utf-8'))"
   ```
3. **قواعد النشر الصارمة (Strict Deployment Guards):**
   - **قاعدة منع Git Push التلقائي:** لا يتم تنفيذ أي `git push` إلا بطلب صريح ومباشر من المستخدم.
   - **قاعدة Hugging Face Deployment:** عند رفع التحديثات إلى Hugging Face Space (`weeasdwee/AI_BOT`)، يتم رفع ملفات بايثون فقط (`api/`, `jobs/`, `scripts/`) ولا يتم رفع ملفات Next.js إطلاقاً.
