--- 

+++ 

@@ -36,2 +36,11 @@

 
+def is_nontrading_quote(row):
+    """Recognize a provider's flat, valid quote; never invent a session bar."""
+    try:
+        prices = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
+        return float(row.get('volume')) == 0 and all(isfinite(p) and p > 0 for p in prices) and len(set(prices)) == 1
+    except (TypeError, ValueError, KeyError):
+        return False
+
+
 def _current_quotes(client, symbols, session):
@@ -58,2 +67,4 @@

     funds = {r['symbol']: r.get('data') or {} for r in funds}
+    from api.trade_liquidity import candidate_liquidity
+    liquidity = candidate_liquidity(client, symbols, session) if symbols else {}
     accepted, rejected = [], []
@@ -69,3 +80,8 @@

             reason = 'not_in_current_eodhd_inventory'
-        (accepted if reason == 'verified' else rejected).append(row if reason == 'verified' else {'symbol': symbol, 'reason': reason})
+        if reason == 'verified' and not liquidity[symbol]['eligible']:
+            reason = 'liquidity_' + liquidity[symbol]['reason']
+        if reason == 'verified':
+            row = {**row, 'entry_liquidity': liquidity[symbol]}
+        (accepted if reason == 'verified' else rejected).append(row if reason == 'verified' else {
+            'symbol': symbol, 'reason': reason, 'entry_liquidity': liquidity.get(symbol)})
     return accepted, rejected