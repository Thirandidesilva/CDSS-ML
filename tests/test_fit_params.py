import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import fit_params  # noqa: E402

RESPONSES = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")


def test_fit_grm_params_discrimination_positive():
    params = fit_params.fit_grm_params(RESPONSES)
    assert (params.discrimination_a > 0).all()


def test_fit_grm_params_thresholds_monotone():
    params = fit_params.fit_grm_params(RESPONSES)
    b = params[["b1", "b2", "b3", "b4"]].to_numpy()
    assert (np.diff(b, axis=1) >= 0).all()


def test_check_stability_is_tight():
    _, _, ll_spread, a_spread = fit_params.check_stability(RESPONSES, n_restarts=3, seed=0)
    assert ll_spread < 0.01
    assert max(a_spread.values()) < 0.01
