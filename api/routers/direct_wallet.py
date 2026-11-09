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
    """Return public config for direct wallet payments."""
    return {
        "enabled": is_direct_wallet_enabled(),
        "recipient_wallet": DIRECT_WALLET_RECIPIENT_NUMBER,
        "supported_wallets": [
            {"id": "vodafone_cash", "name_ar": "فودافون كاش", "name_en": "Vodafone Cash"},
            {"id": "instapay", "name_ar": "انستاباي InstaPay", "name_en": "InstaPay"},
            {"id": "orange_cash", "name_ar": "أورنج كاش", "name_en": "Orange Cash"},
            {"id": "etisalat_cash", "name_ar": "اتصالات كاش", "name_en": "Etisalat Cash"},
            {"id": "we_pay", "name_ar": "وي باي WE Pay", "name_en": "WE Pay"},
            {"id": "smart_wallets", "name_ar": "المحافظ الذكية للبنوك", "name_en": "Smart Bank Wallets"},
        ],
    }


@router.post("/confirm")
def confirm_payment(req: DirectWalletConfirmRequest, authorization: str | None = Header(default=None)):
    """Confirm a direct e-wallet payment and auto-activate Pro instantly."""
    if not is_direct_wallet_enabled():
        raise HTTPException(status_code=403, detail="الدفع معطل حالياً")

    authenticated_user_id = _authenticated_user_id(authorization)
    if req.user_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="هوية المستخدم غير متطابقة")

    try:
        result = confirm_direct_wallet_payment(
            user_id=req.user_id,
            plan_id=req.plan_id,
            sender_mobile=req.sender_mobile,
            transaction_id=req.transaction_id,
            promo_code=req.promo_code,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        print(f"[DIRECT_WALLET_ROUTER] confirm_payment error: {exc}")
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء معالجة الدفع، يرجى المحاولة لاحقاً")
