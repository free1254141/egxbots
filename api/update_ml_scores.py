from concurrent.futures import ThreadPoolExecutor
import os
import sys
from typing import Optional

project_root = os.path.abspath(os.path.dirname(__file__) + '/..')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))
load_dotenv(os.path.join(project_root, 'web', '.env.local'), override=True)

from api.stock_ai import _init_supabase, _get_thread_local_supabase
from api.routers.scan_ai_fast import fast_scan

def update_all_scores(bulk_cache_ttl_seconds: Optional[int] = None):
    print('[ML_SCORES] Starting update of raw AI scores via fast_scan pipeline (unfiltered)...')
    _init_supabase(force=True)
    
    print('[ML_SCORES] Running fast_scan for KING model across all stocks...')
    try:
        king_results = fast_scan(
            country='Egypt',
            limit=500,
            min_precision=0.0,
            buy_threshold=0.0,
            model_name='KING.bin',
            return_raw_prob=True,
            bulk_cache_ttl_seconds=bulk_cache_ttl_seconds,
        )
    except Exception as e:
        print(f"Error running KING scan: {e}")
        king_results = {}
        
    print('[ML_SCORES] Running fast_scan for EGX model across all stocks...')
    try:
        egx_results = fast_scan(
            country='Egypt',
            limit=500,
            min_precision=0.0,
            buy_threshold=0.0,
            model_name='model_EGX.bin',
            return_raw_prob=True,
            bulk_cache_ttl_seconds=bulk_cache_ttl_seconds,
        )
    except Exception as e:
        print(f"Error running EGX scan: {e}")
        egx_results = {}
        
    king_map = {r.get('symbol'): r for r in king_results.get('results', []) if isinstance(r, dict)}
    egx_map = {r.get('symbol'): r for r in egx_results.get('results', []) if isinstance(r, dict)}
    
    all_symbols = sorted(s for s in set(king_map.keys()).union(set(egx_map.keys())) if s)
    if not all_symbols:
        print('[ML_SCORES] No results found from fast_scan. Aborting DB update.')
        return
        
    print(f'[ML_SCORES] Updating raw ML scores for {len(all_symbols)} stocks in DB...')

    def _update_symbol_scores(sym: str) -> int:
        k_res = king_map.get(sym, {})
        e_res = egx_map.get(sym, {})
        k_score = k_res.get('precision')
        e_score = e_res.get('precision')
        if k_score is None and e_score is None:
            return 0
        try:
            update_payload = {}
            if k_score is not None:
                update_payload['king_ai_score'] = round(float(k_score), 4)
            if e_score is not None:
                update_payload['egx_ai_score'] = round(float(e_score), 4)
            sb = _get_thread_local_supabase()
            if sb is None:
                _init_supabase()
                sb = _get_thread_local_supabase()
            if sb is None:
                raise RuntimeError("Supabase client is not initialized")
            res = (
                sb.table('stock_technical_indicators')
                .update(update_payload)
                .eq('symbol', sym)
                .eq('exchange', 'EGX')
                .execute()
            )
            return len(res.data) if res.data else 0
        except Exception as e:
            print(f"Update error for {sym}: {e}")
            return 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        success_count = sum(executor.map(_update_symbol_scores, all_symbols))
            
    print(f'[ML_SCORES] Successfully updated raw ML scores for {success_count} stocks.')

if __name__ == '__main__':
    update_all_scores()
