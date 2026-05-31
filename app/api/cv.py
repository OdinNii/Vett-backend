from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.services.cv_parser import parse_cv
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/cv", tags=["cv"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


class CVParseResponse(BaseModel):
    skills: List[str]
    experience_years: Optional[int]
    experience_level: str
    detected_name: Optional[str]
    detected_title: Optional[str]
    detected_location: Optional[str]
    skills_count: int


@router.post("/upload", response_model=CVParseResponse, status_code=status.HTTP_200_OK)
async def upload_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CVParseResponse:
    content = await file.read()
    max_bytes = settings.max_cv_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.max_cv_size_mb}MB",
        )

    filename = file.filename or "cv"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Use: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    try:
        parsed = parse_cv(content, filename)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse CV: {exc}",
        )

    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    profile.cv_raw_text  = parsed["raw_text"]
    profile.cv_filename  = filename
    profile.cv_parsed_at = datetime.utcnow()

    # Merge newly detected skills with any already stored
    existing_skills = set(profile.skills or [])
    new_skills      = set(parsed["skills"])
    profile.skills  = sorted(existing_skills | new_skills)

    # Update experience fields only if not already set by the user
    if not profile.experience_years and parsed.get("experience_years"):
        profile.experience_years = parsed["experience_years"]
    if not profile.experience_level and parsed.get("experience_level"):
        profile.experience_level = parsed["experience_level"]

    # Backfill location from CV header if the user hasn't set one
    if not profile.location and parsed.get("detected_location"):
        profile.location = parsed["detected_location"]

    await db.commit()

    return CVParseResponse(
        skills=parsed["skills"],
        experience_years=parsed["experience_years"],
        experience_level=parsed["experience_level"],
        detected_name=parsed["detected_name"],
        detected_title=parsed["detected_title"],
        detected_location=parsed["detected_location"],
        skills_count=len(parsed["skills"]),
    )
