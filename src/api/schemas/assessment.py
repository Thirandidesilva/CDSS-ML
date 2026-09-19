"""Reuses the exact per-item validation pattern from the retired src/api.py: ge=0,le=4,
extra="forbid", descriptions sourced from run_pipeline.ITEM_TEXT.
"""
from __future__ import annotations

from typing import Optional

import sys
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import run_pipeline  # noqa: E402

from ..enums import Phenotype, SeverityBand  # noqa: E402


class AssessmentSubmitRequest(BaseModel):
    # extra="forbid" means a typo'd field name (e.g. "q4" instead of "Q4") is rejected
    # with a 422 instead of silently ignored.
    model_config = ConfigDict(extra="forbid")

    dog_id: uuid.UUID  # which dog this submission is for — checked for ownership in the router
    # ge=0, le=4: FastAPI/Pydantic reject anything outside 0-4 before score_case() ever
    # runs, with a 422 naming the exact field — this is the validation the project's
    # "fail loudly, never coerce" rule relies on. description=... is what shows up in
    # the interactive /docs page, pulled from the one place item wording is defined.
    Q4: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q4"])
    Q5: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q5"])
    Q6: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q6"])
    Q7: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q7"])
    Q8: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q8"])
    Q9: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q9"])
    Q10: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q10"])
    Q11: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q11"])
    Q12: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q12"])
    Q13: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q13"])
    Q14: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q14"])
    Q15: int = Field(ge=0, le=4, description=run_pipeline.ITEM_TEXT["Q15"])


class QuestionOut(BaseModel):
    # What GET /assessment/questions returns — one row per item, for a client to
    # render the questionnaire without hardcoding the wording itself.
    item_code: str
    text: str


class RecommendationOut(BaseModel):
    # Mirrors rules.Recommendation.to_dict() exactly — see rules.py for what each
    # field means and how withheld/withheld_reason get set.
    rule_id: str
    urgency: str
    action: str
    evidence: str
    withheld: bool
    withheld_reason: Optional[str]
    caveats: list[str]


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: uuid.UUID
    dog_id: uuid.UUID
    session_number: int
    theta_irt: Optional[float]
    theta_calibrated: Optional[float]  # exactly one of these two is non-null, see models.py
    theta_se: float
    severity_band: SeverityBand
    phenotype: Phenotype
    rf_confidence: float
    flag_irt: bool
    flag_rf: bool
    subscales: dict
    recommendation: RecommendationOut

    @classmethod
    def from_orm_row(cls, row) -> "AssessmentOut":
        # Can't just use from_attributes=True end to end here: recommendation_snapshot
        # is stored as a plain JSON dict on the Assessment row, not a nested ORM object,
        # so it needs to be unpacked into RecommendationOut by hand.
        return cls(
            assessment_id=row.assessment_id,
            dog_id=row.dog_id,
            session_number=row.session_number,
            theta_irt=row.theta_irt,
            theta_calibrated=row.theta_calibrated,
            theta_se=row.theta_se,
            severity_band=row.severity_band,
            phenotype=row.phenotype,
            rf_confidence=row.rf_confidence,
            flag_irt=row.flag_irt,
            flag_rf=row.flag_rf,
            subscales=row.subscales,
            recommendation=RecommendationOut(**row.recommendation_snapshot),
        )
