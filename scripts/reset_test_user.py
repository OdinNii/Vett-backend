#!/usr/bin/env python3
"""
Admin utility: delete a single test user so their email can re-register.

Dry run (default — no changes made):
    python scripts/reset_test_user.py --email user@example.com

Confirm deletion:
    python scripts/reset_test_user.py --email user@example.com --confirm

Must be run from the backend/ directory.
"""
import argparse
import asyncio
import os
import sys

# Add backend root to sys.path so app.* imports resolve
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND_ROOT)

# Load .env before app modules are imported — settings are cached on first use
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))

from sqlalchemy import select, func, delete as sa_delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.user import User, UserProfile  # noqa: E402
from app.models.application import Application  # noqa: E402
from app.models.job import SavedJob, DismissedJob, JobFitScore  # noqa: E402


async def run(email: str, confirm: bool) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            print(f"\nNo user found with email: {email}")
            print("Nothing to delete.\n")
            return

        # Count all linked records before touching anything
        app_count = (await session.execute(
            select(func.count()).select_from(Application).where(Application.user_id == user.id)
        )).scalar_one()

        saved_count = (await session.execute(
            select(func.count()).select_from(SavedJob).where(SavedJob.user_id == user.id)
        )).scalar_one()

        dismissed_count = (await session.execute(
            select(func.count()).select_from(DismissedJob).where(DismissedJob.user_id == user.id)
        )).scalar_one()

        fit_count = (await session.execute(
            select(func.count()).select_from(JobFitScore).where(JobFitScore.user_id == user.id)
        )).scalar_one()

        profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()

        # Always print what will be (or would be) deleted
        print()
        print("=" * 62)
        print("USER FOUND")
        print("=" * 62)
        print(f"  ID:                {user.id}")
        print(f"  Email:             {user.email}")
        print(f"  Full name:         {user.full_name or '(not set)'}")
        print(f"  Active:            {user.is_active}")
        print(f"  Created:           {user.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
        if profile:
            print(f"  Onboarding done:   {profile.onboarding_complete}")
            print(f"  CV file:           {profile.cv_filename or '(none)'}")
        else:
            print("  Profile:           (no profile row)")
        print()
        print("RECORDS THAT WILL BE DELETED:")
        print(f"  user_profiles:     {'1' if profile else '0'}   (via ORM cascade)")
        print(f"  applications:      {app_count}   (via ORM cascade)")
        print(f"  saved_jobs:        {saved_count}   (via ORM cascade)")
        print(f"  dismissed_jobs:    {dismissed_count}   (via ORM cascade)")
        print(f"  job_fit_scores:    {fit_count}   (explicit delete — no ORM cascade from User)")
        print()

        if not confirm:
            print("=" * 62)
            print("DRY RUN — no changes made.")
            print("Add --confirm to perform the deletion.")
            print("=" * 62)
            print()
            return

        # Delete job_fit_scores first — FK on user_id has no ON DELETE CASCADE,
        # so it would block the user row deletion if any rows exist.
        await session.execute(
            sa_delete(JobFitScore).where(JobFitScore.user_id == user.id)
        )

        # Delete user — ORM cascade="all, delete-orphan" handles:
        #   user_profiles, applications, saved_jobs, dismissed_jobs
        await session.delete(user)
        await session.commit()

        print("=" * 62)
        print(f"DELETED: {email}")
        print("The email address can now be used to register again.")
        print("=" * 62)
        print()

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Delete a single test user so their email can re-register. "
            "Default mode is a dry run — no changes are made without --confirm."
        )
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email address of the user to delete",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually perform the deletion (omit for a safe dry run)",
    )
    args = parser.parse_args()

    asyncio.run(run(args.email, args.confirm))


if __name__ == "__main__":
    main()
