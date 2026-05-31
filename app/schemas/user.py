import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    target_role: Optional[str] = None
    target_industries: Optional[List[str]] = None
    experience_years: Optional[int] = None
    experience_level: Optional[str] = None
    location: Optional[str] = None
    country_code: Optional[str] = None
    remote_preference: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    skills: Optional[List[str]] = None
    min_fit_score: Optional[int] = None
    onboarding_path: Optional[str] = None
    onboarding_complete: Optional[bool] = None
    interests: Optional[List[str]] = None
    values: Optional[List[str]] = None
    work_styles: Optional[List[str]] = None
    target_roles: Optional[List[str]] = None


class AutopilotUpdate(BaseModel):
    enabled: bool


class AutopilotResponse(BaseModel):
    autopilot_enabled: bool

    model_config = {"from_attributes": True}


class PushTokenUpdate(BaseModel):
    token: str


class ScheduleUpdate(BaseModel):
    notification_time: Optional[str] = None       # morning / afternoon / evening
    notification_frequency: Optional[str] = None  # daily / paused
    timezone: Optional[str] = None


class ScheduleResponse(BaseModel):
    notification_time: Optional[str]
    notification_frequency: str
    timezone: Optional[str]

    model_config = {"from_attributes": True}


class EmailNotificationsUpdate(BaseModel):
    enabled: bool


class EmailNotificationsResponse(BaseModel):
    email_notifications: bool

    model_config = {"from_attributes": True}


class ProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    onboarding_path: Optional[str]
    onboarding_complete: bool
    target_role: Optional[str]
    target_industries: list
    experience_years: Optional[int]
    experience_level: Optional[str]
    location: Optional[str]
    country_code: Optional[str]
    remote_preference: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: str
    skills: list
    cv_filename: Optional[str]
    cv_parsed_at: Optional[datetime]
    min_fit_score: int
    autopilot_enabled: bool
    notification_time: Optional[str]
    notification_frequency: str
    timezone: Optional[str]
    target_roles: list
    interests: list
    values: list
    work_styles: list
    email_notifications: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class CareerTreeNode(BaseModel):
    title: str
    ring: str
    fit: int
    salary_range: str
    have_skills: List[str]
    gap_skills: List[str]
    angle: float
    r: float


class CareerTreeResponse(BaseModel):
    center_title: str
    direct: List[CareerTreeNode]
    adjacent: List[CareerTreeNode]
    stretch: List[CareerTreeNode]
    peripheral: List[CareerTreeNode]
