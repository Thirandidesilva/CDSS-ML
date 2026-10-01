"""Maps severity band + phenotype to a recommendation, withholding or downgrading on uncertainty."""
from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_BANDS = ["Low", "Moderate", "High"]
# Adapted from dict[int, str] (CODE_GUIDE.md's original contract): cluster.py now
# resolves cluster id -> label by profile shape before writing phenotype_profiles.csv,
# so downstream code reads the label directly. Kept here as the canonical valid set.
PHENOTYPE_LABELS = ["Mild", "Noise-specific", "Generalised"]

SE_THRESHOLD = 0.50
CONF_THRESHOLD = 0.70

# Grounded in the two source documents in docs/: MSD Veterinary Manual, "Behavior
# Problems of Dogs" (Borns-Weil, full review Sept 2025), and the 2015 AAHA Canine and
# Feline Behavior Management Guidelines. Section names below are the actual headers in
# those documents. This is management guidance, not a prescription: neither document
# supports naming a specific drug or dose without a veterinary exam, so none is named.
UNIVERSAL_CAVEAT = (
    "Avoid aversive/punishment-based methods (e.g., shock or prong collars, alpha rolls, "
    "flooding) — AAHA's 2015 guidelines report these worsen fear, anxiety, and aggression "
    "rather than resolving them."
)
SCREENING_CAVEAT = "This is a behavioural screening result, not a veterinary diagnosis."

_SEVERITY_ACTION = {
    "Low": "No behavioural intervention indicated by this screening. Continue routine "
           "positive-reinforcement handling and monitor for the signs of anxiety/distress "
           "listed in AAHA's Table 1, in case they increase.",
    "Moderate": "Begin environmental management: identify and reduce exposure to the "
                "situations that trigger signs, and start structured, positive-reinforcement "
                "interactions (a consistent 'cue-response-reward' routine). Reassess if "
                "signs increase or fail to improve.",
    "High": "Recommend prompt veterinary behavioural evaluation rather than waiting to see "
            "if signs resolve on their own. Continue avoidance/environmental management in "
            "the meantime; do not attempt punishment-based correction.",
}
_SEVERITY_URGENCY = {"Low": "routine", "Moderate": "routine", "High": "prompt"}
_SEVERITY_EVIDENCE = {
    "Low": "MSD Veterinary Manual, Behavior Problems of Dogs — 'Fears, Anxiety, and "
           "Phobias in Dogs': anxiety that is 'not excessive and not out of context' is "
           "normal and adaptive, not itself a disorder.",
    "Moderate": "MSD Veterinary Manual — 'Environmental Management' and 'Behavior "
                "Modification for Fear, Anxiety, and Aggression-Related Behavior Problems "
                "in Dogs' (structured interaction / cue-response-reward programs).",
    "High": "MSD Veterinary Manual — referral to a veterinary behaviourist 'is warranted' "
            "for pronounced cases; AAHA 2015 Guidelines, 'Separation Anxiety' — this class "
            "of presentation 'should be considered a behavioral emergency.'",
}
_PHENOTYPE_ADDENDUM = {
    "Mild": "",
    "Noise-specific": (
        " Signs are concentrated around loud noises/storms. MSD's 'Treatment of Phobias "
        "of Discrete Stimuli in Dogs' recommends building a safe haven the dog already "
        "associates positively with, well before a noise event, and controlled exposure "
        "(e.g., recordings at low volume paired with something the dog enjoys) rather than "
        "letting the dog simply endure the noise at full intensity — MSD is explicit that "
        "'flooding is not recommended.' Discuss any as-needed anxiolytic use with your "
        "veterinarian; AAHA notes this is typically given ahead of a predictable trigger."
    ),
    "Generalised": (
        " Signs span multiple contexts, not just one trigger. MSD notes 'substantial "
        "comorbidity between noise phobia and separation distress disorder,' and AAHA's "
        "Noise Phobia guidance stresses that screening for such overlapping conditions "
        "matters because 'comorbidity worsens each condition.' A plan addressing one "
        "trigger in isolation is unlikely to be sufficient here."
    ),
}


def _phenotype_code(phenotype: str) -> str:
    return {"Mild": "MILD", "Noise-specific": "NOISE", "Generalised": "GEN"}[phenotype]


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
    if band not in SEVERITY_BANDS:
        raise ValueError(f"unknown band {band!r}; expected one of {SEVERITY_BANDS}")
    if phenotype not in PHENOTYPE_LABELS:
        raise ValueError(f"unknown phenotype {phenotype!r}; expected one of {PHENOTYPE_LABELS}")

    rule_id = f"R-{_phenotype_code(phenotype)}-{band.upper()}"
    evidence = _SEVERITY_EVIDENCE[band]

    if flag_irt:
        return Recommendation(
            rule_id=rule_id,
            urgency="unknown",
            action="Recommendation withheld pending a more precise assessment; "
                   "consult your veterinarian if you have concerns.",
            evidence=evidence,
            withheld=True,
            withheld_reason=f"theta SE {theta_se:.3f} exceeds {SE_THRESHOLD}; "
                             "severity band is too imprecise to act on",
            caveats=[SCREENING_CAVEAT],
        )

    action = _SEVERITY_ACTION[band]
    caveats = [SCREENING_CAVEAT, UNIVERSAL_CAVEAT]
    if flag_rf:
        caveats.append(f"phenotype confidence {rf_confidence:.2f} below {CONF_THRESHOLD}; "
                        "type-specific content suppressed, severity-appropriate action stands")
    else:
        action += _PHENOTYPE_ADDENDUM[phenotype]

    return Recommendation(
        rule_id=rule_id,
        urgency=_SEVERITY_URGENCY[band],
        action=action,
        evidence=evidence,
        withheld=False,
        withheld_reason=None,
        caveats=caveats,
    )


def detectable_change(
    theta_before: float,
    theta_after: float,
    se_before: float,
    se_after: float,
) -> dict:
    """MDC95 = 1.96 * sqrt(se_before^2 + se_after^2) (standard reliable-change-index
    formula). A change below this threshold is not distinguishable from measurement
    noise, regardless of which severity band it happens to cross.
    """
    delta = theta_after - theta_before
    mdc95 = 1.96 * (se_before ** 2 + se_after ** 2) ** 0.5
    detectable = abs(delta) >= mdc95
    return {
        "theta_before": theta_before,
        "theta_after": theta_after,
        "delta": delta,
        "mdc95": mdc95,
        "detectable": detectable,
        "statement": (
            f"theta change of {delta:+.3f} exceeds the 95% minimum detectable change "
            f"({mdc95:.3f})" if detectable else
            f"theta change of {delta:+.3f} is not distinguishable from measurement "
            f"noise (95% minimum detectable change is {mdc95:.3f})"
        ),
    }
