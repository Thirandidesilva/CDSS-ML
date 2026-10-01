"""Checks whether C-BARQ's own independent subscales corroborate separation and noise/fear as separable constructs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATA_PATH = ROOT / "data" / "raw" / "CBARQ.dat"
RESULTS = ROOT / "results"

PRIMARY_PAIR = ("sepprobs", "nonsocialfear")
PAIRS = [
    ("sepprobs", "nonsocialfear"),
    ("sepprobs", "strangerfear"),
    ("strangerfear", "nonsocialfear"),
]


def corroborate():
    c = pd.read_csv(DATA_PATH, sep="\t")

    results = []
    for a, b in PAIRS:
        sub = c[[a, b]].dropna()
        r = float(sub[a].corr(sub[b]))
        results.append({"a": a, "b": b, "r": round(r, 4), "n": len(sub)})
        primary = " (primary: separation vs noise/general-fear)" if (a, b) == PRIMARY_PAIR else ""
        print(f"{a} vs {b}: r={r:.4f}  n={len(sub)}{primary}")

    interpretation = (
        "sepprobs (separation problems) vs nonsocialfear (fear of loud noises, unfamiliar "
        "objects/situations - the closest available proxy to noise-related fear; no literal "
        "'noise' subscale exists in this file) is the primary comparison. strangerfear (fear "
        "of unfamiliar people) is a different construct closer to Q9 and is reported for "
        "context only, not as the noise proxy."
    )
    print(f"\n{interpretation}")

    out = {"pairs": results, "primary_pair": list(PRIMARY_PAIR), "interpretation": interpretation}
    dest = RESULTS / "cbarq_corroboration.json"
    with open(dest, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    corroborate()
