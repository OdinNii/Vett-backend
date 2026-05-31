import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.models.job import Job, JobFitScore
from app.models.application import Application
from app.schemas.application import (
    ApplyRequest,
    ApplicationStatusUpdate,
    ApplicationResponse,
    CoverNoteResponse,
    FallbackPackResponse,
)
from app.services.application_engine import (
    submit_application as _engine_submit,
    build_cover_note,
    build_fallback_pack,
)
from app.schemas.job import JobCardResponse, FitScoreDetail

router = APIRouter(prefix="/applications", tags=["applications"])

APPLICATION_STATUSES = {
    "applied", "submitted", "manual_required", "failed",
    "viewed", "interview_scheduled",
    "offer_received", "accepted", "rejected", "withdrawn",
}


def _build_job_card(job: Job, fit: Optional[JobFitScore]) -> JobCardResponse:
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
        fit=FitScoreDetail.model_validate(fit) if fit else None,
    )


def _build_app_response(
    application: Application,
    job: Optional[Job],
    fit: Optional[JobFitScore],
) -> ApplicationResponse:
    return ApplicationResponse(
        id=application.id,
        job_id=application.job_id,
        status=application.status,
        applied_at=application.applied_at,
        updated_at=application.updated_at,
        fit_score_snapshot=application.fit_score_snapshot,
        cover_note_shown=application.cover_note_shown,
        platform=application.platform,
        user_notes=application.user_notes,
        timeline=application.timeline,
        job=_build_job_card(job, fit) if job else None,
    )


@router.post("/submit", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def submit(
    body: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    """
    Submit a job application via the Vett engine.

    The engine visits the job page, detects the form, fills it with the user's
    profile data, and POSTs it. The application status reflects the outcome:
      submitted       — form successfully submitted
      manual_required — known ATS / JS page / no form; user should finish
      failed          — hard error during submission
    """
    existing = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.job_id == body.job_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied to this job")

    job = await db.get(Job, body.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    fit_result = await db.execute(
        select(JobFitScore).where(
            JobFitScore.job_id == body.job_id,
            JobFitScore.user_id == current_user.id,
        )
    )
    fit = fit_result.scalar_one_or_none()

    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    result = await _engine_submit(
        job_url=job.redirect_url or "",
        user=current_user,
        profile=profile,
    )

    cover_note = (
        build_cover_note(profile, current_user, job_title=job.title or "", company=job.company or "")
        if profile else ""
    )

    fallback_pack = None
    if result.status == "manual_required" and profile:
        fallback_pack = build_fallback_pack(
            profile,
            current_user,
            job_title=job.title or "",
            company=job.company or "",
            job_url=job.redirect_url or "",
            required_skills=job.required_skills or [],
        )

    application = Application(
        user_id=current_user.id,
        job_id=body.job_id,
        status=result.status,
        fit_score_snapshot=fit.overall if fit else None,
        cover_note=cover_note,
        platform=result.platform,
        fallback_pack=fallback_pack,
        timeline=[{
            "event": result.status,
            "timestamp": datetime.utcnow().isoformat(),
            "message": result.message,
        }],
    )
    db.add(application)
    await db.commit()

    return _build_app_response(application, job, fit)


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def apply(
    body: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    existing = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.job_id == body.job_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied to this job")

    job = await db.get(Job, body.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    fit_result = await db.execute(
        select(JobFitScore).where(
            JobFitScore.job_id == body.job_id,
            JobFitScore.user_id == current_user.id,
        )
    )
    fit = fit_result.scalar_one_or_none()

    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    cover_note = (
        build_cover_note(profile, current_user, job_title=job.title or "", company=job.company or "")
        if profile else ""
    )

    application = Application(
        user_id=current_user.id,
        job_id=body.job_id,
        status="applied",
        fit_score_snapshot=fit.overall if fit else None,
        cover_note=cover_note,
        platform="direct",
        timeline=[{"event": "applied", "timestamp": datetime.utcnow().isoformat()}],
    )
    db.add(application)
    await db.commit()

    return _build_app_response(application, job, fit)


@router.get("", response_model=List[ApplicationResponse])
async def list_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ApplicationResponse]:
    stmt = (
        select(Application, Job, JobFitScore)
        .join(Job, Application.job_id == Job.id)
        .outerjoin(
            JobFitScore,
            and_(JobFitScore.job_id == Job.id, JobFitScore.user_id == current_user.id),
        )
        .where(Application.user_id == current_user.id)
        .order_by(Application.applied_at.desc())
    )
    result = await db.execute(stmt)
    return [_build_app_response(app, job, fit) for app, job, fit in result.all()]


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: uuid.UUID,
    body: ApplicationStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    if body.status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {body.status}")

    timeline = list(application.timeline or [])
    timeline.append({"event": body.status, "timestamp": datetime.utcnow().isoformat()})
    application.timeline = timeline
    application.status = body.status
    if body.user_notes is not None:
        application.user_notes = body.user_notes

    await db.commit()

    job = await db.get(Job, application.job_id)
    fit_result = await db.execute(
        select(JobFitScore).where(
            JobFitScore.job_id == application.job_id,
            JobFitScore.user_id == current_user.id,
        )
    )
    fit = fit_result.scalar_one_or_none()

    return _build_app_response(application, job, fit)


@router.get("/{application_id}/cover-note", response_model=CoverNoteResponse)
async def get_cover_note(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoverNoteResponse:
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    application.cover_note_shown = True
    await db.commit()

    return CoverNoteResponse(
        application_id=application.id,
        cover_note=application.cover_note or "",
    )


@router.get("/{application_id}/fallback", response_model=FallbackPackResponse)
async def get_fallback_pack(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FallbackPackResponse:
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    if application.status != "manual_required" or not application.fallback_pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No fallback pack available for this application",
        )

    pack = application.fallback_pack
    return FallbackPackResponse(
        application_id=application.id,
        cover_note=pack.get("cover_note", ""),
        key_points=pack.get("key_points", []),
        job_url=pack.get("job_url", ""),
        deadline=pack.get("deadline"),
    )
