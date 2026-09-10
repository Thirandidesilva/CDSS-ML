import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import run_pipeline  # noqa: E402


@pytest.fixture
def isolated_pipeline_env(tmp_path, monkeypatch):
    """Copies real reference/results artifacts into tmp_path and points run_pipeline
    at them, so tests never read/write the real (git-tracked) data/reference or results.
    """
    ref = tmp_path / "reference"
    results = tmp_path / "results"
    models = tmp_path / "models"
    ref.mkdir()
    results.mkdir()
    models.mkdir()

    shutil.copy(ROOT / "data" / "reference" / "params_own.csv", ref / "params_own.csv")
    shutil.copy(ROOT / "results" / "scored_responses.csv", results / "scored_responses.csv")
    shutil.copy(ROOT / "results" / "phenotype_profiles.csv", results / "phenotype_profiles.csv")
    shutil.copy(ROOT / "models" / "phenotype_rf.joblib", models / "phenotype_rf.joblib")
    shutil.copy(ROOT / "models" / "phenotype_rf_metadata.json", models / "phenotype_rf_metadata.json")

    monkeypatch.setattr(run_pipeline, "REF", ref)
    monkeypatch.setattr(run_pipeline, "RESULTS", results)
    monkeypatch.setattr(run_pipeline, "MODELS", models)
    return run_pipeline
