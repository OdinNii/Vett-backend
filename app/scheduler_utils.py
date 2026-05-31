"""
Per-user APScheduler helpers.

Imported by app/main.py (startup scheduling) and app/api/users.py
(reschedule on PATCH /me/schedule), keeping both sides decoupled from each
other and from job_scanner.py to avoid circular imports.
"""
from __future__ import annotations

import logging
import uuid

from apscheduler.triggers.cron import CronTrigger

from app.scheduler_state import scheduler, record_scan
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Canonical time-slot → UTC hour mapping
# The CronTrigger timezone parameter handles local→UTC conversion, so these
# are the *local* hours we fire each scan at.
TIME_SLOTS: dict[str, int] = {
    "morning":   7,
    "afternoon": 13,
    "evening":   18,
}


async def _run_user_scan_job(user_id_str: str) -> None:
    """
    APScheduler async job function for a single user.

    Deferred imports inside the function body prevent circular imports at
    module-load time (job_scanner → application_engine → … → here).
    """
    from sqlalchemy import select
    from app.models.user import User
    from app.services.job_scanner import scan_jobs_for_user

    logger.info("Scheduled scan starting for user %s", user_id_str)
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(User).where(User.id == uuid.UUID(user_id_str))
            )
            user = result.scalar_one_or_none()
            if not user:
                logger.warning("Scheduled scan: user %s not found", user_id_str)
                return
            count = await scan_jobs_for_user(db, user)
            record_scan({user_id_str: count})
            logger.info("Scheduled scan done for user %s — %d jobs", user_id_str, count)
        except Exception:
            logger.exception("Scheduled scan failed for user %s", user_id_str)


def schedule_user_scan(
    user_id: str,
    notification_time: str | None,
    timezone: str | None,
    frequency: str | None,
) -> None:
    """
    Add or replace the per-user APScheduler cron job.

    Pass frequency="paused" to cancel any existing job without adding a new one.
    """
    job_id = f"user_scan_{user_id}"

    if frequency == "paused":
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("Unscheduled scan job for user %s (paused)", user_id)
        return

    hour = TIME_SLOTS.get(notification_time or "morning", 7)
    tz = timezone or "UTC"

    scheduler.add_job(
        _run_user_scan_job,
        trigger=CronTrigger(hour=hour, minute=0, timezone=tz),
        id=job_id,
        args=[user_id],
        replace_existing=True,
        misfire_grace_time=300,
    )
    job = scheduler.get_job(job_id)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else "unknown"
    logger.info(
        "Scheduled user scan %s at %02d:00 %s — next run: %s",
        user_id, hour, tz, next_run,
    )


def unschedule_user_scan(user_id: str) -> None:
    """Remove the per-user scan job entirely."""
    job_id = f"user_scan_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Removed scan job for user %s", user_id)
