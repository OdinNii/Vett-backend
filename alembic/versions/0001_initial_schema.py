"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # user_profiles
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_path", sa.String(20), nullable=True),
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("target_role", sa.String(255), nullable=True),
        sa.Column("target_industries", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(10), nullable=True, server_default="'gb'"),
        sa.Column("remote_preference", sa.String(20), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(10), nullable=False, server_default="'GBP'"),
        sa.Column("skills", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("cv_raw_text", sa.Text(), nullable=True),
        sa.Column("cv_filename", sa.String(255), nullable=True),
        sa.Column("cv_parsed_at", sa.DateTime(), nullable=True),
        sa.Column("min_fit_score", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("interests", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("values", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("work_styles", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adzuna_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(10), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_short", sa.String(500), nullable=True),
        sa.Column("redirect_url", sa.String(1000), nullable=True),
        sa.Column("company_url", sa.String(500), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("salary_currency", sa.String(10), nullable=False, server_default="'GBP'"),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("contract_type", sa.String(50), nullable=True),
        sa.Column("contract_time", sa.String(50), nullable=True),
        sa.Column("is_remote", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("required_skills", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("experience_years_min", sa.Integer(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adzuna_id"),
    )
    op.create_index("ix_jobs_adzuna_id", "jobs", ["adzuna_id"])

    # job_fit_scores
    op.create_table(
        "job_fit_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=False),
        sa.Column("skills_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("experience_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("location_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("salary_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_skills", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("missing_skills", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("scored_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_id"),
    )
    op.create_index("ix_fit_scores_user_id", "job_fit_scores", ["user_id"])
    op.create_index("ix_fit_scores_job_id", "job_fit_scores", ["job_id"])

    # saved_jobs
    op.create_table(
        "saved_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_id"),
    )

    # dismissed_jobs
    op.create_table(
        "dismissed_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_id"),
    )

    # applications
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="'applied'"),
        sa.Column("applied_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("cover_note", sa.Text(), nullable=True),
        sa.Column("cover_note_shown", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("platform", sa.String(100), nullable=True),
        sa.Column("fit_score_snapshot", sa.Integer(), nullable=True),
        sa.Column("timeline", postgresql.JSON(), nullable=True, server_default="[]"),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])


def downgrade() -> None:
    op.drop_table("applications")
    op.drop_table("dismissed_jobs")
    op.drop_table("saved_jobs")
    op.drop_table("job_fit_scores")
    op.drop_table("jobs")
    op.drop_table("user_profiles")
    op.drop_table("users")
