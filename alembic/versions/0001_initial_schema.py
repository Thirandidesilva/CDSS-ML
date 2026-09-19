"""initial schema: users, dogs, assessment, irt_response, recommendation, report

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

_now = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Uuid, primary_key=True),
        sa.Column("user_name", sa.String, nullable=False, unique=True),
        sa.Column("first_name", sa.String),
        sa.Column("last_name", sa.String),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("phone_number", sa.String),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column(
            "role", sa.Enum("owner", "admin", name="user_role", native_enum=False),
            nullable=False, server_default="owner",
        ),
        sa.Column("profile_picture", sa.String),
        sa.Column(
            "status", sa.Enum("active", "disabled", "deleted", name="account_status", native_enum=False),
            nullable=False, server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.user_id")),
        sa.Column("updated_by", sa.Uuid, sa.ForeignKey("users.user_id")),
    )

    op.create_table(
        "dogs",
        sa.Column("dog_id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("dog_name", sa.String, nullable=False),
        sa.Column("dog_breed", sa.String),
        sa.Column("dog_age", sa.Integer),
        sa.Column(
            "dog_gender", sa.Enum("male", "female", "unknown", name="dog_gender", native_enum=False),
        ),
        sa.Column("profile_picture", sa.String),
        sa.Column(
            "status", sa.Enum("active", "deleted", name="dog_status", native_enum=False),
            nullable=False, server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.user_id")),
        sa.Column("updated_by", sa.Uuid, sa.ForeignKey("users.user_id")),
    )

    op.create_table(
        "recommendation",
        sa.Column("rec_id", sa.Uuid, primary_key=True),
        sa.Column(
            "severity_level",
            sa.Enum("Low", "Moderate", "High", name="severity_band", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "phenotype",
            sa.Enum("Mild", "Noise-specific", "Generalised", name="phenotype_label", native_enum=False),
            nullable=False,
        ),
        sa.Column("rule_id", sa.String, nullable=False, unique=True),
        sa.Column("recommendation_text", sa.Text, nullable=False),
        sa.Column("evidence", sa.Text, nullable=False),
        sa.Column("source", sa.String),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    )

    op.create_table(
        "assessment",
        sa.Column("assessment_id", sa.Uuid, primary_key=True),
        sa.Column("dog_id", sa.Uuid, sa.ForeignKey("dogs.dog_id"), nullable=False),
        sa.Column("session_number", sa.Integer, nullable=False),
        sa.Column("theta_irt", sa.Float),
        sa.Column("theta_calibrated", sa.Float),
        sa.Column("theta_se", sa.Float, nullable=False),
        sa.Column("score_model_name", sa.String, nullable=False),
        sa.Column(
            "severity_band",
            sa.Enum("Low", "Moderate", "High", name="severity_band", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "phenotype",
            sa.Enum("Mild", "Noise-specific", "Generalised", name="phenotype_label", native_enum=False),
            nullable=False,
        ),
        sa.Column("rf_confidence", sa.Float, nullable=False),
        sa.Column("flag_irt", sa.Boolean, nullable=False),
        sa.Column("flag_rf", sa.Boolean, nullable=False),
        sa.Column("subscales", sa.JSON, nullable=False),
        sa.Column("recommendation_snapshot", sa.JSON, nullable=False),
        sa.Column("recommendation_rec_id", sa.Uuid, sa.ForeignKey("recommendation.rec_id")),
        sa.Column(
            "status", sa.Enum("active", "deleted", name="assessment_status", native_enum=False),
            nullable=False, server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.user_id"), nullable=False),
    )

    op.create_table(
        "irt_response",
        sa.Column("response_id", sa.Uuid, primary_key=True),
        sa.Column("assessment_id", sa.Uuid, sa.ForeignKey("assessment.assessment_id"), nullable=False),
        sa.Column("item_code", sa.String(3), nullable=False),
        sa.Column("likert_value", sa.Integer, nullable=False),
        sa.UniqueConstraint("assessment_id", "item_code"),
        sa.CheckConstraint("likert_value >= 0 AND likert_value <= 4", name="ck_likert_range"),
    )

    op.create_table(
        "report",
        sa.Column("report_id", sa.Uuid, primary_key=True),
        sa.Column("assessment_id", sa.Uuid, sa.ForeignKey("assessment.assessment_id"), nullable=False),
        sa.Column("dog_id", sa.Uuid, sa.ForeignKey("dogs.dog_id"), nullable=False),
        sa.Column("generated_by", sa.Uuid, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
        sa.Column("report_format", sa.String, server_default="json"),
        sa.Column("filepath", sa.String),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column(
            "status", sa.Enum("generating", "ready", "failed", name="report_status", native_enum=False),
            nullable=False, server_default="ready",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now),
    )


def downgrade() -> None:
    op.drop_table("report")
    op.drop_table("irt_response")
    op.drop_table("assessment")
    op.drop_table("recommendation")
    op.drop_table("dogs")
    op.drop_table("users")
