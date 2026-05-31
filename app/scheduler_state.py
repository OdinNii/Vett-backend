"""
Singleton APScheduler instance + in-process scan-state tracking.

Imported by app/main.py (to start the scheduler) and app/api/scheduler.py
(to expose status/trigger endpoints), keeping both sides decoupled from each
other and avoiding circular imports.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

_last_scan_at: Optional[datetime] = None
_last_scan_jobs: int = 0
_last_scan_users: int = 0


def record_scan(results: dict[str, int]) -> None:
    """Update in-process state after every scheduled or manual scan."""
    global _last_scan_at, _last_scan_jobs, _last_scan_users
    _last_scan_at = datetime.utcnow()
    _last_scan_jobs = sum(results.values())
    _last_scan_users = len(results)


def get_scheduler_state() -> dict:
    """Return current scheduler state for the /scheduler/status endpoint."""
    job = scheduler.get_job("job_scan")
    next_run: Optional[str] = (
        job.next_run_time.isoformat() if (job and job.next_run_time) else None
    )
    return {
        "last_scan_at": _last_scan_at.isoformat() if _last_scan_at else None,
        "last_scan_jobs": _last_scan_jobs,
        "last_scan_users": _last_scan_users,
        "next_scan_at": next_run,
        "scheduler_running": scheduler.running,
    }
