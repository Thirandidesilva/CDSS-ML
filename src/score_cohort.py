"""Scores the full cohort with IRT parameters and checks results against verified_facts.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import irt  # noqa: E402


def score_cohort() -> pd.DataFrame:
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    items, a, b = irt.load_params(ROOT / "data" / "reference" / "params_own.csv")

    est = irt.grm_eap(responses[items], items, a, b)
    out = responses[["ID"] + items].copy()
    out["theta_irt"] = est.theta.to_numpy()
    out["theta_se"] = est.theta_se.to_numpy()
    return out


def compare_to_verified_facts(scored: pd.DataFrame) -> None:
    facts = json.loads((ROOT / "handoff" / "verified_facts.json").read_text())
    params = pd.read_csv(ROOT / "data" / "reference" / "params_own.csv").set_index("item")

    rel_observed = irt.marginal_reliability(scored.theta_se, scored.theta_irt, denominator="observed")
    se_mean = float(scored.theta_se.mean())
    disc_min_item = params.discrimination_a.idxmin()
    disc_max_item = params.discrimination_a.idxmax()

    rows = [
        ("rel_observed", facts["rel_observed"], round(rel_observed, 3)),
        ("se_mean", facts["se_mean"], round(se_mean, 3)),
        ("disc_min", tuple(facts["disc_min"]),
         (disc_min_item, round(float(params.discrimination_a[disc_min_item]), 3))),
        ("disc_max", tuple(facts["disc_max"]),
         (disc_max_item, round(float(params.discrimination_a[disc_max_item]), 3))),
    ]
    print(f"{'quantity':<12} {'target':<22} {'obtained':<22} match")
    for name, target, obtained in rows:
        match = "yes" if target == obtained else "NO"
        print(f"{name:<12} {str(target):<22} {str(obtained):<22} {match}")
    print("\ndisc_min/disc_max identity mismatches are expected: Phase 1 corrected the "
          "Q7/Q8 and Q14/Q15 item mapping, so 'which Q number' is not comparable to the "
          "old (mismapped) target even if the underlying construct is the same.")


if __name__ == "__main__":
    scored = score_cohort()
    dest = ROOT / "results" / "scored_responses.csv"
    scored.to_csv(dest, index=False)
    print(f"wrote {dest} shape {scored.shape}\n")
    compare_to_verified_facts(scored)
