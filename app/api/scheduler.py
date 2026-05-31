"""
Scheduler status and manual-trigger endpoints.

GET  /api/v1/scheduler/status  — last/next scan times (no auth required)
POST /api/v1/scheduler/trigger — kick off a full scan immediately (auth required)
"""
from datetime import datetime

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.database import AsyncSessionLocal
from app.models.user import User
from app.scheduler_state import get_scheduler_state, record_scan
from app.services.job_scanner import run_full_scan

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
async def scheduler_status() -> dict:
    """Return when the last scan ran and when the next one is scheduled."""
    return get_scheduler_state()


@router.post("/trigger")
async def trigger_scan(
    _current_user: User = Depends(get_current_user),
) -> dict:
    """
    Manually trigger a full scan across all active users with complete profiles.
    Useful for testing autopilot and the scheduler without waiting for 7 am.
    """
    async with AsyncSessionLocal() as db:
        results = await run_full_scan(db)
    record_scan(results)
    return {
        "triggered_at": datetime.utcnow().isoformat(),
        "users_scanned": len(results),
        "jobs_processed": sum(results.values()),
    }
