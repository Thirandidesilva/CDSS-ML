"""Runs one dog's responses through every stage and returns the full audit trail."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import irt      # noqa: E402
import rules    # noqa: E402

REF = ROOT / "data" / "reference"
RESULTS = ROOT / "results"

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
    # TODO: pick params_calibrated.csv if present, else params_own.csv, plus matching norms
    raise NotImplementedError


def encode(answers):
    # TODO: map Likert labels/ints to 0-4 for all twelve items
    raise NotImplementedError


def subscale_means(items):
    # TODO: mean per subscale, for phenotype + rules only, never for severity
    raise NotImplementedError


def assign_band(theta, norms):
    # TODO: Low < 75th percentile, Moderate 75th-90th, High >= 90th of reference distribution
    raise NotImplementedError


def assign_phenotype(items):
    # TODO: nearest-centroid label against phenotype_profiles.csv + calibrated RF confidence
    raise NotImplementedError


def uncertainty_flags(theta_se, rf_conf, se_threshold=0.50, conf_threshold=0.70):
    # TODO: flag_irt = theta_se > se_threshold, flag_rf = rf_conf < conf_threshold
    raise NotImplementedError


def score_case(answers, model=None, *, verbose=True):
    # TODO: run all stages, return the audit dict rules.py/api.py depend on
    raise NotImplementedError


def demo():
    raise NotImplementedError


def score_all():
    raise NotImplementedError


def interactive():
    raise NotImplementedError


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
