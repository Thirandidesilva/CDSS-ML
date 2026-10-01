"""Fits and serialises the phenotype-confidence Random Forest on the twelve raw items."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cluster  # noqa: E402
import irt      # noqa: E402

MODELS = ROOT / "models"


def main():
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")

    labels, profiles = cluster.fit_clusters(responses)
    mapping = cluster.label_clusters_by_profile(profiles)
    phenotype = labels.map(mapping)

    X = responses[irt.ITEMS_ALL]
    model = RandomForestClassifier(n_estimators=200, random_state=42)
    model.fit(X, phenotype)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_accuracy = float(cross_val_score(model, X, phenotype, cv=cv).mean())

    MODELS.mkdir(exist_ok=True)
    joblib.dump(model, MODELS / "phenotype_rf.joblib")

    metadata = {
        "n": len(responses),
        "features": list(irt.ITEMS_ALL),
        "cv_accuracy": round(cv_accuracy, 4),
        "cv_scheme": "StratifiedKFold(n_splits=5, shuffle=True, random_state=42) — "
                     "results/rf_confidence_calibration.csv (referenced by BUILD_BRIEF.md) "
                     "does not exist in this repo, so a standard scheme was substituted.",
        "sklearn_version": sklearn.__version__,
    }
    with open(MODELS / "phenotype_rf_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"wrote {MODELS / 'phenotype_rf.joblib'}")
    print(f"wrote {MODELS / 'phenotype_rf_metadata.json'}")
    print(f"\ncv_accuracy: {cv_accuracy:.4f}")
    print("phenotype distribution:", phenotype.value_counts().to_dict())


if __name__ == "__main__":
    main()
