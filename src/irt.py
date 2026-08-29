"""Scores severity theta from item responses under a fixed graded response model."""
from __future__ import annotations

ITEMS_ALL = [f"Q{i}" for i in range(4, 16)]
ITEMS_CALIBRATED = [q for q in ITEMS_ALL if q != "Q11"]
N_CATEGORIES = 5


def load_params(path):
    # TODO: read item, discrimination_a, b1..b4 columns; reject non-monotone thresholds
    raise NotImplementedError


def category_probs(a_j, b_j, theta):
    # TODO: Samejima boundary-curve differences, P(Y=k|theta) for k=0..4
    raise NotImplementedError


def grm_eap(responses, items, a, b, n_quad=61, span=4.0):
    # TODO: EAP theta + posterior SD over a fixed quadrature grid, N(0,1) prior
    raise NotImplementedError


def marginal_reliability(theta_se, theta=None, *, denominator="observed"):
    # TODO: 1 - mean(SE^2) / var, denominator "observed" or "prior", never guess which
    raise NotImplementedError


def test_information(a, b, theta):
    # TODO: Fisher information of the whole test at each theta
    raise NotImplementedError
