import json
from types import SimpleNamespace
from unittest.mock import Mock
from api.egx_inventory import refresh_egx_inventory
from api.egx_inventory import restore_inventory


def rows():
    return [dict(Code=f'S{i}',Name=f'Company {i}',Type='Common Stock',Currency='EGP',Isin=f'ISIN{i}') for i in range(100)]


def test_inventory_preserves_real_names_and_weekly_refresh_is_once(tmp_path, monkeypatch):
    ok, symbols, _ = refresh_egx_inventory(tmp_path,rows=rows())
    assert ok and len(symbols)==100
    saved=json.loads((tmp_path/'Egypt_all_symbols.json').read_text(encoding='utf-8'))
    assert saved[0]['Name']=='Company 0' and saved[0]['InventorySource']=='EODHD'
    fetch=Mock(side_effect=AssertionError('Scheduled weekly update must reuse the successful snapshot'))
    monkeypatch.setattr('requests.get',fetch)
    assert refresh_egx_inventory(tmp_path,trigger='scheduled')[2].startswith('Skipped')
    fetch.assert_not_called()


def test_bad_inventory_does_not_replace_last_good_file(tmp_path):
    assert refresh_egx_inventory(tmp_path,rows=rows())[0]
    before=(tmp_path/'Egypt_all_symbols.json').read_bytes()
    assert not refresh_egx_inventory(tmp_path,rows=[])[0]
    assert (tmp_path/'Egypt_all_symbols.json').read_bytes()==before
    malformed=rows(); malformed[5].pop('Code')
    assert not refresh_egx_inventory(tmp_path,rows=malformed)[0]
    assert (tmp_path/'Egypt_all_symbols.json').read_bytes()==before


def test_provider_error_never_leaks_token_or_replaces_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv('EODHD_API_KEY','test-secret-value')
    fetch=Mock(side_effect=RuntimeError('failed URL ?api_token=test-secret-value'))
    monkeypatch.setattr('requests.get',fetch)
    result=refresh_egx_inventory(tmp_path)
    assert not result[0] and 'test-secret-value' not in result[2]
    assert not (tmp_path/'Egypt_all_symbols.json').exists()


def cache_client(snapshot=None, fail_write=False):
    store={'payload':snapshot}
    class Query:
        def select(self,fields): assert fields=='payload'; return self
        def eq(self,key,value): assert key=='cache_key'; return self
        def limit(self,n): assert n==1; return self
        def upsert(self,row):
            if fail_write: raise RuntimeError('Persistence unavailable')
            store['payload']=row['payload']; return self
        def execute(self): return SimpleNamespace(data=[{'payload':store['payload']}] if store['payload'] else [])
    return SimpleNamespace(table=lambda name:Query()),store


def test_weekly_snapshot_survives_ephemeral_rebuild_without_another_provider_call(tmp_path, monkeypatch):
    client,store=cache_client()
    first=tmp_path/'first'; rebuilt=tmp_path/'rebuilt'
    assert refresh_egx_inventory(first,rows=rows(),client=client)[0]
    assert store['payload']['metadata']['count']==100
    fetch=Mock(side_effect=AssertionError('Successful weekly snapshot must survive restart'))
    monkeypatch.setattr('requests.get',fetch)
    assert refresh_egx_inventory(rebuilt,trigger='scheduled',client=client)[2].startswith('Skipped')
    assert json.loads((rebuilt/'Egypt_all_symbols.json').read_text(encoding='utf-8'))[0]['InventorySource']=='EODHD'
    fetch.assert_not_called()


def test_failed_persistence_or_bad_stored_snapshot_retains_existing_json(tmp_path):
    assert refresh_egx_inventory(tmp_path,rows=rows())[0]
    before=(tmp_path/'Egypt_all_symbols.json').read_bytes()
    client,_=cache_client(fail_write=True)
    changed=rows(); changed[0]['Name']='Changed'
    assert not refresh_egx_inventory(tmp_path,rows=changed,client=client)[0]
    assert (tmp_path/'Egypt_all_symbols.json').read_bytes()==before
    bad,_=cache_client({'metadata':{'source':'EODHD','count':1},'rows':[]})
    assert not refresh_egx_inventory(tmp_path,rows=changed,client=bad)[0]
    assert (tmp_path/'Egypt_all_symbols.json').read_bytes()==before


def test_older_persisted_snapshot_does_not_overwrite_newer_local_inventory(tmp_path):
    client,store=cache_client()
    assert refresh_egx_inventory(tmp_path,rows=rows(),client=client)[0]
    store['payload']['metadata']['fetched_at']='2020-01-01T00:00:00+00:00'
    store['payload']['rows'][0]['Name']='Old name'
    restore_inventory(tmp_path,client,force=True)
    saved=json.loads((tmp_path/'Egypt_all_symbols.json').read_text(encoding='utf-8'))
    assert saved[0]['Name']=='Company 0'
