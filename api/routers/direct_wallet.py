"""FastAPI Router for Direct E-Wallet Payments."""
from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from api.direct_wallet_payments import (
    confirm_direct_wallet_payment,
    is_direct_wallet_enabled,
    DIRECT_WALLET_RECIPIENT_NUMBER,
)
from api import stock_ai
from api.stock_ai import _init_supabase

router = APIRouter(prefix="/payment/direct-wallet", tags=["direct-wallet"])


class DirectWalletConfirmRequest(BaseModel):
    user_id: str
    plan_id: str = "pro"
    sender_mobile: str
    transaction_id: str
    promo_code: str = ""


def _authenticated_user_id(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        _init_supabase()
        user_result = stock_ai.supabase.auth.get_user(token)
        user = getattr(user_result, "user", None)
        if user and getattr(user, "id", None):
            return str(user.id)
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/config")
def config():
    """Direct wallet transfers are retired; EasyKash is the sole approved gateway."""
    return {
        "enabled": False,
        "provider": "easykash",
        "supported_wallets": [],
    }


@router.post("/confirm")
def confirm_payment():
    """Direct wallet auto-activation is permanently retired; use EasyKash checkout."""
    raise HTTPException(
        status_code=410,
        detail="التحويل المباشر غير متاح؛ يتم الدفع والتفعيل الفوري عبر بوابة EasyKash المعتمدة فقط",
    )
