--- 

+++ 

@@ -2078,3 +2078,9 @@

                     if int(volume_val) == 0:
-                        continue
+                        # EGX may publish a dated unchanged quote without any
+                        # trades (e.g. illiquid Nile stocks). Retain only a
+                        # finite, positive, flat daily bar; execution policies
+                        # still exclude zero-volume bars from trading sessions.
+                        from api.recommendation_freshness import is_nontrading_quote
+                        if is_intraday or sb_exchange.upper() != 'EGX' or not is_nontrading_quote(row):
+                            continue
                 except Exception: