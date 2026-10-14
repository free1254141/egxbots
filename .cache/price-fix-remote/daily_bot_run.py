--- 

+++ 

@@ -1309,2 +1309,5 @@

 
+_SENT_MARKET_BUY_HOLD_DATES: set[str] = set()
+
+
 def _send_market_buy_hold(gate: Dict[str, Any], market_date: str) -> bool:
@@ -1317,2 +1320,6 @@

 
+    if market_date in _SENT_MARKET_BUY_HOLD_DATES:
+        print(f"[MARKET_GATE] Buy-hold notice already delivered in memory for {market_date}; skipping duplicate.")
+        return True
+
     cache_key = "telegram_market_buy_hold_sent"
@@ -1321,2 +1328,3 @@

         print(f"[MARKET_GATE] Buy-hold notice already delivered for {market_date}; skipping duplicate.")
+        _SENT_MARKET_BUY_HOLD_DATES.add(market_date)
         return True
@@ -1348,2 +1356,3 @@

     if delivered:
+        _SENT_MARKET_BUY_HOLD_DATES.add(market_date)
         sent_dates = list(payload.get("sent_dates", []))
@@ -2429,3 +2438,4 @@

     from api.recommendation_policy import candidate_assessment
-    audit.update(model=resolved_model, candidates=[{**candidate_assessment(item), "council_score": item.get("council_score")} for item in results])
+    audit.update(model=resolved_model, candidates=[{**candidate_assessment(item), "council_score": item.get("council_score"),
+                                                 "entry_liquidity": item.get("entry_liquidity")} for item in results])
     if not results:
@@ -2619,2 +2629,3 @@

                     "execution": "published_close_reference_not_broker_fill",
+                    "entry_liquidity": res_item.get("entry_liquidity"),
                 },
@@ -2993,2 +3004,3 @@

     active_steps = {}
+    rss_stage_progress = {}
     symbols_raw = []
@@ -3001,2 +3013,3 @@

     daily_bulk_cache_ttl = 2 * 60 * 60
+    observed_quotes = None
     job_status = "running"
@@ -3062,2 +3075,12 @@

         _append_step_log(step_name, "started", details, 0)
+
+    def _rss_progress(stage_name, progress):
+        rss_stage_progress[stage_name] = progress
+        # Update the active ledger entry instead of appending hundreds of rows.
+        for entry in reversed(steps_log):
+            if entry.get('step') == stage_name and entry.get('status') == 'started':
+                entry.update(progress=progress, timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
+                             details=f"RSS {progress['processed']}/{progress['total']}; {progress['rss_succeeded']} valid feeds")
+                _persist_job('running')
+                break
 
@@ -3158,3 +3181,4 @@

         else:
-            _record_step("sync_inventory", True, "Skipped - weekly scheduled refresh only", 0)
+            if _stage_needed('sync_inventory'):
+                _record_step("sync_inventory", True, "Skipped - weekly scheduled refresh only", 0)
             print("\n>>> STEP 0: Skipping EGX inventory refresh today (weekly scheduled run only).")
@@ -3212,2 +3236,5 @@

                                                              on_progress=_price_progress)
+                    # The sync provider must positively verify quote observation
+                    # timestamps. Never turn a daily OHLC date into a live quote.
+                    observed_quotes = sync_result.get('observed_quotes')
                     # The writer has finished: discard stale scanner data before the
@@ -3226,3 +3253,4 @@

             print("\n>>> STEP 1: Skipping price sync (--skip-sync).")
-            _record_step("sync_prices", True, "Skipped", 0)
+            if _stage_needed('sync_prices'):
+                _record_step("sync_prices", True, "Skipped", 0)
 
@@ -3292,2 +3320,31 @@

 
+        # Protect/monitor short positions promptly after prices and indicators;
+        # heavy ML/news stages must not delay the trading lifecycle.
+        if phase == "midday" and _stage_needed('refresh_market_status_for_gate'):
+            _start_step("refresh_market_status_for_gate", "Refreshing intraday market status")
+            try:
+                ok_status, status_message = _refresh_market_status_cache()
+                _record_step("refresh_market_status_for_gate", ok_status, status_message, 0)
+            except Exception as error:
+                _record_step("refresh_market_status_for_gate", False, str(error)[:200], 0)
+        if _stage_needed('short_swings_daily'):
+            _start_step("short_swings_daily", "Monitoring short positions after the price/indicator stages")
+            try:
+                from api.short_swings_daily import run_daily_short_swings
+                from api.daily_job_outcome import effective_daily_steps
+                effective_steps = effective_daily_steps(steps_log)
+                prices_ok = any(step.get("status") == "success" for step in effective_steps
+                                if step.get("step") == "sync_prices")
+                indicators_ok = any(step.get("status") == "success" for step in effective_steps
+                                    if step.get("step") == "calculate_indicators")
+                swings_res = run_daily_short_swings(
+                    trigger=trigger, dry_run=dry_run, phase=phase, job_run_id=job_run_id,
+                    observed_quotes=observed_quotes,
+                ) if (phase == "close" or prices_ok or indicators_ok) else {
+                    "success": False, "message": "No usable price/indicator data; intraday short monitoring withheld"}
+                _record_step("short_swings_daily", swings_res.get("success", False),
+                             swings_res.get("message", ""), swings_res.get("count", 0))
+            except Exception as error:
+                _record_step("short_swings_daily", False, str(error)[:200], 0)
+
         # 2.2 Update AI Scores for all symbols in stock_technical_indicators
@@ -3304,52 +3361,4 @@

 
-        # 2.5 Fetch & Analyze News Sentiment
-        print("\n>>> STEP 2.5: Fetching and analyzing news sentiment...")
-        if _stage_needed('news_sentiment'):
-            _start_step("news_sentiment", "Fetching and analyzing news sentiment from Google News RSS")
-            try:
-                from api.news_sentiment_engine import process_exchange_news
-                if not symbols_raw:
-                    symbols_raw = _fetch_egx_symbols()
-                    symbols_raw = _filter_active_symbols(symbols_raw)
-            
-                # Fetch and process news sentiment for all active EGX symbols
-                ok, count = process_exchange_news("EGX", symbols_raw)
-                _record_step("news_sentiment", ok, f"Processed news for {count} symbols", count)
-            except Exception as e:
-                _record_step("news_sentiment", False, str(e)[:200], 0)
-                print(f"[NEWS_SENTIMENT] Error: {e}")
-
-        # 2.6 Corporate Actions Sweep (rights issues / splits / dividends / bonus
-        # shares) — targeted Google News RSS queries. Runs ONCE per day here;
-        # the chat pipeline never invokes this (it only reads the table and
-        # caches its own keyless web findings with origin = 'chat_cache').
-        print("\n>>> STEP 2.6: Fetching corporate actions (اكتتابات/توزيعات/تجزئة/منح)...")
-        if _stage_needed('corporate_actions'):
-            _start_step("corporate_actions", "Fetching and classifying corporate actions from Google News RSS")
-            try:
-                from api.corporate_actions_engine import process_exchange_corporate_actions
-                if not symbols_raw:
-                    symbols_raw = _fetch_egx_symbols()
-                    symbols_raw = _filter_active_symbols(symbols_raw)
-
-                ok_ca, ca_count = process_exchange_corporate_actions("EGX", symbols_raw, days_back=30)
-                _record_step("corporate_actions", ok_ca, f"Stored/refreshed {ca_count} corporate actions", ca_count)
-            except Exception as e:
-                _record_step("corporate_actions", False, str(e)[:200], 0)
-                print(f"[CORPORATE_ACTIONS] Error: {e}")
-
-        # 2.7 Pre-compute and save Sector Heatmap
-        print("\n>>> STEP 2.7: Pre-computing and saving Sector Heatmap...")
-        if _stage_needed('precompute_heatmap'):
-            _start_step("precompute_heatmap", "Pre-computing and saving Sector Heatmap to Supabase")
-            try:
-                ok_h, msg_h = update_market_heatmap()
-                _record_step("precompute_heatmap", ok_h, msg_h, 0)
-            except Exception as e:
-                _record_step("precompute_heatmap", False, str(e)[:200], 0)
-                print(f"[HEATMAP] Error pre-computing heatmap: {e}")
-
+        # Intraday monitoring must finish before optional external RSS sweeps.
         if phase == "midday":
-            # Only shared site data and short-position monitoring run intraday.
-            # Ordinary portfolio/recommendation lifecycle and LLM reports stay EOD.
             if _stage_needed('refresh_market_status_for_gate'):
@@ -3377,8 +3386,67 @@

                     _record_step("short_swings_daily", False, str(error)[:200], 0)
+
+        # 2.5 Fetch & Analyze News Sentiment
+        print("\n>>> STEP 2.5: Fetching and analyzing news sentiment...")
+        if _stage_needed('news_sentiment'):
+            _start_step("news_sentiment", "Fetching and analyzing news sentiment from Google News RSS")
+            try:
+                from api.news_sentiment_engine import process_exchange_news
+                if not symbols_raw:
+                    symbols_raw = _fetch_egx_symbols()
+                    symbols_raw = _filter_active_symbols(symbols_raw)
+            
+                # Fetch and process news sentiment for all active EGX symbols
+                ok, count = process_exchange_news("EGX", symbols_raw, progress_callback=lambda p: _rss_progress("news_sentiment", p))
+                _record_step("news_sentiment", ok, f"Processed news for {count} symbols; RSS: {json.dumps(rss_stage_progress.get('news_sentiment', {}))}", count)
+            except Exception as e:
+                _record_step("news_sentiment", False, str(e)[:200], 0)
+                print(f"[NEWS_SENTIMENT] Error: {e}")
+
+        # 2.6 Corporate Actions Sweep (rights issues / splits / dividends / bonus
+        # shares) — targeted Google News RSS queries. Runs ONCE per day here;
+        # the chat pipeline never invokes this (it only reads the table and
+        # caches its own keyless web findings with origin = 'chat_cache').
+        print("\n>>> STEP 2.6: Fetching corporate actions (اكتتابات/توزيعات/تجزئة/منح)...")
+        if _stage_needed('corporate_actions'):
+            _start_step("corporate_actions", "Fetching and classifying corporate actions from Google News RSS")
+            try:
+                from api.corporate_actions_engine import process_exchange_corporate_actions
+                if not symbols_raw:
+                    symbols_raw = _fetch_egx_symbols()
+                    symbols_raw = _filter_active_symbols(symbols_raw)
+
+                ok_ca, ca_count = process_exchange_corporate_actions("EGX", symbols_raw, days_back=30, progress_callback=lambda p: _rss_progress("corporate_actions", p))
+                _record_step("corporate_actions", ok_ca, f"Stored/refreshed {ca_count} corporate actions; RSS: {json.dumps(rss_stage_progress.get('corporate_actions', {}))}", ca_count)
+            except Exception as e:
+                _record_step("corporate_actions", False, str(e)[:200], 0)
+                print(f"[CORPORATE_ACTIONS] Error: {e}")
+
+        # 2.7 Pre-compute and save Sector Heatmap
+        print("\n>>> STEP 2.7: Pre-computing and saving Sector Heatmap...")
+        if _stage_needed('precompute_heatmap'):
+            _start_step("precompute_heatmap", "Pre-computing and saving Sector Heatmap to Supabase")
+            try:
+                ok_h, msg_h = update_market_heatmap()
+                _record_step("precompute_heatmap", ok_h, msg_h, 0)
+            except Exception as e:
+                _record_step("precompute_heatmap", False, str(e)[:200], 0)
+                print(f"[HEATMAP] Error pre-computing heatmap: {e}")
+
+        if phase == "midday":
+            # Only shared site data and short-position monitoring run intraday.
+            # Ordinary portfolio/recommendation lifecycle and LLM reports stay EOD.
             _finish_critical_prices()
-            from api.cache_invalidation import invalidate_daily_cache
-            invalidate_daily_cache(steps_log)
+            if _stage_needed('cache_revalidation'):
+                _start_step('cache_revalidation', 'Refresh successful intraday datasets')
+                try:
+                    from api.cache_invalidation import invalidate_daily_cache
+                    cache_result = invalidate_daily_cache(steps_log) or {}
+                    _record_step('cache_revalidation', not cache_result.get('error'),
+                                 ('Skipped - cache refresh not configured/eligible' if cache_result.get('skipped') else (json.dumps(cache_result) if cache_result else 'Done')), 0)
+                except Exception as cache_error:
+                    _record_step('cache_revalidation', False, str(cache_error)[:300])
             from api.price_sync_policy import price_sync_usable
+            from api.daily_job_outcome import effective_daily_steps
             essential_ok = all((price_sync_usable(step) if step.get("step") == "sync_prices" else step.get("status") == "success")
-                               for step in steps_log
+                               for step in effective_daily_steps(steps_log)
                                if step.get("step") in {"sync_prices", "calculate_indicators"} and step.get("status") != "started")
@@ -3470,14 +3538,2 @@

 
-        # 5.5 Run Short Swings Engine & Dispatch Telegram Alerts
-        print("\n>>> STEP 5.5: Running Short Swings engine & Telegram dispatch (الصفقات القصيرة)...")
-        if _stage_needed('short_swings_daily'):
-            _start_step("short_swings_daily", "Running short swings engine and sending VIP/Free telegram alerts")
-            try:
-                from api.short_swings_daily import run_daily_short_swings
-                swings_res = run_daily_short_swings(trigger=trigger, dry_run=dry_run, phase="close", job_run_id=job_run_id)
-                _record_step("short_swings_daily", swings_res.get("success", True), swings_res.get("message", "Done"), swings_res.get("count", 0))
-            except Exception as e_swings:
-                _record_step("short_swings_daily", False, str(e_swings)[:200], 0)
-                print(f"[SHORT_SWINGS] Error running daily short swings: {e_swings}")
-
         # 6. Run Historical Similarity Scan
@@ -3530,3 +3586,4 @@

         else:
-            _record_step("weekly_performance_report", True, "Skipped - scheduled Sunday only", 0)
+            if _stage_needed('weekly_performance_report'):
+                _record_step("weekly_performance_report", True, "Skipped - scheduled Sunday only", 0)
 
@@ -3620,5 +3677,5 @@

                 from api.cache_invalidation import invalidate_daily_cache
-                cache_result = invalidate_daily_cache(steps_log)
+                cache_result = invalidate_daily_cache(steps_log) or {}
                 _record_step('cache_revalidation', not cache_result.get('error'),
-                             ('Skipped - cache refresh not configured/eligible' if cache_result.get('skipped') else json.dumps(cache_result)), 0)
+                             ('Skipped - cache refresh not configured/eligible' if cache_result.get('skipped') else (json.dumps(cache_result) if cache_result else 'Done')), 0)
             except Exception as e_cache: