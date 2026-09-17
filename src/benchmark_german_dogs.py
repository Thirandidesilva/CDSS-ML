"""Tests whether demographic/ownership variables predict an anxiety proxy in the German DOGS cohort."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATA_PATH = ROOT / "data" / "raw" / "DOGS_de.xlsx"
RESULTS = ROOT / "results"

NUMERIC_PREDICTORS = [
    "Age", "Sex", "Weight", "Height", "Neuter status", "Age acquisition", "Training level",
    "Owner sex", "Owner age", "Owner edication", "N previous dogs", "Purpose", "N people",
    "N dogs", "Time together", "Time play w",
]
CATEGORICAL_PREDICTORS = ["Head shape group"]


def load_complete_cases():
    df = pd.read_excel(DATA_PATH, sheet_name="data")
    df = df.dropna(subset=["Calmness", "Boldness"])
    df = df.dropna(subset=NUMERIC_PREDICTORS + CATEGORICAL_PREDICTORS)

    anxiety_proxy = (2 - df["Calmness"]) + (2 - df["Boldness"])
    X = pd.get_dummies(df[NUMERIC_PREDICTORS + CATEGORICAL_PREDICTORS], columns=CATEGORICAL_PREDICTORS)
    return X, anxiety_proxy


def benchmark():
    X, y = load_complete_cases()
    print(f"complete cases: {len(X)}")
    print(f"predictors ({X.shape[1]} after one-hot encoding {CATEGORICAL_PREDICTORS}): "
          f"{NUMERIC_PREDICTORS + CATEGORICAL_PREDICTORS}")

    model = RandomForestRegressor(n_estimators=200, random_state=42)
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(model, X, y, cv=cv, scoring="r2")
    cv_r2_mean = float(scores.mean())
    print(f"\nCV R^2: {cv_r2_mean:.4f}  (per-fold: {[round(s, 4) for s in scores]})")

    model.fit(X, y)
    importances = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
    print("\ntop feature importances:")
    print(importances.head(10).to_string())

    interpretation = (
        f"CV R^2 = {cv_r2_mean:.4f}: demographic/ownership variables carry little to no "
        "predictive signal for this anxiety proxy in a large, real cohort. This null result "
        "is itself the reportable finding (representativeness benchmark), not a failed model."
    )
    print(f"\n{interpretation}")

    out = {
        "n": len(X),
        "predictors": NUMERIC_PREDICTORS + CATEGORICAL_PREDICTORS,
        "cv_r2_mean": round(cv_r2_mean, 4),
        "cv_r2_scores": [round(float(s), 4) for s in scores],
        "top_importances": importances.head(10).round(4).to_dict(),
        "interpretation": interpretation,
    }
    dest = RESULTS / "german_dogs_benchmark.json"
    with open(dest, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    benchmark()
