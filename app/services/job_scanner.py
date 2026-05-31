"""
Background job scanner.

Runs on a configurable interval (default: every 6 hours).
For each active user with a completed profile:
  1. Queries Adzuna for their target role + location
  2. Upserts new jobs into the DB
  3. Extracts required skills from job descriptions
  4. Scores the job against the user's profile
  5. Caches the fit score in job_fit_scores
"""
import asyncio
import re
import logging
from datetime import datetime, date
from typing import Dict, List, Optional

from sqlalchemy import select, not_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.user import User, UserProfile
from app.models.job import Job, JobFitScore, DismissedJob
from app.models.application import Application
from app.services.adzuna import adzuna_client
from app.services.fit_scorer import score_job_for_user
from app.services.cv_parser import ALL_SKILLS

# Skills too generic to add value in an Adzuna keyword query —
# they appear in almost every job description and narrow results to near-zero
# when combined with a role term.
_GENERIC_SEARCH_SKILLS = frozenset({
    "adaptability", "analytical", "benchmarking", "coaching", "collaboration",
    "communication", "compliance", "creativity", "critical thinking",
    "forecasting", "initiative", "kpi", "leadership", "management",
    "mentoring", "metrics", "operations", "organisation", "presentation",
    "problem solving", "reporting", "research", "strategy",
    "team leadership", "time management", "training",
})
from app.services.application_engine import submit_application
from app.services.notifications import send_push
from app.services.email_service import send_application_digest, ApplicationDigestItem

logger = logging.getLogger(__name__)

# Fallback keywords derived from experience level when target_role is not set
_LEVEL_KEYWORDS: Dict[str, str] = {
    "junior": "junior developer software engineer",
    "mid":    "software engineer product designer",
    "senior": "senior software engineer senior designer",
    "lead":   "tech lead engineering manager",
    "head":   "head of engineering director of product",
}

# Map the craft onboarding answer → Adzuna search keyword
_CRAFT_KEYWORDS: Dict[str, str] = {
    "design":      "UX designer product designer",
    "engineering": "software engineer developer",
    "product":     "product manager",
    "data":        "data analyst data scientist",
    "marketing":   "marketing manager growth",
    "operations":  "operations manager",
}


def _extract_skills_from_description(description: str) -> list[str]:
    """Scan a job description for both tech and soft skills."""
    text_lower = description.lower()
    found: set[str] = set()
    for skill in ALL_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            found.add(skill)
    return sorted(found)


def _extract_experience_years(description: str) -> Optional[int]:
    patterns = [
        r"(\d+)\+?\s*years?\s+(?:of\s+)?experience",
        r"(\d+)\+?\s*yrs?\s+(?:of\s+)?experience",
        r"minimum\s+(\d+)\s*years?",
        r"at\s+least\s+(\d+)\s*years?",
    ]
    text_lower = description.lower()
    for pat in patterns:
        match = re.search(pat, text_lower)
        if match:
            return int(match.group(1))
    return None


def _infer_level(description: str) -> Optional[str]:
    text_lower = description.lower()
    if any(kw in text_lower for kw in ["senior", "sr.", "lead", "principal", "staff"]):
        return "senior"
    if any(kw in text_lower for kw in ["junior", "entry level", "graduate", "jr."]):
        return "junior"
    if any(kw in text_lower for kw in ["mid", "intermediate", "mid-level"]):
        return "mid"
    return None


def _derive_keywords(profile: UserProfile) -> str:
    """
    Derive Adzuna search keywords from profile data.

    Priority:
      1. target_role (explicitly set by the user during onboarding)
      2. Experience-level fallback (junior/mid/senior/lead buckets)
      3. Generic catch-all

    One searchable domain skill is appended to the base term.  We skip skills
    in _GENERIC_SEARCH_SKILLS because Adzuna AND-matches every term — adding
    generic words like "communication" or "analytical" produces near-zero
    results.  We also skip niche job titles (e.g. "settlements specialist")
    because they return only a handful of results nationally.

    Keeping the query to 2 terms maximises result volume while still being
    relevant to the user's actual background.
    """
    if profile.target_role:
        base = profile.target_role
    elif profile.experience_level:
        base = _LEVEL_KEYWORDS.get(profile.experience_level.lower(),
                                   "software engineer designer product manager")
    else:
        base = "software engineer designer product manager"

    # Add ONE searchable domain skill (skip generic ones that kill Adzuna results)
    if profile.skills:
        searchable = [s for s in profile.skills if s not in _GENERIC_SEARCH_SKILLS]
        if searchable:
            return f"{base} {searchable[0]}"

    return base


async def scan_jobs_for_user(db: AsyncSession, user: User) -> int:
    """Scan and score jobs for a single user. Returns count of new jobs found."""

    # ── Load profile explicitly ──────────────────────────────────────────────
    # async SQLAlchemy CANNOT lazy-load relationships; always query directly.
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile: Optional[UserProfile] = profile_result.scalar_one_or_none()

    if not profile or not profile.onboarding_complete:
        logger.info("Skipping user %s — no profile or onboarding incomplete", user.id)
        return 0

    keywords = _derive_keywords(profile)
    logger.info("Scanning jobs for user %s — keywords: %r", user.id, keywords)

    # Only restrict by location for users who explicitly want on-site roles.
    # Passing a city (e.g. "Swindon") for remote/any users collapses Adzuna
    # results to near-zero because most remote postings omit a city entirely.
    location_filter = (
        profile.location
        if profile.remote_preference not in ("remote", "any") and profile.location
        else None
    )

    try:
        raw = await adzuna_client.search_jobs(
            country=profile.country_code or "gb",
            keywords=keywords,
            location=location_filter,
            salary_min=profile.salary_min,
            results_per_page=50,
        )
    except Exception as exc:
        logger.error("Adzuna API error for user %s: %s", user.id, exc)
        return 0

    results = raw.get("results", [])
    new_count = 0

    for raw_job in results:
        parsed = adzuna_client.parse_job(raw_job)
        if not parsed.get("adzuna_id"):
            continue

        # Enrich with NLP extractions
        desc = parsed.get("description", "")
        parsed["required_skills"] = _extract_skills_from_description(desc)
        parsed["experience_years_min"] = _extract_experience_years(desc)
        parsed["experience_level"] = _infer_level(desc)

        # Parse posted_at to naive UTC datetime (DB column is TIMESTAMP WITHOUT TIME ZONE)
        posted_raw = parsed.pop("posted_at", None)
        if isinstance(posted_raw, str):
            try:
                dt = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
                parsed["posted_at"] = dt.replace(tzinfo=None)  # strip tz → naive UTC
            except ValueError:
                parsed["posted_at"] = None

        # Upsert job
        stmt = pg_insert(Job).values(**parsed)
        stmt = stmt.on_conflict_do_update(
            index_elements=["adzuna_id"],
            set_={
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                "salary_min": stmt.excluded.salary_min,
                "salary_max": stmt.excluded.salary_max,
                "required_skills": stmt.excluded.required_skills,
                "is_active": True,
                "fetched_at": datetime.utcnow(),
            },
        )
        stmt = stmt.returning(Job.id)
        result = await db.execute(stmt)
        job_id = result.scalar_one()

        # Fetch the full job object for scoring
        job_row = await db.get(Job, job_id)
        if not job_row:
            continue

        # Score the job against the user's profile
        fit = score_job_for_user(profile, job_row)

        # Upsert fit score
        fit_stmt = pg_insert(JobFitScore).values(
            user_id=user.id,
            job_id=job_id,
            overall=fit.overall,
            skills_score=fit.skills_score,
            experience_score=fit.experience_score,
            location_score=fit.location_score,
            salary_score=fit.salary_score,
            matched_skills=fit.matched_skills,
            missing_skills=fit.missing_skills,
            reason=fit.reason,
            scored_at=datetime.utcnow(),
        )
        fit_stmt = fit_stmt.on_conflict_do_update(
            index_elements=["user_id", "job_id"],
            set_={
                "overall": fit_stmt.excluded.overall,
                "skills_score": fit_stmt.excluded.skills_score,
                "experience_score": fit_stmt.excluded.experience_score,
                "location_score": fit_stmt.excluded.location_score,
                "salary_score": fit_stmt.excluded.salary_score,
                "matched_skills": fit_stmt.excluded.matched_skills,
                "missing_skills": fit_stmt.excluded.missing_skills,
                "reason": fit_stmt.excluded.reason,
                "scored_at": datetime.utcnow(),
            },
        )
        await db.execute(fit_stmt)
        new_count += 1

    await db.commit()
    logger.info("Scanned %d jobs for user %s", new_count, user.id)

    # ── Autopilot: submit top-3 jobs automatically ───────────────────────────
    if profile.autopilot_enabled:
        await _autopilot_apply(db, user, profile)
    elif new_count > 0 and profile.push_token:
        # Non-autopilot briefing notification
        match_count = min(new_count, 3)
        noun = "match" if match_count == 1 else "matches"
        await send_push(
            token=profile.push_token,
            title="Your Vett briefing is ready.",
            body=f"{match_count} strong {noun} today. Tap to review.",
            data={"screen": "Feed"},
        )

    return new_count


async def _autopilot_apply(db: AsyncSession, user: User, profile: UserProfile) -> None:
    """
    After a scan, automatically submit applications for the top-3 scored
    jobs that the user hasn't yet applied to or dismissed.
    Sends a push notification and email digest after recording results.
    """
    dismissed_sub = select(DismissedJob.job_id).where(DismissedJob.user_id == user.id)
    applied_sub   = select(Application.job_id).where(Application.user_id == user.id)

    stmt = (
        select(Job, JobFitScore)
        .join(JobFitScore, JobFitScore.job_id == Job.id)
        .where(JobFitScore.user_id == user.id)
        .where(Job.is_active == True)
        .where(JobFitScore.overall >= (profile.min_fit_score or 60))
        .where(not_(Job.id.in_(dismissed_sub)))
        .where(not_(Job.id.in_(applied_sub)))
        .order_by(JobFitScore.overall.desc())
        .limit(3)
    )
    rows = (await db.execute(stmt)).all()

    # Fire all HTTP submissions concurrently (DB stays sequential)
    results = await asyncio.gather(
        *[submit_application(job_url=job.redirect_url or "", user=user, profile=profile)
          for job, fit in rows],
        return_exceptions=True,
    )

    submitted_titles: list[str] = []
    digest_items: List[ApplicationDigestItem] = []

    for (job, fit), result in zip(rows, results):
        if isinstance(result, Exception):
            logger.error("Autopilot apply failed for job %s: %s", job.id, result)
            continue

        application = Application(
            user_id=user.id,
            job_id=job.id,
            status=result.status,
            fit_score_snapshot=fit.overall,
            platform=result.platform,
            timeline=[{
                "event": result.status,
                "timestamp": datetime.utcnow().isoformat(),
                "message": result.message,
                "source": "autopilot",
            }],
        )
        db.add(application)
        await db.flush()  # populate application.id before commit

        logger.info("Autopilot: %s → job %s (%s)", result.status, job.id, job.title)

        if result.status == "submitted":
            submitted_titles.append(job.title or "")

        if result.status in ("submitted", "manual_required", "applied"):
            digest_items.append(ApplicationDigestItem(
                job_title=job.title or "Role",
                company=job.company or "Company",
                status=result.status,
                job_url=job.redirect_url or "",
                application_id=str(application.id),
            ))

    await db.commit()

    # Push notification — only when ≥1 application was fully submitted
    if submitted_titles and profile.push_token:
        count = len(submitted_titles)
        noun = "job" if count == 1 else "jobs"
        await send_push(
            token=profile.push_token,
            title=f"Vett applied to {count} {noun} for you.",
            body="Tap to see where.",
            data={"screen": "Tracker"},
        )

    # Email digest — once per day, respects email_notifications preference
    if digest_items:
        await _maybe_send_digest(db, user, profile, digest_items)


async def _maybe_send_digest(
    db: AsyncSession,
    user: User,
    profile: UserProfile,
    digest_items: List[ApplicationDigestItem],
) -> None:
    """
    Send the application digest email at most once per calendar day.
    Skipped if the user has turned off email_notifications.
    """
    if not getattr(profile, "email_notifications", True):
        logger.debug("Email digest disabled for user %s", user.id)
        return

    today = date.today()
    last_sent = profile.last_digest_sent_at
    if last_sent and last_sent.date() == today:
        logger.debug("Digest already sent today for user %s", user.id)
        return

    sent = await send_application_digest(
        user_email=user.email,
        user_name=user.full_name,
        applications=digest_items,
        notification_time=profile.notification_time,
    )

    if sent:
        profile.last_digest_sent_at = datetime.utcnow()
        await db.commit()


async def build_digest_items_for_user(
    db: AsyncSession,
    user: User,
) -> List[ApplicationDigestItem]:
    """
    Query today's submitted/manual_required applications for a user and
    return them as ApplicationDigestItem objects.  Used by the test endpoint.
    """
    stmt = (
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user.id)
        .where(Application.status.in_(["submitted", "manual_required", "applied"]))
        .where(
            # Keep only applications from today (midnight UTC onwards)
            Application.applied_at >= datetime(date.today().year, date.today().month, date.today().day)
        )
        .order_by(Application.applied_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    items: List[ApplicationDigestItem] = []
    for application, job in rows:
        items.append(ApplicationDigestItem(
            job_title=job.title or "Role",
            company=job.company or "Company",
            status=application.status,
            job_url=job.redirect_url or "",
            application_id=str(application.id),
        ))
    return items


async def run_full_scan(db: AsyncSession) -> dict[str, int]:
    """Scan jobs for all active users with complete profiles."""
    result = await db.execute(
        select(User)
        .join(UserProfile, User.id == UserProfile.user_id)
        .where(User.is_active == True)
        .where(UserProfile.onboarding_complete == True)
    )
    users = result.scalars().all()

    totals: Dict[str, int] = {}
    for user in users:
        count = await scan_jobs_for_user(db, user)
        totals[str(user.id)] = count

    return totals
