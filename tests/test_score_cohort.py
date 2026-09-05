import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import score_cohort  # noqa: E402


def test_score_cohort_shape_and_validity():
    scored = score_cohort.score_cohort()
    assert scored.shape == (163, 15)
    assert (scored.theta_se > 0).all()
    assert not scored.isnull().values.any()
