import pytest
from api.stock_aliases import resolve_stock_symbol, extract_all_stock_symbols
from api.native_telegram_vip_chat import handle_native_vip_chat

def test_stock_aliases_arabic_resolution():
    assert resolve_stock_symbol("حلل سهم طلعت مصطفى") == "TMGH"
    assert resolve_stock_symbol("سهم فوري") == "FWRY"
    assert resolve_stock_symbol("السويدي اليكتريك") == "SWDY"
    assert resolve_stock_symbol("البنك التجاري الدولي") == "COMI"
    assert resolve_stock_symbol("حديد عز") == "ESRS"
    assert resolve_stock_symbol("بلتون القابضة") == "BTFH"
    assert resolve_stock_symbol("مدينة مصر") == "MASR"

def test_stock_aliases_multi_symbol_extraction():
    symbols = extract_all_stock_symbols("قارن بين طلعت مصطفى وفوري والسويدي")
    assert "TMGH" in symbols
    assert "FWRY" in symbols
    assert "SWDY" in symbols
    assert len(symbols) == 3

def test_native_vip_chat_check_quota():
    res = handle_native_vip_chat({
        "action": "check_quota",
        "telegram_user_id": 999999123,
        "telegram_username": "test_user",
    })
    assert res.get("ok") is True
    assert "remaining" in res
    assert "limit" in res

def test_native_vip_chat_set_pending_prompt():
    res = handle_native_vip_chat({
        "action": "set_pending_prompt",
        "telegram_user_id": 999999123,
        "telegram_username": "test_user",
        "prompt_mode": "stock",
    })
    assert res.get("ok") is True
    assert res.get("pending_prompt", {}).get("mode") == "stock"
