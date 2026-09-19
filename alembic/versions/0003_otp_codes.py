"""otp_codes: one-time codes for the forget-username/forget-password flows

Revision ID: 0003_otp_codes
Revises: 0002_seed_recommendation_table
Create Date: 2026-09-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_otp_codes"
down_revision = "0002_seed_recommendation_table"
branch_labels = None
depends_on = None

_now = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "otp_codes",
        sa.Column("otp_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum("forget_username", "forget_password", name="otp_purpose", native_enum=False),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    )


def downgrade() -> None:
    op.drop_table("otp_codes")
