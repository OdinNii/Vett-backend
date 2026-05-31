"""add email_notifications to user_profiles

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "email_notifications",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("last_digest_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "last_digest_sent_at")
    op.drop_column("user_profiles", "email_notifications")
