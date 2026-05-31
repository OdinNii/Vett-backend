import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, JSON, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    saved_jobs: Mapped[list["SavedJob"]] = relationship("SavedJob", back_populates="user", cascade="all, delete-orphan")
    dismissed_jobs: Mapped[list["DismissedJob"]] = relationship("DismissedJob", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)

    # Path choice
    onboarding_path: Mapped[str] = mapped_column(String(20), nullable=True)  # "directed" | "explorer"
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    # Role preferences
    target_role: Mapped[str] = mapped_column(String(255), nullable=True)
    target_industries: Mapped[list] = mapped_column(JSON, default=list)
    experience_years: Mapped[int] = mapped_column(Integer, nullable=True)
    experience_level: Mapped[str] = mapped_column(String(50), nullable=True)  # junior/mid/senior/lead

    # Location
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(String(10), nullable=True, default="gb")
    remote_preference: Mapped[str] = mapped_column(String(20), nullable=True)  # remote/hybrid/onsite/any

    # Salary
    salary_min: Mapped[int] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), default="GBP")

    # Skills (extracted from CV + manual)
    skills: Mapped[list] = mapped_column(JSON, default=list)

    # CV data
    cv_raw_text: Mapped[str] = mapped_column(Text, nullable=True)
    cv_filename: Mapped[str] = mapped_column(String(255), nullable=True)
    cv_parsed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Fit score threshold — hide jobs below this
    min_fit_score: Mapped[int] = mapped_column(Integer, default=60)

    # Autopilot — Vett submits applications automatically after scanning
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Push notifications — Expo push token registered by the mobile client
    push_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Explorer path extras
    interests: Mapped[list] = mapped_column(JSON, default=list)
    values: Mapped[list] = mapped_column(JSON, default=list)
    work_styles: Mapped[list] = mapped_column(JSON, default=list)

    # Notification schedule
    notification_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="morning")
    notification_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    timezone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="UTC")

    # Target roles saved from Career Tree
    target_roles: Mapped[list] = mapped_column(JSON, default=list)

    # Email digest notifications (daily summary after autopilot applies)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    # Tracks when the last digest was sent — used to enforce one-per-day
    last_digest_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="profile")
