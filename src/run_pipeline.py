"""Runs one dog's responses through every stage and returns the full audit trail."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import irt      # noqa: E402
import rules    # noqa: E402

REF = ROOT / "data" / "reference"
RESULTS = ROOT / "results"

# "calibrated" needs Darwin's Ark (Phase 9); "own" is the fallback, demo-quality only.
PARAM_PREFERENCE = ["params_calibrated.csv", "params_own.csv"]

LIKERT = {"Never": 0, "Rarely": 1, "Sometimes": 2, "Often": 3, "Always": 4}
SUBSCALES = {
    "separation":    ["Q4", "Q5", "Q6", "Q11"],
    "noise":         ["Q7", "Q8"],
    "fear":          ["Q9", "Q13"],
    "aggression":    ["Q10"],
    "compulsive":    ["Q12"],
    "physiological": ["Q14", "Q15"],
}
ITEM_TEXT = {
    "Q4": "Trembles, shakes, or appears distressed when left alone",
    "Q5": "Barks, howls, or whines persistently when left alone",
    "Q6": "Destroys or chews household objects when left alone",
    "Q7": "Shows fear or panic during thunderstorms or fireworks",
    "Q8": "Hides, cowers, or freezes at sudden loud noises",
    "Q9": "Shows fear of or avoids unfamiliar people",
    "Q10": "Growls, snaps, or barks aggressively at strangers approaching the home",
    "Q11": "Follows you constantly and becomes distressed when you leave the room",
    "Q12": "Engages in repetitive behaviours: pacing, tail chasing, excessive licking",
    "Q13": "Trembles, shakes, or pants excessively in unfamiliar places (vet, car journey)",
    "Q14": "Loses appetite or refuses to eat during stressful situations",
    "Q15": "Has difficulty settling or calming down after a stressful event",
}


def load_scoring_model():
    """Picks the best available parameter set and its matching reference norms."""
    for name in PARAM_PREFERENCE:
        path = REF / name
        if path.exists():
            items, a, b = irt.load_params(path)
            norms_path = (REF / "population_norms_theta.csv"
                          if name.startswith("params_calibrated")
                          else REF / "population_norms_own_theta.csv")
            if not norms_path.exists():
                scored = pd.read_csv(RESULTS / "scored_responses.csv")
                est = irt.grm_eap(scored[items], items, a, b)
                norms = pd.DataFrame({
                    "percentile": [50, 75, 85, 90, 95, 99],
                    "theta_cutpoint": [round(float(np.percentile(est.theta, p)), 4)
                                       for p in (50, 75, 85, 90, 95, 99)]})
                norms.to_csv(norms_path, index=False)
                print(f"  NOTE: no reference norms for {name}; derived COHORT-relative\n"
                      f"        cut-points and wrote {norms_path.name}. These are a\n"
                      f"        within-sample ranking, not a population reference.")
            else:
                norms = pd.read_csv(norms_path)
            return name, items, a, b, norms
    sys.exit("no item-parameter file found in data/reference/")


def encode(answers):
    """Maps Likert labels or ints to 0-4 for all twelve items."""
    row = {}
    for q in irt.ITEMS_ALL:
        v = answers.get(q)
        if v is None:
            raise KeyError(f"no answer for {q}")
        if isinstance(v, str):
            v = LIKERT.get(v.strip().title())
            if v is None:
                raise ValueError(f"unrecognised response for {q}: {answers[q]!r}")
        row[q] = int(v)
    return pd.DataFrame([row])


def subscale_means(items):
    return {name: float(items[qs].mean(axis=1).iloc[0])
            for name, qs in SUBSCALES.items()}


def assign_band(theta, norms):
    """Population-referenced band, not cohort-relative — avoids guaranteeing a fixed fraction of any sample lands in each band."""
    cut = norms.set_index("percentile").theta_cutpoint
    if theta < cut.loc[75]:
        return "Low"
    if theta < cut.loc[90]:
        return "Moderate"
    return "High"


def assign_phenotype(items):
    """Nearest-centroid label; confidence is softmax-over-distance, a stand-in until Phase 8's Random Forest is serialised."""
    prof = pd.read_csv(RESULTS / "phenotype_profiles.csv").set_index("phenotype")
    cent = prof[irt.ITEMS_ALL]
    x = items[irt.ITEMS_ALL].to_numpy(float).ravel()
    dist = np.linalg.norm(cent.to_numpy(float) - x, axis=1)
    ix = int(np.argmin(dist))
    cid = cent.index[ix]
    assert cid in rules.PHENOTYPE_LABELS, f"unexpected phenotype label {cid!r} in phenotype_profiles.csv"
    w = np.exp(-dist)
    conf = float(w[ix] / w.sum())
    return cid, conf


def uncertainty_flags(theta_se, rf_conf, se_threshold=0.50, conf_threshold=0.70):
    """Two independent flags: measurement imprecision and phenotype-label uncertainty, never combined."""
    return theta_se > se_threshold, rf_conf < conf_threshold


def score_case(answers, model=None, *, verbose=True):
    """Runs one case through every stage; returns the full audit dict."""
    if model is None:
        model = load_scoring_model()
    pname, items_used, a, b, norms = model

    items = encode(answers)
    subs = subscale_means(items)
    est = irt.grm_eap(items[items_used], items_used, a, b)
    theta = float(est.theta.iloc[0])
    se = float(est.theta_se.iloc[0])
    band = assign_band(theta, norms)
    pheno, conf = assign_phenotype(items)
    f_irt, f_rf = uncertainty_flags(se, conf)
    rec = rules.evaluate(band, pheno, flag_irt=f_irt, flag_rf=f_rf,
                         theta_se=se, rf_confidence=conf)

    if verbose:
        print(f"  stage 1  encode            raw sum {int(items.sum(axis=1).iloc[0])}/48")
        print(f"           subscales         " +
              ", ".join(f"{k} {v:.2f}" for k, v in subs.items()))
        print(f"  stage 2  GRM theta         {theta:+.3f}  (SE {se:.3f}, "
              f"{len(items_used)} items, {pname})")
        print(f"  stage 3  severity band     {band}")
        print(f"  stage 4  phenotype         {pheno}  (confidence {conf:.2f})")
        print(f"  stage 5  flags             measurement={f_irt}  phenotype={f_rf}")
        print(f"  stage 6  rule              {rec.rule_id}  [{rec.urgency}]")
        print(f"           action            {rec.action}")
        if rec.withheld:
            print(f"           WITHHELD          {rec.withheld_reason}")
        for c in rec.caveats:
            print(f"           caveat            {c[:88]}")

    return dict(theta=theta, theta_se=se, severity=band, phenotype=pheno,
                rf_confidence=conf, flag_irt=f_irt, flag_rf=f_rf,
                subscales=subs, recommendation=rec.to_dict())


def demo():
    model = load_scoring_model()
    print(f"\nscoring model: {model[0]}  ({len(model[1])} items)\n")
    scored = pd.read_csv(RESULTS / "scored_responses.csv")
    picks = {"lowest theta": scored.theta_irt.idxmin(),
             "median theta": (scored.theta_irt - scored.theta_irt.median()).abs().idxmin(),
             "highest theta": scored.theta_irt.idxmax()}
    for label, ix in picks.items():
        row = scored.loc[ix]
        print(f"--- {row.ID}  ({label}) " + "-" * 44)
        score_case({q: int(row[q]) for q in irt.ITEMS_ALL}, model)
        print()


def score_all():
    model = load_scoring_model()
    scored = pd.read_csv(RESULTS / "scored_responses.csv")
    out = []
    for _, row in scored.iterrows():
        r = score_case({q: int(row[q]) for q in irt.ITEMS_ALL}, model, verbose=False)
        out.append(dict(ID=row.ID, theta=r["theta"], theta_se=r["theta_se"],
                        severity=r["severity"], phenotype=r["phenotype"],
                        rf_confidence=r["rf_confidence"],
                        flag_irt=r["flag_irt"], flag_rf=r["flag_rf"],
                        rule_id=r["recommendation"]["rule_id"],
                        withheld=r["recommendation"]["withheld"],
                        urgency=r["recommendation"]["urgency"]))
    df = pd.DataFrame(out)
    dest = RESULTS / "pipeline_output_cohort.csv"
    df.to_csv(dest, index=False)
    print(f"\nscored {len(df)} dogs with {model[0]} -> {dest.name}\n")
    print("severity distribution:", df.severity.value_counts().to_dict())
    print("phenotype distribution:", df.phenotype.value_counts().to_dict())
    print("rules fired:", df.rule_id.value_counts().to_dict())
    n_w = int(df.withheld.sum())
    print(f"\nrecommendation withheld for {n_w} of {len(df)} dogs "
          f"({100 * n_w / len(df):.1f}%) — this number belongs in the evaluation,\n"
          "because a system that never withholds is not more useful, only less honest.")


def interactive():
    print("\nAnswer each item: Never / Rarely / Sometimes / Often / Always\n")
    answers = {}
    for q in irt.ITEMS_ALL:
        while True:
            v = input(f"  {q}. {ITEM_TEXT[q]}\n      > ").strip().title()
            if v in LIKERT:
                answers[q] = v
                break
            print("      expected one of: Never, Rarely, Sometimes, Often, Always")
    print()
    score_case(answers)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="score the whole cohort")
    ap.add_argument("--interactive", action="store_true", help="enter one dog by hand")
    args = ap.parse_args()
    if args.all:
        score_all()
    elif args.interactive:
        interactive()
    else:
        demo()
