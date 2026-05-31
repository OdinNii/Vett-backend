from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.schemas.user import (
    UserResponse,
    ProfileUpdate,
    ProfileResponse,
    AutopilotUpdate,
    AutopilotResponse,
    PushTokenUpdate,
    ScheduleUpdate,
    ScheduleResponse,
    CareerTreeResponse,
    EmailNotificationsUpdate,
    EmailNotificationsResponse,
)
from app.scheduler_utils import schedule_user_scan

router = APIRouter(prefix="/users", tags=["users"])


async def _get_or_create_profile(db: AsyncSession, user_id) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    return profile


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get("/me/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return ProfileResponse.model_validate(profile)


@router.patch("/me/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await _get_or_create_profile(db, current_user.id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await db.commit()
    return ProfileResponse.model_validate(profile)


@router.patch("/me/autopilot", response_model=AutopilotResponse)
async def update_autopilot(
    body: AutopilotUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutopilotResponse:
    """Enable or disable autopilot mode for the current user."""
    profile = await _get_or_create_profile(db, current_user.id)
    profile.autopilot_enabled = body.enabled
    await db.commit()
    return AutopilotResponse.model_validate(profile)


@router.post("/me/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    body: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Store the Expo push token for the current user."""
    profile = await _get_or_create_profile(db, current_user.id)
    profile.push_token = body.token
    await db.commit()


@router.patch("/me/schedule", response_model=ScheduleResponse)
async def update_schedule(
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    """
    Update the user's notification schedule and immediately reschedule their
    APScheduler job.

    time values: morning (7 am) | afternoon (1 pm) | evening (6 pm)
    frequency values: daily | paused
    timezone: IANA timezone string, e.g. "Europe/London"
    """
    profile = await _get_or_create_profile(db, current_user.id)

    if body.notification_time is not None:
        profile.notification_time = body.notification_time
    if body.notification_frequency is not None:
        profile.notification_frequency = body.notification_frequency
    if body.timezone is not None:
        profile.timezone = body.timezone

    await db.commit()

    # Reschedule immediately — changes take effect without a restart
    schedule_user_scan(
        user_id=str(current_user.id),
        notification_time=profile.notification_time,
        timezone=profile.timezone,
        frequency=profile.notification_frequency,
    )

    return ScheduleResponse.model_validate(profile)


@router.patch("/me/email-notifications", response_model=EmailNotificationsResponse)
async def update_email_notifications(
    body: EmailNotificationsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailNotificationsResponse:
    """Enable or disable the daily application digest email."""
    profile = await _get_or_create_profile(db, current_user.id)
    profile.email_notifications = body.enabled
    await db.commit()
    return EmailNotificationsResponse.model_validate(profile)


@router.get("/me/career-tree", response_model=CareerTreeResponse)
async def get_career_tree(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CareerTreeResponse:
    """Return personalised career tree rings based on the user's CV and profile."""
    from app.services.career_tree import build_career_tree

    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    return build_career_tree(profile)
