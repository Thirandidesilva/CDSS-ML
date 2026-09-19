"""Request/response shapes for the report/ router."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..enums import ReportStatus


class ReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: uuid.UUID  # which assessment to build the report from


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: uuid.UUID
    assessment_id: uuid.UUID
    dog_id: uuid.UUID       # denormalized from the assessment, so ownership checks need no join
    generated_by: uuid.UUID  # who requested it — used for the owner-only /report list+download
    generated_at: datetime
    report_format: str
    status: ReportStatus
    content: dict  # the full clinical/audit payload, see services/report.py
