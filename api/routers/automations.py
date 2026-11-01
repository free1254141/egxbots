"""
api/routers/automations.py — FastAPI endpoints for Scheduled AI Chat Automations.

Provides endpoints for syncing in-memory worker cache from Vercel/Next.js
and executing on-demand test runs.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from api.scheduled_automations_worker import (
    sync_automations_cache,
    execute_single_automation,
    _supabase_request,
)

router = APIRouter(prefix="/automations", tags=["automations"])


class TestRunRequest(BaseModel):
    automation_id: str


@router.post("/sync")
def sync_automations():
    """Syncs the HF worker's in-memory active automations list immediately."""
    count = sync_automations_cache()
    return {"ok": True, "active_count": count}


@router.post("/test-run")
def test_run(req: TestRunRequest):
    """Executes a single automation immediately and delivers to user's Telegram."""
    rows = _supabase_request(f"scheduled_chat_automations?id=eq.{req.automation_id}&limit=1")
    if not rows or not isinstance(rows, list) or len(rows) == 0:
        raise HTTPException(status_code=404, detail="Automation not found")

    auto = rows[0]
    result = execute_single_automation(auto, is_test=True)
    return result


@router.get("/status")
def status():
    """Returns worker status and cache count."""
    count = sync_automations_cache()
    return {"ok": True, "worker_active": True, "cached_automations": count}
