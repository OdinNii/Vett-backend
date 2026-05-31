import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), index=True)

    # Application state machine
    status: Mapped[str] = mapped_column(
        String(50),
        default="applied",
        # applied → viewed → interview_scheduled → offer_received → accepted / rejected / withdrawn
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Cover note generated for this application
    cover_note: Mapped[str] = mapped_column(Text, nullable=True)
    cover_note_shown: Mapped[bool] = mapped_column(default=False)

    # Platform the application was submitted through
    platform: Mapped[str] = mapped_column(String(100), nullable=True)  # direct/indeed/linkedin/ats

    # Fit score snapshot at time of application
    fit_score_snapshot: Mapped[int] = mapped_column(Integer, nullable=True)

    # Timeline events (interview dates, follow-ups, etc.)
    timeline: Mapped[list] = mapped_column(JSON, default=list)

    # Notes the user adds
    user_notes: Mapped[str] = mapped_column(Text, nullable=True)

    # Fallback pack for manual_required applications
    fallback_pack: Mapped[dict] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="applications")
    job: Mapped["Job"] = relationship("Job", back_populates="applications")
