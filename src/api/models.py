"""ORM schema: users, dogs, assessment, irt_response, recommendation, report.

Six tables, one file — small enough to read end to end, matching this project's
"can the author explain this under examination" standard. Never imported by
run_pipeline.py/rules.py/etc.: this is a layer that calls into the ML core, not the
other way round.
"""
from __future__ import annotations

from typing import Optional

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import (
    AccountStatus,
    AssessmentStatus,
    DogGender,
    DogStatus,
    Phenotype,
    ReportStatus,
    SeverityBand,
    UserRole,
)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# The repeated pattern below — SAEnum(SomeEnum, native_enum=False, values_callable=...) —
# stores the enum's plain string VALUE ("owner", not "OWNER") as a VARCHAR + CHECK
# constraint, on every database (native_enum=False avoids Postgres-only ENUM types, so
# the same column definition works unchanged against the SQLite test DB too).


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)  # bcrypt hash, never plaintext
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=UserRole.OWNER,
    )
    profile_picture: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=AccountStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    # Self-referential FK: who created/last edited this row (usually the user themself,
    # but lets an admin-on-behalf edit be recorded honestly instead of faked).
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.user_id"))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.user_id"))

    # relationship() is a Python-side convenience only — it doesn't add a column, it lets
    # code write `user.dogs` instead of a manual query for `Dog.user_id == user.user_id`.
    dogs: Mapped[list["Dog"]] = relationship(back_populates="owner", foreign_keys="Dog.user_id")


class Dog(Base):
    __tablename__ = "dogs"

    dog_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)  # the owner
    dog_name: Mapped[str] = mapped_column(String, nullable=False)
    dog_breed: Mapped[Optional[str]] = mapped_column(String)
    dog_age: Mapped[Optional[int]] = mapped_column(Integer)
    dog_gender: Mapped[Optional[DogGender]] = mapped_column(
        SAEnum(DogGender, native_enum=False, values_callable=lambda e: [m.value for m in e]),
    )
    profile_picture: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[DogStatus] = mapped_column(
        SAEnum(DogStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=DogStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.user_id"))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.user_id"))

    owner: Mapped["User"] = relationship(back_populates="dogs", foreign_keys=[user_id])
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="dog")


class Assessment(Base):
    """One row per submitted questionnaire — the persisted result of one score_case() call."""

    __tablename__ = "assessment"

    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    dog_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dogs.dog_id"), nullable=False)
    session_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1st, 2nd, ... for this dog

    # Exactly one of these two is non-null per row — never a bare "theta" column
    # (naming discipline, CODE_GUIDE.md). Which one depends on score_model_name.
    theta_irt: Mapped[Optional[float]] = mapped_column(Float)
    theta_calibrated: Mapped[Optional[float]] = mapped_column(Float)
    theta_se: Mapped[float] = mapped_column(Float, nullable=False)  # standard error of theta
    score_model_name: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "params_calibrated.csv"

    severity_band: Mapped[SeverityBand] = mapped_column(
        SAEnum(SeverityBand, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    phenotype: Mapped[Phenotype] = mapped_column(
        SAEnum(Phenotype, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    rf_confidence: Mapped[float] = mapped_column(Float, nullable=False)  # Random Forest confidence, 0-1

    # Kept as two independent booleans — never merged into one flag (CLAUDE.md).
    flag_irt: Mapped[bool] = mapped_column(Boolean, nullable=False)  # theta too imprecise -> withhold
    flag_rf: Mapped[bool] = mapped_column(Boolean, nullable=False)   # phenotype unsure -> downgrade only

    subscales: Mapped[dict] = mapped_column(JSON, nullable=False)  # the 6 subscale means, for reporting
    # Full snapshot of what rules.evaluate() actually returned at scoring time (see
    # services/scoring.py) — the history stays correct even if rules.py's wording
    # changes later, because this is a copy, not a live read.
    recommendation_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Convenience link to the matching static row in `recommendation` (for joins/reports
    # only) — never read back into rules.evaluate() or any scoring logic.
    recommendation_rec_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("recommendation.rec_id")
    )

    status: Mapped[AssessmentStatus] = mapped_column(
        SAEnum(AssessmentStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=AssessmentStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)

    dog: Mapped["Dog"] = relationship(back_populates="assessments")
    responses: Mapped[list["IRTResponse"]] = relationship(back_populates="assessment")
    reports: Mapped[list["Report"]] = relationship(back_populates="assessment")


class IRTResponse(Base):
    """The 12 raw Q4-Q15 answers behind one assessment — one row per item, not one wide row."""

    __tablename__ = "irt_response"
    __table_args__ = (UniqueConstraint("assessment_id", "item_code"),)  # exactly 12 rows/assessment

    response_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment.assessment_id"), nullable=False
    )
    item_code: Mapped[str] = mapped_column(String(3), nullable=False)  # "Q4".."Q15"
    likert_value: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-4, the raw answer

    assessment: Mapped["Assessment"] = relationship(back_populates="responses")


class Recommendation(Base):
    """Static reference table mirroring rules.py's 9 cells. Seeded once by an Alembic
    data migration; never read by score_case()/rules.evaluate() at scoring time."""

    __tablename__ = "recommendation"

    rec_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    severity_level: Mapped[SeverityBand] = mapped_column(
        SAEnum(SeverityBand, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    phenotype: Mapped[Phenotype] = mapped_column(
        SAEnum(Phenotype, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # e.g. "R-GEN-HIGH"
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)  # baseline action text
    evidence: Mapped[str] = mapped_column(Text, nullable=False)  # MSD/AAHA citation
    source: Mapped[Optional[str]] = mapped_column(String)  # "MSD" / "AAHA" / "MSD+AAHA"
    seeded_at: Mapped[datetime] = mapped_column(default=_now)


class Report(Base):
    """A generated clinical/audit document for one assessment, downloadable by its owner."""

    __tablename__ = "report"

    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment.assessment_id"), nullable=False
    )
    dog_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dogs.dog_id"), nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(default=_now)
    report_format: Mapped[str] = mapped_column(String, default="json")
    filepath: Mapped[Optional[str]] = mapped_column(String)  # reserved for a future on-disk PDF
    content: Mapped[dict] = mapped_column(JSON, nullable=False)  # the full report, snapshotted
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=ReportStatus.READY,
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)

    assessment: Mapped["Assessment"] = relationship(back_populates="reports")
