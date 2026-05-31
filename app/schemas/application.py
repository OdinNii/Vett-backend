import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.job import JobCardResponse


class ApplyRequest(BaseModel):
    job_id: uuid.UUID


class ApplicationStatusUpdate(BaseModel):
    status: str
    user_notes: Optional[str] = None


class TimelineEvent(BaseModel):
    event: str
    timestamp: datetime
    notes: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    applied_at: datetime
    updated_at: datetime
    fit_score_snapshot: Optional[int]
    cover_note_shown: bool
    platform: Optional[str]
    user_notes: Optional[str]
    timeline: list
    job: Optional[JobCardResponse] = None

    model_config = {"from_attributes": True}


class CoverNoteResponse(BaseModel):
    application_id: uuid.UUID
    cover_note: str


class FallbackPackResponse(BaseModel):
    application_id: uuid.UUID
    cover_note: str
    key_points: List[str]
    job_url: str
    deadline: Optional[str] = None
