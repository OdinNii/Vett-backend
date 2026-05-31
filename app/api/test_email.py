"""
Test endpoints — development / QA only.

POST /api/v1/test/send-digest
    Triggers the application digest email to the currently authenticated user
    using today's submitted applications. Bypasses the once-per-day guard so
    you can call it repeatedly during testing.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.services.email_service import send_application_digest
from app.services.job_scanner import build_digest_items_for_user

router = APIRouter(prefix="/test", tags=["test"])


@router.post("/send-digest", status_code=status.HTTP_200_OK)
async def test_send_digest(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Send the application digest email for the current user immediately.

    Uses today's submitted/manual_required applications. Bypasses the
    once-per-day guard so you can call it more than once during testing.

    Returns { "sent": true/false, "application_count": N }.
    """
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    digest_items = await build_digest_items_for_user(db, current_user)

    sent = await send_application_digest(
        user_email=current_user.email,
        user_name=current_user.full_name,
        applications=digest_items,
        notification_time=profile.notification_time,
    )

    return {
        "sent": sent,
        "application_count": len(digest_items),
        "email": current_user.email,
        "note": (
            "No SENDGRID_API_KEY configured — set it in .env to send real emails"
            if not sent and not digest_items
            else (
                "No applications submitted today — submit some first or check autopilot"
                if not digest_items
                else "Check your inbox"
            )
        ),
    }
