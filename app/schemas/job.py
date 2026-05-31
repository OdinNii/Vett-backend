import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class FitScoreDetail(BaseModel):
    overall: int
    skills_score: int
    experience_score: int
    location_score: int
    salary_score: int
    matched_skills: List[str]
    missing_skills: List[str]
    reason: str

    model_config = {"from_attributes": True}


class JobCardResponse(BaseModel):
    """Compact job representation shown in the feed (card stack)."""
    id: uuid.UUID
    title: str
    company: Optional[str]
    location: Optional[str]
    is_remote: bool
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: str
    contract_type: Optional[str]
    category: Optional[str]
    description_short: Optional[str]
    redirect_url: Optional[str]
    posted_at: Optional[datetime]
    fit: Optional[FitScoreDetail]

    model_config = {"from_attributes": True}


class JobDetailResponse(JobCardResponse):
    """Full job detail view."""
    description: Optional[str]
    required_skills: List[str]
    experience_level: Optional[str]
    experience_years_min: Optional[int]

    model_config = {"from_attributes": True}


class JobFeedResponse(BaseModel):
    jobs: List[JobCardResponse]
    total: int
    page: int
    page_size: int
    scanned_at: Optional[datetime] = None


class SaveJobRequest(BaseModel):
    job_id: uuid.UUID


class DismissJobRequest(BaseModel):
    job_id: uuid.UUID
