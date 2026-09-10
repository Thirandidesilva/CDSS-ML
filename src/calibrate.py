"""Refits GRM item parameters on Darwin's Ark data and reconciles severity band counts."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fit_params  # noqa: E402
import irt          # noqa: E402

ZIP_PATH = ROOT / "data" / "raw" / "DarwinsArk.zip"
ANSWERS_ENTRY = "DarwinsArk/DarwinsArk_20191115_answers.csv"
MAPPING_PATH = ROOT / "data" / "raw" / "darwins_ark_item_mapping.csv"
REF = ROOT / "data" / "reference"
RESULTS = ROOT / "results"

PERCENTILES = [50, 75, 85, 90, 95, 99]
CHAPTER_BANDS = {"Low": 98, "Moderate": 24, "High": 41}


def load_mapping():
    mapping = pd.read_csv(MAPPING_PATH).dropna(subset=["darwins_ark_id"]).copy()
    mapping["darwins_ark_id"] = mapping["darwins_ark_id"].astype(int)
    return mapping


def load_darwins_ark_matrix(mapping: pd.DataFrame):
    """Reads Darwin's Ark answers straight out of the zip, recodes to our 0-4 GRM scale, keeps complete cases only."""
    with zipfile.ZipFile(ZIP_PATH) as zf:
        with zf.open(ANSWERS_ENTRY) as f:
            answers = pd.read_csv(f, usecols=["dog", "question", "answer"])

    answers = answers[answers["question"].isin(mapping["darwins_ark_id"])]
    wide = answers.pivot_table(index="dog", columns="question", values="answer", aggfunc="first")

    recoded = {}
    for _, row in mapping.iterrows():
        col = wide[row["darwins_ark_id"]]
        recoded[row["item"]] = (4 - col) if row["recoding"] == "4-raw" else col
    wide = pd.DataFrame(recoded)

    complete = wide.dropna()
    return complete[mapping["item"].tolist()].astype(int)


def assign_band(theta, cut75, cut90):
    if theta < cut75:
        return "Low"
    if theta < cut90:
        return "Moderate"
    return "High"


def calibrate():
    mapping = load_mapping()
    items = mapping["item"].tolist()
    print(f"mapped items ({len(items)}): {items}")

    darwins_ark = load_darwins_ark_matrix(mapping)
    print(f"Darwin's Ark complete cases across mapped items: {len(darwins_ark)}")

    print("\nrefitting GRM on Darwin's Ark ...")
    best_params, best_ll, ll_spread, a_spread = fit_params.check_stability(
        darwins_ark, items=items, n_restarts=5, seed=0)

    dest = REF / "params_calibrated.csv"
    best_params.to_csv(dest, index=False)
    print(f"\nwrote {dest} (log-likelihood {best_ll:.3f})")
    print(best_params.sort_values("discrimination_a").to_string(index=False))

    a = best_params["discrimination_a"].to_numpy(float)
    b = best_params[["b1", "b2", "b3", "b4"]].to_numpy(float)

    darwins_est = irt.grm_eap(darwins_ark, items, a, b)
    norms = pd.DataFrame({
        "percentile": PERCENTILES,
        "theta_cutpoint": [round(float(np.percentile(darwins_est.theta, p)), 4)
                           for p in PERCENTILES],
    })
    norms_dest = REF / "population_norms_theta.csv"
    norms.to_csv(norms_dest, index=False)
    print(f"\nwrote {norms_dest}")
    print(norms.to_string(index=False))

    cut75 = float(norms.set_index("percentile").loc[75, "theta_cutpoint"])
    cut90 = float(norms.set_index("percentile").loc[90, "theta_cutpoint"])

    ours = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    our_est = irt.grm_eap(ours[items], items, a, b)
    scored = ours[["ID"] + items].copy()
    scored["theta_calibrated"] = our_est.theta
    scored["theta_se"] = our_est.theta_se

    scored_dest = RESULTS / "scored_responses_calibrated.csv"
    scored.to_csv(scored_dest, index=False)
    print(f"\nwrote {scored_dest}")
    assert scored["theta_calibrated"].notna().all(), "theta_calibrated has nulls"

    bands = scored["theta_calibrated"].apply(lambda t: assign_band(t, cut75, cut90))
    counts = bands.value_counts().reindex(["Low", "Moderate", "High"]).fillna(0).astype(int)

    print("\nregenerated band counts (calibrated theta, calibrated 75th/90th cut-points):")
    print(counts.to_string())
    print(f"\nchapter's stated band counts: {CHAPTER_BANDS}")

    if counts.to_dict() != CHAPTER_BANDS:
        print(
            "\nDIVERGES from the chapter's 98/24/41. Not adjusting cut-points to force "
            "agreement. For the chapter's numbers to be right, theta_calibrated would have "
            "to have been computed from a different (never-persisted) calibrated fit, or "
            "the reference distribution behind the 75th/90th cut-points would have to be a "
            "different population than the one Darwin's Ark's complete-case cohort "
            f"(n={len(darwins_ark)}) gives here. The band counts above are what "
            "data/reference/params_calibrated.csv and population_norms_theta.csv actually "
            "produce when run end to end, and are reproducible by re-running this script."
        )
    else:
        print("\nMATCHES the chapter's 98/24/41.")


if __name__ == "__main__":
    calibrate()
