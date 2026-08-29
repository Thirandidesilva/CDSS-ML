"""Maps severity band + phenotype to a recommendation, withholding or downgrading on uncertainty."""
from __future__ import annotations

from dataclasses import dataclass, field

# TODO: cluster id -> phenotype label, filled in once cluster.py exists
PHENOTYPE_LABELS: dict[int, str] = {}


@dataclass
class Recommendation:
    rule_id: str
    urgency: str
    action: str
    evidence: str
    withheld: bool
    withheld_reason: str | None
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "urgency": self.urgency,
            "action": self.action,
            "evidence": self.evidence,
            "withheld": self.withheld,
            "withheld_reason": self.withheld_reason,
            "caveats": list(self.caveats),
        }


def evaluate(
    band: str,
    phenotype: str,
    *,
    flag_irt: bool,
    flag_rf: bool,
    theta_se: float,
    rf_confidence: float,
) -> Recommendation:
    # TODO: 9 explicit cells (band x phenotype), no default branch;
    # flag_irt withholds entirely, flag_rf downgrades only
    raise NotImplementedError


def detectable_change(
    theta_before: float,
    theta_after: float,
    se_before: float,
    se_after: float,
) -> dict:
    # TODO: compare theta delta against MDC95 = 1.508
    raise NotImplementedError
