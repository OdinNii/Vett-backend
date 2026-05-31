"""add notification schedule and target_roles to user_profiles

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("notification_time", sa.String(20), nullable=True, server_default="morning"),
    )
    op.add_column(
        "user_profiles",
        sa.Column("notification_frequency", sa.String(20), nullable=False, server_default="daily"),
    )
    op.add_column(
        "user_profiles",
        sa.Column("timezone", sa.String(100), nullable=True, server_default="UTC"),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "target_roles",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "target_roles")
    op.drop_column("user_profiles", "timezone")
    op.drop_column("user_profiles", "notification_frequency")
    op.drop_column("user_profiles", "notification_time")
