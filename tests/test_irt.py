import importlib.util
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import irt  # noqa: E402


def _load_reference_irt():
    path = ROOT / ".claude" / "docs" / "irt_reference.py"
    spec = importlib.util.spec_from_file_location("irt_reference", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_grm_reproduces_archive():
    items, a, b = irt.load_params(ROOT / "data" / "reference" / "params_own.csv")
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    est = irt.grm_eap(responses[items], items, a, b)

    archive = pd.read_csv(ROOT / "results" / "scored_responses.csv").set_index("ID")
    est.index = responses["ID"]

    r = np.corrcoef(est.theta, archive.loc[est.index, "theta_irt"])[0, 1]
    maxdiff = float((est.theta - archive.loc[est.index, "theta_irt"]).abs().max())

    assert r > 0.999999
    assert maxdiff < 0.001


def test_irt_matches_archived_reference_implementation():
    """Regression guard: src/irt.py was rewritten referencing the archived copy; confirm no drift."""
    ref = _load_reference_irt()
    items, a, b = irt.load_params(ROOT / "data" / "reference" / "params_own.csv")
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")

    est = irt.grm_eap(responses[items], items, a, b)
    ref_est = ref.grm_eap(responses[items], items, a, b)

    assert np.allclose(est.theta, ref_est.theta, atol=1e-9)
    assert np.allclose(est.theta_se, ref_est.theta_se, atol=1e-9)


def test_calibrated_item_count():
    assert len(irt.ITEMS_CALIBRATED) == 10
    assert "Q11" not in irt.ITEMS_CALIBRATED
    assert "Q14" not in irt.ITEMS_CALIBRATED


def test_load_params_raises_on_non_monotone_thresholds():
    csv = io.StringIO(
        "item,discrimination_a,b1,b2,b3,b4\n"
        "Q4,1.0,0.5,0.2,1.0,2.0\n"
    )
    with pytest.raises(ValueError):
        irt.load_params(csv)


def test_load_params_raises_on_non_positive_discrimination():
    csv = io.StringIO(
        "item,discrimination_a,b1,b2,b3,b4\n"
        "Q4,0.0,-1.0,0.0,1.0,2.0\n"
    )
    with pytest.raises(ValueError):
        irt.load_params(csv)


def test_category_probs_sums_to_one():
    theta = np.linspace(-4, 4, 61)
    probs = irt.category_probs(1.5, np.array([-1.0, -0.2, 0.5, 1.5]), theta)
    assert np.allclose(probs.sum(axis=0), 1.0, atol=1e-9)
