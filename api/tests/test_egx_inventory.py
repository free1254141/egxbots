import json
from unittest.mock import Mock
from api.egx_inventory import refresh_egx_inventory


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
