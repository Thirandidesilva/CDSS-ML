import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import run_pipeline  # noqa: E402

FORBIDDEN_FEATURES = [
    "anxiety_index", "raw_score",
    *run_pipeline.SUBSCALES.keys(),
    "theta", "theta_irt", "theta_calibrated",
    "severity",
]


def test_no_leakage_features():
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    assert not set(responses.columns) & set(FORBIDDEN_FEATURES)


def test_leakage_is_demonstrable(isolated_pipeline_env):
    """Positive control: proves the guard isn't vacuous by showing what happens when a classifier IS allowed to train on the index."""
    rp = isolated_pipeline_env
    rp.score_all()
    df = pd.read_csv(rp.RESULTS / "pipeline_output_cohort.csv")

    clf = DecisionTreeClassifier()
    clf.fit(df[["theta"]], df["severity"])
    accuracy = clf.score(df[["theta"]], df["severity"])

    assert accuracy > 0.95


def test_rf_model_feature_list_has_no_forbidden_feature():
    model = joblib.load(ROOT / "models" / "phenotype_rf.joblib")
    assert not set(model.feature_names_in_) & set(FORBIDDEN_FEATURES)
