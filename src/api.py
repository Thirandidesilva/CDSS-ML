"""Exposes score_case() as a FastAPI endpoint for scoring a single dog's responses."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import run_pipeline  # noqa: E402


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class RecommendationOut(BaseModel):
    rule_id: str
    urgency: str
    action: str
    evidence: str
    withheld: bool
    withheld_reason: Optional[str]
    caveats: list[str]


class AssessmentResponse(BaseModel):
    theta: float
    theta_se: float
    severity: str
    phenotype: str
    rf_confidence: float
    flag_irt: bool
    flag_rf: bool
    recommendation: RecommendationOut


def create_app() -> FastAPI:
    app = FastAPI(title="Canine Anxiety CDSS", description=__doc__)
    model = run_pipeline.load_scoring_model()

    @app.post("/assess", response_model=AssessmentResponse)
    def assess(payload: AssessmentRequest) -> AssessmentResponse:
        result = run_pipeline.score_case(payload.model_dump(), model, verbose=False)
        return AssessmentResponse(
            theta=result["theta"],
            theta_se=result["theta_se"],
            severity=result["severity"],
            phenotype=result["phenotype"],
            rf_confidence=result["rf_confidence"],
            flag_irt=result["flag_irt"],
            flag_rf=result["flag_rf"],
            recommendation=result["recommendation"],
        )

    return app
