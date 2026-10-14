# التشغيل اليومي — المرجع الحالي لكل الإيجنتس

آخر مراجعة: 14 أكتوبر 2026، توقيت Africa/Cairo. المرجع يفرق بين الكود المحلي وسجل الإنتاج؛ لا يعتبر وجود تعديل على Git إثبات نشره على HF.

تحديث الإصلاح: [التحقق من حداثة الأسعار والاستكمال المحدود](reports/daily-price-freshness-fix-2026-10-14.md). وصف نقص timestamps أدناه هو حالة التشغيل السابق؛ الإصلاح الجديد يضيف وقت إعادة الكتابة وتحققًا فعليًا بعد الحفظ. لا يغير سجلات تشغيل اليوم التاريخية.

## الحالة الفعلية يوم 14 أكتوبر

| التشغيل | ID | البداية بالقاهرة | نهاية المسار الأساسي | الحالة المسجلة | الصحة الفعلية |
|---|---|---|---|---|---|
| الأول midday | 57390402-9628-45a8-bc46-254b4f1013fd | 12:15:11 | 14:58:19 | completed | جزئي: أسعار، أخبار، وأسعار توصيات حرجة |
| الثاني close | 35a3c73f-92f4-4413-8d33-5c01b8627b88 | 17:00:29 | 17:53:35 | completed | جزئي: أسعار وتقارير اجتماعية |

الثاني استغرق 53 دقيقة و6 ثوانٍ. استكمال الأسعار انتهى 17:59:53؛ استعاد 0/42. لا يوجد تشغيل running في سجلات اليوم المقروءة. completed تعني نهاية المسار، وليست نجاح جميع المراحل. اقرأ error وآخر نتائج steps الفعالة بعد الاستكمال.

### نتيجة مراحل التشغيل الثاني

| المرحلة | الحالة/المحاولة | النتيجة | الزمن المسجل |
|---|---|---|---|
| sync_inventory | skipped | Skipped - weekly scheduled refresh only | — |
| quarterly_fundamentals | skipped | Skipped - scheduled Sunday close only | 14.0 ثانية |
| sync_prices | failed | Synced 233/275 symbols | 491.2 ثانية |
| calculate_indicators | success | 275 success, 0 failed, 232 records | 17.9 ثانية |
| ml_scores_update | success | Successfully updated AI ML Scores in DB | 174.2 ثانية |
| news_sentiment | success | Processed news for 24 symbols | 1704.9 ثانية |
| corporate_actions | success | Stored/refreshed 69 corporate actions | 282.2 ثانية |
| precompute_heatmap | success | Saved 287 symbols | 4.9 ثانية |
| update_positions | success | Positions updated | 30.6 ثانية |
| evaluate_recommendations | success | {"total": 0, "evaluated": 0, "updated": 0, "closed": 0, "adjusted": 0, "unchanged": 0, "blocked": 0, "errors": 0, "blocked_symbols": []} | 0.3 ثانية |
| recommendation_telegram_retries | success | Retried 0 Telegram events | 0.3 ثانية |
| refresh_market_status_for_gate | success | Market status cache updated successfully (using FREE data providers) | 110.8 ثانية |
| generate_recommendations | skipped | Skipped - market regime rejects new BUYs (panic: broad_five_day_selloff, both_indices_below_sma50) | 0.4 ثانية |
| short_swings_daily | success | Short swings close: 0 entries, 0 exits, 1 updates; completed | 17.0 ثانية |
| historical_similarity | success | 245 symbols scanned | 61.6 ثانية |
| weekly_performance_report | skipped | Skipped - scheduled Sunday only | — |
| refresh_market_status | success | Market status cache updated successfully (using FREE data providers) | 125.8 ثانية |
| hf_history_rebase | skipped | Skipped - current archive is within rebase window | 0.2 ثانية |
| accumulation_scan | success | Saved 226 records (acc=10, dist=3) | 5.3 ثانية |
| critical_recommendation_prices | success | {} | 2548.3 ثانية |
| cache_revalidation | success | {"invalidated": ["daily-market-data", "daily-news-data", "daily-recommendations", "daily-symbols", "daily-short-swings"], "skipped": false, "status": 200} | 78.2 ثانية |
| daily_market_outlook | success | DeepSeek market outlook delivered to both Telegram channels | 15.4 ثانية |
| daily_social_reports | failed | stock: HTTP 503; market: HTTP 503 | 36.4 ثانية |
| sync_prices | failed / استكمال 1 | Recovered 0/42 prices | — |

مدة critical_recommendation_prices تشمل انتظار ضم المسار الموازي؛ لا تثبت أن جميعها وقت طلبات مزود. الأخبار وحدها استغرقت 28 دقيقة و25 ثانية في الثاني. في الأول الأخبار فشلت بعد 78 دقيقة و6 ثوانٍ، والإجراءات الرأسمالية انتهت بصفر بعد 70 دقيقة و8 ثوانٍ؛ سبب البطء الداخلي غير مثبت بهذه القراءة.

## أسعار جلسة اليوم: ما ثبت وما لم يثبت

- سجل الثاني: 233/275 مزامنة ناجحة، 42 فشلًا؛ الأول 221/275.
- قاعدة stock_prices بتاريخ 2026-10-14، exchange=EGX: 224 رمزًا، وليس 233.
- مزامنة history ناجحة لا تعني وحدها وجود شمعة جلسة اليوم. لا تعرض العداد كعدد أسعار الإغلاق النهائية.
- upsert في api/stock_ai.py لا يرسل updated_at للأسعار، ولا يوجد trigger تحديث على stock_prices في المخطط المقروء. لذلك توقيت الصف قد يبقى من midday رغم إعادة الكتابة في close؛ لا نستطيع تحديد آخر إعادة تحديث لكل سهم من هذا الحقل.
- EGSA وEITP وEOSB لها صفوف اليوم أُنشئت أثناء فترة الثاني (17:04 تقريبًا). هذا دليل وقت إنشاء، وليس إثبات أن هذه الثلاثة فقط أعيد تحديثها.
- أمثلة أسعار اليوم المحفوظة: COMI=122، SWDY=114، AFMC=134.30. لم نتحقق مستقلًا من المزود أنها الإغلاق النهائي.
- EPPK لا يملك صفًا بتاريخ اليوم؛ آخر صف 13 أكتوبر بسعر 9.78. فشل الأول في EITP/EPPK بسبب missing_current_session؛ EITP له صف اليوم لاحقًا.

### كل الرموز ذات صف سعر بتاريخ 14 أكتوبر (224)

AALR, ABUK, ACAMD, ACAP, ACGC, ACTF, ADCI, ADIB, ADPC, AFDI, AFMC, AIDC, AIH, AJWA, ALCN, ALEX, ALUM, AMER, AMES, AMIA, AMOC, APPC, APSW, ARAB, ARCC, AREH, ASCM, ASPI, ATLC, ATQA, AXPH, BINV, BIOC, BONY, BTFH, CAED, CANA, CCAP, CCRS, CEFM, CERA, CFGH, CICH, CIEB, CIRA, CLHO, CNFN, COMI, COPR, COSG, CPCI, CPME, CRST, CSAG, DAPH, DCRC, DGTZ, DOMT, DSCW, DTPP, EALR, EASB, EAST, EBSC, ECAP, EDFM, EEII, EFIC, EFID, EFIH, EGAL, EGAS, EGBE, EGCH, EGREF, EGSA, EGTS, EHDR, EITP, ELEC, ELKA, ELNA, ELSH, EMFD, ENGC, EOSB, EPCO, ETEL, ETRS, EXPA, FAIT, FAITA, FERC, FWRY, GBCO, GDWA, GGCC, GGRN, GIHD, GMCI, GOUR, GPIM, GRCA, GSSC, GTEX, GTHE, GTWL, HDBK, HELI, HRHO, ICFC, ICID, IDRE, IEEC, IFAP, INFI, IRAX, IRON, ISMA, ISMQ, ISPH, JUFO, KABO, KASABF, KORA, KRDI, KWIN, KZPC, LCSW, LUTS, MAAL, MASR, MBEG, MBSC, MCQE, MCRO, MENA, MEPA, MFPC, MFSC, MHOT, MICH, MILS, MIPH, MOED, MOIL, MOIN, MOSC, MPCI, MPCO, MPRC, MTIE, NAHO, NARE, NBKE, NCCW, NCGC, NEDA, NHPS, NINH, NIPH, OBRI, OCDI, OCPH, ODIN, OFH, OIH, OLFI, ORAS, ORHD, ORWE, PACH, PHAR, PHDC, PHGC, PHTV, POUL, PRCL, PRDC, PRMH, QNBE, RACC, RAKT, RAYA, RMDA, ROTO, RREI, RTVC, RUBX, SAUD, SCEM, SCFM, SCTS, SDTI, SEIG, SIPC, SKPC, SMFR, SNFC, SPIN, SPMD, SUGR, SVCE, SWDY, TALM, TANM, TAQA, TMGH, TORA, TRTO, TWSA, TYCN, UBEE, UEFM, UEGC, UNIP, UNIT, UTOP, VALU, VLMRA, WCDF, WKOL, ZEOT, ZMID

### قائمة EODHD دون سعر بتاريخ اليوم (52)

| الرمز | اسم المصدر | آخر تاريخ محفوظ بنفس الرمز |
|---|---|---|
| ACRO | Acrow Misr | لا يوجد |
| ADRI | Arab Development & Real Estate Investment | لا يوجد |
| AGIG | Arab Moltaka Investments Co | لا يوجد |
| AIND | Arabia Investments Holding | لا يوجد |
| AIVCB | Al Arafa Investment And Consulting in EGP | لا يوجد |
| ALRA | Atlas For Investment and Food Industries | لا يوجد |
| AMII | Arabian Metal Industries And Industrial Investments | لا يوجد |
| AMPI | Al Moasher for Programming and Information Dissemination | لا يوجد |
| ANFI | Alexandria National Company for Financial Investment | لا يوجد |
| AREHA | Egyptian Real Estate Group Bearer Shares | لا يوجد |
| ARVA | Arab Valves Company | لا يوجد |
| AUTO | GB Corp | لا يوجد |
| BCAP | B Investments Holding | لا يوجد |
| BIDI | El Badr Investment And Development BID | لا يوجد |
| BIGP | Barbary Investment Group ( BIG) | لا يوجد |
| CILB | City Lab | لا يوجد |
| CIRF | Cairo For Investment And Real Estate Development | لا يوجد |
| DEIN | Delta Insurance | 2026-10-07 |
| EDBM | The Egyptian Company for Construction Development-Lift Slab | لا يوجد |
| EKHOA | Egyptian Kuwaiti Holding-EGP | لا يوجد |
| ELWA | El Wadi For International and Investment Development | لا يوجد |
| EPPK | El Ahram Co. For Printing And Packing | 2026-10-13 |
| ESRS | Ezz Steel | لا يوجد |
| FCMD | Future Care for Medical Industries - FCMI | لا يوجد |
| FIRE | First Investment Company And Real Estate Development | لا يوجد |
| FNAR | Al Fanar Contracting Construction Trade Import And Export Co | لا يوجد |
| FTNS | Fitness Prime | لا يوجد |
| GPPL | Golden Pyramids Plaza | 2026-09-08 |
| HBCO | Heibco for commercial investments & real estate development | لا يوجد |
| IBCT | International Business Corporation For Trading and Agencies | لا يوجد |
| ICLE | International Company For Leasing (IncoLEASE) | 2026-09-08 |
| INEG | Integrated Engineering Group S.A.E | لا يوجد |
| MATD | Marsa Marsa Alam For Tourism Development | لا يوجد |
| MEDP | Medical Packaging Company | لا يوجد |
| MEGM | Middle East Glass Manufacturing | 2022-04-28 |
| MKIT | Misr Kuwait Investment & Trading Co. | لا يوجد |
| NAPR | National Printing | لا يوجد |
| NDRL | National Drilling | 2026-10-07 |
| ORMT | Orascom Investment Holding | لا يوجد |
| PIOH | Pioneers Holding | لا يوجد |
| QNBA | Qatar National Bank | لا يوجد |
| RKAZ | REKAZ Financial Holding | لا يوجد |
| SAIB | Societe Arabe Internationale De Banque S.A.E | 2026-09-15 |
| SEIGA | Saudi Egyptian Investment & Finance $ | لا يوجد |
| SIMO | Paper Middle East (Simo) | لا يوجد |
| SMPP | Modern Shorouk Printing & Packaging | 2026-10-12 |
| SPHT | El Shams Pyramids For Hotels& Touristic Projects | 2026-10-04 |
| SRWA | Sarwa Capital Holding | لا يوجد |
| UASG | United Arab Shipping | لا يوجد |
| UPMS | Union Pharmacist Company For Medical Services and Investment | لا يوجد |
| VERT | Vertika for Industry & Trade | لا يوجد |
| VLMR | Valmore Holding | لا يوجد |

لا يعني عدم وجود بيانات تحت رمز EODHD أن الشركة غير متداولة. توجد اختلافات رموز ظاهرة مثل AUTO مقابل GBCO وBCAP مقابل BINV، لكنها ليست تفويضًا للاستبدال الآلي؛ يلزم سجل هوية موثق بالـISIN/المزود.

## قائمة الأسهم: المصدر والحفظ والتحديث

- symbols_data/Egypt_all_symbols.json وEgypt_inventory_source.json موجودان؛ المصدر EODHD، EGX، delisted=0، count=276.
- fetched_at=2026-10-12T19:12:51.186869+03:00؛ نفس metadata محفوظة في market_cache بمفتاح egx_inventory_eodhd وبـ276 صفًا.
- computed_at للنسخة الدائمة: 12 أكتوبر 20:36:59 القاهرة؛ هذا وقت حفظ النسخة وليس وقت جلب القائمة.
- week_start=2026-10-11. التشغيلان اليوم تخطيا التحديث الأسبوعي؛ هذا متوقع. الموعد التالي الأحد 18 أكتوبر، close، إذا ظل الجدول مفعّلًا.
- refresh_egx_inventory في api/egx_inventory.py يطلب EODHD مرة للأسبوع؛ يرفض القوائم الفارغة/أقل من 100 والانكماش لأقل من70%؛ يحفظ snapshot الدائم قبل استبدال JSON ذريًا.
- HF filesystem مؤقت؛ restore_inventory يستعيد النسخة الدائمة الأحدث عند الحاجة، مع تهدئة قراءة ساعة. فشل الجلب يحافظ على آخر قائمة سليمة.
- العدد المستخدم اليوم 275 بعد فلتر النشاط، مقابل276 بالقائمة. لم يحدد سجل التشغيل اسم الرمز المستبعد؛ لا نخمنه. صفحة الموقع/heatmap أوسع (287) من universe المزود، فلا تخلط الأعداد.

## الجدولة والتشغيلان

المرجع api/daily_job_scheduler.py وapi/daily_bot_run.py. تعمل الخدمة على HF، والجدولة داخل العملية؛ ليست GitHub Actions.

الجدول الدائم daily_job_schedule: enabled=true، midday_run_time=12:15، run_time=17:00، active_days=[0,1,2,3,4] بترميز JS (الأحد إلى الخميس). daily_job_config.json يستخدم أيام Python [0,1,2,3,6]؛ التحويل مقصود. Africa/Cairo تشمل التوقيت الصيفي؛ اليوم فرقUTC+3، لا تثبّت الفرق طوال السنة.

| الترتيب المحلي الحالي | الأول midday | الثاني close |
|---|---|---|
| استعادة قائمة الأسهم ثم sync_inventory | استعادة سليمة؛ لا جلب أسبوعي | جلب أسبوعي الأحد فقط ثم mark_non_listed عند تحديث ناجح |
| quarterly_fundamentals | تخطي | الأحد close إذا أصبح التحديث مستحقًا بعد90 يومًا |
| sync_prices | أحدث شمعة جزئية حتى لو تاريخ اليوم موجود | إعادة جلب أحدث شمعة حتى لو midday كتب نفس التاريخ |
| critical_recommendation_prices | مسار موازي محدود للأسهم المفتوحة الناقصة | نفس الحماية، مع إعادة تقييم محددة عند إصلاح أسعار متأخرة |
| calculate_indicators | مؤشرات من history محفوظ | نفس المرحلة |
| refresh_market_status_for_gate + short_swings_daily | الكود المحلي الأحدث يقدمهما مباشرة بعد المؤشرات | short_swings_daily محليًا بعد المؤشرات |
| ml_scores_update | KING/EGX | KING/EGX |
| news_sentiment ثم corporate_actions | أخبار وإجراءات رأسمالية | نفس المراحل |
| precompute_heatmap | لقطة عامة مشتركة | لقطة عامة مشتركة |
| نهاية midday | ضم المسار الحرج، cache_revalidation، إنهاء | يستمر |
| update_positions | لا ينفذ | تحديث المراكز |
| evaluate_recommendations | لا ينفذ | تقييم المفتوحة؛ لا إغلاق مصطنع عند نقص السعر |
| recommendation_telegram_retries | لا ينفذ | إعادة الأحداث المرفوضة المؤكدة فقط بحسب سجل التسليم |
| refresh_market_status_for_gate ثم generate_recommendations | لا ينفذ | بوابة السوق قد تمنع BUY؛ التخطي المقبول لا يعتبر فشلًا |
| historical_similarity | لا ينفذ | مسح تشابه تاريخي |
| weekly_performance_report | لا ينفذ | الأحد فقط |
| refresh_market_status | لا ينفذ | تحديث ملخص السوق |
| hf_history_rebase | لا ينفذ | فحص rebase الشهري؛ لا نشر أرشيف ما دام غير مستحق |
| accumulation_scan | لا ينفذ | تجميع/توزيع، stock_scans_summary |
| ضم المسار الحرج ثم cache_revalidation | عند نهاية الأول | إبطال tags المتأثرة الناجحة فقط |
| daily_market_outlook | لا ينفذ | تحليل السوق وتسليم قناتي تليجرام |
| daily_social_reports | لا ينفذ | تقارير السهم والسوق والتجميع والمتابعة وصورها حسب بواباتها |

**اختلاف الإنتاج عن المحلي:** سجل اليوم وضع short_swings_daily في نهاية midday بعد الأخبار، وفي close بعد generate_recommendations، خلاف ترتيب الكود المحلي الأحدث أعلاه. لا تدّعِ أن تقديم المرحلة منشور؛ يلزم مطابقة SHA HF عند مهمة نشر منفصلة.

## حالات البيانات والتوصيات

- شمعة تاريخ اليوم أثناء الجلسة مؤقتة؛ التاريخ وحده لا يثبت الإغلاق النهائي.
- الدخول اللحظي يحتاج جلسة مفتوحة وسعرًا مرصودًا لنفس اليوم وحجمًا موجبًا وشروط الاستراتيجية/بوابة السوق؛ observed_at وقت اللقطة وليس ضمان وقت آخر صفقة.
- يحتفظ الدخول المنشور بسعره؛ لا يعاد تصويره كدخول افتتاحي، ولا تستخدم قمة/قاع سابقين للدخول لحساب خروج داخل اليوم.
- close يسمح بإشارات الغد وحسابات الإغلاق. midday لا ينشئ إشارات close من شمعة غير مكتملة.
- السعر الناقص يبقى ناقصًا؛ لا تستخدم entry_price كأنه current_price ولا تختلق عائد0%.
- zero-volume quote قد يكون سعرًا غير متداول صالحًا للعرض؛ لا يعتبر جلسة تنفيذ صالحة.
- min price coverage الافتراضي80% يسمح بعمل الأجزاء ذات بيانات قابلة للاستخدام، مع استمرار تسجيل الرموز الفاشلة. لا يعطي ترخيصًا لتداول سهم ناقص.

## الانقطاع والاستكمال ومنع التكرار

1. كل phase لها daily_job_runs ID مستقل. running/heartbeat حديث يمنع محاولة متزامنة.
2. startup catch-up يستأنف المرحلة المستحقة؛ midday الفائت لا يعاد بعد14:30. المحاولات الكاملة محدودة3 مع15 دقيقة تهدئة.
3. daily_continuation يعيد نفس ID واليوم والphase للمسار المقطوع؛ لا يعيد مراحل نجاح سابقة. لا تمسح سجل الفشل.
4. daily_stage_recovery يسمح بمحاولة فعلية واحدة للمرحلة الفاشلة، عبر checkpoint/CAS. نقص prerequisite المحجوب لا يستهلك محاولة تنفيذ؛ إصلاح أسعار غير قابلة للاستخدام يقتضي تحديث مشتقاتها.
5. short_swings_daily يستخدم snapshot/checkpoint خاصًا للphase/التاريخ ورسائل تسليم مستقلة. لا تعيد حساب/إرسال الأحداث المؤكدة. timeout أو غموض التسليم يحتاج مطابقة receipt؛ لا ترسل آليًا مرة ثانية.
6. daily_social_recovery يصلح الجزء الاجتماعي/الكاش المحدود، ولا يعيد التداول أو الإشعارات. تقرير ready لا يعاد توليده، والصورة الجاهزة يعاد استخدامها. الطلب الغامض لا يعاد لمجرد timeout.
7. daily_job_outcome.effective_daily_steps يحسب النتائج الفعالة مع المحافظة على التاريخ. لا تستبدل233/275 بـ0/42 كأن الأخير تغطية السوق الكاملة.
8. بعد terminal لا تكرر polling أو قراءة logs بلا فشل محدد؛ ابدأ بسجل المهمة وcheckpoint المحدد. لا تشغل دورة كاملة كاختبار.

## حدود المراجعة والمشكلات القائمة

هذه الجولة قراءة حالة وكتابة توثيق فقط؛ لا تشغيل daily، ولا إعادة تقارير/صور/إشعارات، ولا جلب EODHD جديد، ولا نشر HF. القائمة الحالية صالحة للأسبوع؛ لا داعي لطلب مزود مكرر للتحقق منها.

مشكلات مثبتة تحتاج مهمة إصلاح منفصلة: 42 فشل مزامنة متكرر؛ فرق233 نجاح history مقابل224 أسعار اليوم؛ غياب timestamp لآخر إعادة تحديث الأسعار؛ بطء RSS في الأول والثاني؛ HTTP503 لتقريري stock/market؛ اختلاف ترتيب short monitoring بين المحلي وسجل الإنتاج. السبب التفصيلي للـ503 ولمعظم42 رمزًا لم يحقق من logs، فلا ينسب إلى الموديل أو مزود بعينه.

## مراجع الملفات

- api/daily_bot_run.py: المسار الأساسي.
- api/daily_job_scheduler.py: الجدولة والحماية والاستكمال.
- api/daily_job_outcome.py: الصحة الفعلية وتفسير السجل.
- api/daily_stage_recovery.py، daily_continuation.py، daily_recovery_state.py: الإصلاح وCAS.
- api/egx_inventory.py: قائمة المزود وحفظها.
- api/smart_sync.py، price_sync_policy.py، stock_ai.py: الأسعار وحدود الطلبات والكتابة.
- api/short_swings_daily.py، short_swings_engine.py: القصير وسلامة الدخول/الخروج.
- api/daily_social_reports.py، daily_social_recovery.py: تقارير وصور.
- docs/reports/daily-continuation-and-inventory-2026-10-12.md وdocs/reports/daily-price-sync-speed-2026-10-12.md: تاريخ الإصلاحات.

عند تغيير المسار حدّث هذا المرجع وسجل Git/HF SHA وتاريخ النشر والأجزاء المتحققة فعليًا. أي تقرير جديد يجب أن يميز الحالة المسجلة completed والصحة الجزئية، وعددUniverse وعددالأسعار بتاريخ الجلسة.

