import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, Float, JSON, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    adzuna_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Core fields
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(String(10), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    description_short: Mapped[str] = mapped_column(String(500), nullable=True)

    # URLs
    redirect_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    company_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Salary
    salary_min: Mapped[float] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), default="GBP")

    # Classification
    category: Mapped[str] = mapped_column(String(255), nullable=True)
    contract_type: Mapped[str] = mapped_column(String(50), nullable=True)  # full_time/part_time/contract
    contract_time: Mapped[str] = mapped_column(String(50), nullable=True)  # permanent/temporary
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)

    # Skills extracted from description
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    experience_level: Mapped[str] = mapped_column(String(50), nullable=True)
    experience_years_min: Mapped[int] = mapped_column(Integer, nullable=True)

    # Metadata
    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    fit_scores: Mapped[list["JobFitScore"]] = relationship("JobFitScore", back_populates="job", cascade="all, delete-orphan")
    saved_by: Mapped[list["SavedJob"]] = relationship("SavedJob", back_populates="job", cascade="all, delete-orphan")
    dismissed_by: Mapped[list["DismissedJob"]] = relationship("DismissedJob", back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="job")


class JobFitScore(Base):
    """Per-user fit score cache for each job."""
    __tablename__ = "job_fit_scores"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), index=True)

    # Overall + dimension scores (0–100)
    overall: Mapped[int] = mapped_column(Integer)
    skills_score: Mapped[int] = mapped_column(Integer, default=0)
    experience_score: Mapped[int] = mapped_column(Integer, default=0)
    location_score: Mapped[int] = mapped_column(Integer, default=0)
    salary_score: Mapped[int] = mapped_column(Integer, default=0)

    # Matched / missing skills for transparency
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)

    # One-line "why" shown on the card
    reason: Mapped[str] = mapped_column(String(500), nullable=True)

    scored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship("Job", back_populates="fit_scores")


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), index=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="saved_jobs")
    job: Mapped["Job"] = relationship("Job", back_populates="saved_by")


class DismissedJob(Base):
    __tablename__ = "dismissed_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), index=True)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="dismissed_jobs")
    job: Mapped["Job"] = relationship("Job", back_populates="dismissed_by")
