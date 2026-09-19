"""Builds the full clinical/audit report payload for one assessment."""
from __future__ import annotations

from ..models import Assessment


def build_report_content(assessment: Assessment) -> dict:
    # Full clinical/audit detail (theta, both flags kept separate, rule_id, evidence) —
    # this is for the author/examiner/clinician, not the plain-language owner-facing
    # summary that Phase 12 (still unbuilt) would produce instead.
    return {
        "assessment_id": str(assessment.assessment_id),
        "dog_id": str(assessment.dog_id),
        "session_number": assessment.session_number,
        "theta_irt": assessment.theta_irt,
        "theta_calibrated": assessment.theta_calibrated,
        "theta_se": assessment.theta_se,
        "score_model_name": assessment.score_model_name,
        "severity_band": assessment.severity_band.value,
        "phenotype": assessment.phenotype.value,
        "rf_confidence": assessment.rf_confidence,
        "flag_irt": assessment.flag_irt,
        "flag_rf": assessment.flag_rf,
        "subscales": assessment.subscales,
        "recommendation": assessment.recommendation_snapshot,
        "generated_from_created_at": assessment.created_at.isoformat(),
    }
