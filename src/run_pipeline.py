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
# TODO: confirm subscale groupings and item text against data/raw/item_mapping.csv (Phase 1)
SUBSCALES: dict[str, list[str]] = {}
ITEM_TEXT: dict[str, str] = {}


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
