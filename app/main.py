"""
Vett API — FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.database import init_db, AsyncSessionLocal
from app.api import auth, users, jobs, applications, cv
from app.api import scheduler as scheduler_router
from app.api import test_email as test_email_router
from app.scheduler_state import scheduler
from app.scheduler_utils import schedule_user_scan

settings = get_settings()
logger = logging.getLogger(__name__)


async def _bootstrap_user_schedules() -> None:
    """
    At startup, register a per-user APScheduler cron job for every active user
    with a completed profile.  Uses each user's stored notification_time and
    timezone so scans fire at the right local hour.
    """
    from app.models.user import User, UserProfile

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserProfile)
            .join(UserProfile, User.id == UserProfile.user_id)
            .where(User.is_active == True)          # noqa: E712
            .where(UserProfile.onboarding_complete == True)  # noqa: E712
        )
        rows = result.all()

    scheduled = 0
    for user, profile in rows:
        schedule_user_scan(
            user_id=str(user.id),
            notification_time=profile.notification_time or "morning",
            timezone=profile.timezone or "UTC",
            frequency=profile.notification_frequency or "daily",
        )
        scheduled += 1

    logger.info("Bootstrapped %d per-user scan jobs", scheduled)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── Startup ───────────────────────────────────────────────────────────────
    await init_db()
    logger.info("Database initialised")

    scheduler.start()
    logger.info("Scheduler started")

    await _bootstrap_user_schedules()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Vett — Job matching platform API. Phase 1 MVP.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router,             prefix="/api/v1")
app.include_router(users.router,            prefix="/api/v1")
app.include_router(jobs.router,             prefix="/api/v1")
app.include_router(applications.router,     prefix="/api/v1")
app.include_router(cv.router,               prefix="/api/v1")
app.include_router(scheduler_router.router, prefix="/api/v1")
app.include_router(test_email_router.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
