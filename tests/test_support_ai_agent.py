import pytest
from unittest.mock import patch, MagicMock
from api.support_ai_agent import (
    tool_search_user,
    tool_get_user_subscription,
    tool_explain_founders_policy,
    tool_get_pending_payment_orders,
    execute_support_tool,
    process_support_message_with_deepseek,
    is_support_ai_enabled
)

def test_explain_founders_policy():
    policy = tool_explain_founders_policy()
    assert policy["grace_period_hours"] == 72
    assert "72" in policy["rule"]
    assert "50" in policy["tiers"]["tier_1_october"]
    assert "100" in policy["tiers"]["tier_2_current"]

def test_execute_support_tool_dispatch():
    # 1. explain_founders_policy
    res1 = execute_support_tool("explain_founders_policy", {})
    assert "72" in res1

    # 2. Unknown tool
    res2 = execute_support_tool("unknown_tool_xyz", {})
    assert "أداة غير معروفة" in res2

def test_is_support_ai_enabled():
    enabled = is_support_ai_enabled()
    assert isinstance(enabled, bool)

@patch("api.support_ai_agent._get_deepseek_key")
def test_deepseek_missing_key(mock_key):
    mock_key.return_value = ""
    reply = process_support_message_with_deepseek("sess_test", "مرحبا")
    assert reply is None
