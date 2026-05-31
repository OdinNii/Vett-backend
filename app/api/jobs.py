import uuid
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, not_, exists
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.models.job import Job, JobFitScore, SavedJob, DismissedJob
from app.schemas.job import (
    JobFeedResponse,
    JobCardResponse,
    JobDetailResponse,
    FitScoreDetail,
    SaveJobRequest,
    DismissJobRequest,
)
from app.services.job_scanner import scan_jobs_for_user
from app.services.adzuna import adzuna_client

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Minimum threshold for users who have no CV / no skills yet
_NO_CV_THRESHOLD = 40


def _build_card(job: Job, fit: Optional[JobFitScore]) -> JobCardResponse:
    fit_detail = FitScoreDetail.model_validate(fit) if fit else None
    return JobCardResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        is_remote=job.is_remote,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        contract_type=job.contract_type,
        category=job.category,
        description_short=job.description_short,
        redirect_url=job.redirect_url,
        posted_at=job.posted_at,
        fit=fit_detail,
    )


_DAILY_FEED_LIMIT = 3


@router.get("/feed", response_model=JobFeedResponse)
async def get_feed(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobFeedResponse:
    # Fetch user profile for threshold
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    # If user has no CV (no skills), use a lower threshold so they see jobs
    has_skills = bool(profile and profile.skills)
    if profile:
        min_score = profile.min_fit_score if has_skills else min(profile.min_fit_score, _NO_CV_THRESHOLD)
    else:
        min_score = _NO_CV_THRESHOLD

    # IDs of dismissed jobs
    dismissed_sub = select(DismissedJob.job_id).where(DismissedJob.user_id == current_user.id)

    # Jobs scored for this user above threshold, excluding dismissed
    stmt = (
        select(Job, JobFitScore)
        .join(JobFitScore, and_(JobFitScore.job_id == Job.id, JobFitScore.user_id == current_user.id))
        .where(Job.is_active == True)
        .where(JobFitScore.overall >= min_score)
        .where(not_(Job.id.in_(dismissed_sub)))
        .order_by(JobFitScore.overall.desc(), Job.posted_at.desc())
        .limit(_DAILY_FEED_LIMIT)
    )
    result = await db.execute(stmt)
    rows = result.all()

    jobs = [_build_card(job, fit) for job, fit in rows]
    return JobFeedResponse(jobs=jobs, total=len(jobs), page=1, page_size=_DAILY_FEED_LIMIT)


@router.get("/adzuna-test")
async def adzuna_test(
    keywords: str = Query("software engineer"),
    country: str = Query("gb"),
) -> dict:
    """No-auth endpoint: call Adzuna directly and return raw results (dev/debug only)."""
    raw = await adzuna_client.search_jobs(
        country=country,
        keywords=keywords,
        results_per_page=5,
    )
    results = raw.get("results", [])
    return {
        "total_available": raw.get("count", 0),
        "returned": len(results),
        "jobs": [adzuna_client.parse_job(r) for r in results],
    }


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    fit_result = await db.execute(
        select(JobFitScore).where(
            JobFitScore.job_id == job_id,
            JobFitScore.user_id == current_user.id,
        )
    )
    fit = fit_result.scalar_one_or_none()

    fit_detail = FitScoreDetail.model_validate(fit) if fit else None
    return JobDetailResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        is_remote=job.is_remote,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        contract_type=job.contract_type,
        category=job.category,
        description_short=job.description_short,
        description=job.description,
        required_skills=job.required_skills or [],
        experience_level=job.experience_level,
        experience_years_min=job.experience_years_min,
        redirect_url=job.redirect_url,
        posted_at=job.posted_at,
        fit=fit_detail,
    )


@router.post("/save", status_code=status.HTTP_204_NO_CONTENT)
async def save_job(
    body: SaveJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    existing = await db.execute(
        select(SavedJob).where(
            SavedJob.user_id == current_user.id,
            SavedJob.job_id == body.job_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(SavedJob(user_id=current_user.id, job_id=body.job_id))
        await db.commit()


@router.delete("/save/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(SavedJob).where(
            SavedJob.user_id == current_user.id,
            SavedJob.job_id == job_id,
        )
    )
    saved = result.scalar_one_or_none()
    if saved:
        await db.delete(saved)
        await db.commit()


@router.get("/saved/list", response_model=List[JobCardResponse])
async def get_saved_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[JobCardResponse]:
    stmt = (
        select(Job, JobFitScore)
        .join(SavedJob, SavedJob.job_id == Job.id)
        .outerjoin(
            JobFitScore,
            and_(JobFitScore.job_id == Job.id, JobFitScore.user_id == current_user.id),
        )
        .where(SavedJob.user_id == current_user.id)
        .order_by(SavedJob.saved_at.desc())
    )
    result = await db.execute(stmt)
    return [_build_card(job, fit) for job, fit in result.all()]


@router.post("/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_job(
    body: DismissJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    existing = await db.execute(
        select(DismissedJob).where(
            DismissedJob.user_id == current_user.id,
            DismissedJob.job_id == body.job_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(DismissedJob(user_id=current_user.id, job_id=body.job_id))
        await db.commit()


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scan(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Manually trigger a job scan for the current user (async, fire-and-forget)."""
    background_tasks.add_task(scan_jobs_for_user, db, current_user)
    return {"status": "scan started"}


@router.post("/scan/run", response_model=dict)
async def trigger_scan_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Synchronously scan and score jobs for the current user. Returns count."""
    count = await scan_jobs_for_user(db, current_user)
    return {"status": "complete", "jobs_found": count}
