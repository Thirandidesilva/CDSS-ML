import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import irt      # noqa: E402
import rules    # noqa: E402

RESPONSES = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
THREE_DOGS = RESPONSES.iloc[[0, 81, 162]]


def test_score_case_on_three_real_dogs(isolated_pipeline_env):
    rp = isolated_pipeline_env
    model = rp.load_scoring_model()
    for _, row in THREE_DOGS.iterrows():
        answers = {q: int(row[q]) for q in irt.ITEMS_ALL}
        r = rp.score_case(answers, model, verbose=False)

        assert isinstance(r["theta"], float)
        assert isinstance(r["theta_se"], float) and r["theta_se"] > 0
        assert r["severity"] in rules.SEVERITY_BANDS
        assert r["phenotype"] in rules.PHENOTYPE_LABELS
        assert 0.0 <= r["rf_confidence"] <= 1.0
        assert isinstance(r["flag_irt"], bool)
        assert isinstance(r["flag_rf"], bool)

        rec = r["recommendation"]
        assert set(rec.keys()) == {
            "rule_id", "urgency", "action", "evidence",
            "withheld", "withheld_reason", "caveats",
        }
        json.dumps(rec)


def test_demo_runs_without_raising(isolated_pipeline_env, capsys):
    isolated_pipeline_env.demo()
    out = capsys.readouterr().out
    assert "scoring model" in out


def test_score_all_runs_and_writes_output(isolated_pipeline_env):
    rp = isolated_pipeline_env
    rp.score_all()
    dest = rp.RESULTS / "pipeline_output_cohort.csv"
    assert dest.exists()
    df = pd.read_csv(dest)
    assert len(df) == 163
    assert set(df.columns) == {
        "ID", "theta", "theta_se", "severity", "phenotype", "rf_confidence",
        "flag_irt", "flag_rf", "rule_id", "withheld", "urgency",
    }
