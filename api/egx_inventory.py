"""Validated EODHD inventory, atomically replaced once per scheduled week."""
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def normalize_inventory(rows):
    if not isinstance(rows, list) or len(rows) < 100:
        raise ValueError('EODHD returned an empty/incomplete EGX inventory')
    unique = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid inventory row')
        code = str(row.get('Code') or row.get('Symbol') or '').strip().upper()
        if not code or not row.get('Name'):
            raise ValueError('Inventory row is missing its code/name')
        unique[code] = dict(Symbol=code,Name=row['Name'],Exchange='EGX',Country='Egypt',
                            Type=row.get('Type'),Currency=row.get('Currency'),Isin=row.get('Isin'),
                            InventorySource='EODHD')
    if len(unique) < 100:
        raise ValueError('Incomplete unique inventory')
    return [unique[s] for s in sorted(unique)]


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,suffix='.tmp',delete=False) as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2)
        name=handle.name
    try:
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.remove(name)


def refresh_egx_inventory(directory, *, trigger='manual', rows=None):
    directory=Path(directory).resolve()
    target=directory/'Egypt_all_symbols.json'
    metadata_path=directory/'Egypt_inventory_source.json'
    now=datetime.now(ZoneInfo('Africa/Cairo'))
    week=(now.date()-timedelta(days=(now.weekday()+1)%7)).isoformat()
    try:
        if trigger=='scheduled' and target.exists() and metadata_path.exists():
            metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
            if metadata.get('source')=='EODHD' and metadata.get('week_start')==week:
                previous=json.loads(target.read_text(encoding='utf-8'))
                return True,[r['Symbol'] for r in previous],'Skipped - EODHD inventory already refreshed this week'
        if rows is None:
            import requests
            token=os.getenv('EODHD_API_KEY') or os.getenv('EODHD_API_TOKEN')
            if not token:
                return False,[],'EODHD API key not configured; existing inventory retained'
            response=requests.get('https://eodhd.com/api/exchange-symbol-list/EGX',
                params={'api_token':token,'fmt':'json','delisted':0},timeout=30)
            if response.status_code!=200:
                return False,[],f'EODHD returned HTTP {response.status_code}; existing inventory retained'
            rows=response.json()
        normalized=normalize_inventory(rows)
        if target.exists():
            old=json.loads(target.read_text(encoding='utf-8'))
            if len(normalized)<len(old)*0.7:
                return False,[],'Unexpected inventory shrink; existing inventory retained for review'
        _atomic_json(target,normalized)
        _atomic_json(metadata_path,dict(source='EODHD',exchange='EGX',delisted=0,count=len(normalized),
                                      fetched_at=now.isoformat(),week_start=week))
        return True,[r['Symbol'] for r in normalized],f'Updated EODHD EGX inventory with {len(normalized)} symbols'
    except Exception as error:
        # Request exception strings may contain the API token; only report type.
        return False,[],f'Inventory refresh failed ({type(error).__name__}); existing inventory retained'
