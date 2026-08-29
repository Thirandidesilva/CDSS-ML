"""Scores severity theta from item responses under a fixed graded response model."""
from __future__ import annotations

import numpy as np
import pandas as pd

ITEMS_ALL = [f"Q{i}" for i in range(4, 16)]
ITEMS_CALIBRATED = [q for q in ITEMS_ALL if q != "Q11"]
N_CATEGORIES = 5


def load_params(path) -> tuple[list[str], np.ndarray, np.ndarray]:
    p = pd.read_csv(path)
    if "item" not in p.columns:
        p = p.rename(columns={p.columns[0]: "item"})
    p = p.set_index("item")
    items = list(p.index)
    a = p["discrimination_a"].to_numpy(float)
    b = p[["b1", "b2", "b3", "b4"]].to_numpy(float)
    if np.any(np.diff(b, axis=1) < 0):
        bad = [items[i] for i in np.where((np.diff(b, axis=1) < 0).any(axis=1))[0]]
        raise ValueError(f"non-monotone thresholds for {bad}; refusing to score")
    if np.any(a <= 0):
        raise ValueError("non-positive discrimination; refusing to score")
    return items, a, b


def category_probs(a_j: float, b_j: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """P(Y=k|theta) for one item, k=0..4. Returns shape (5, n_theta)."""
    z = a_j * (theta[None, :] - b_j[:, None])
    upper = 1.0 / (1.0 + np.exp(-z))
    top = np.ones((1, theta.size))
    bot = np.zeros((1, theta.size))
    probs = np.vstack([top, upper]) - np.vstack([upper, bot])
    return np.clip(probs, 1e-12, 1.0)


def grm_eap(
    responses: pd.DataFrame,
    items: list[str],
    a: np.ndarray,
    b: np.ndarray,
    n_quad: int = 61,
    span: float = 4.0,
) -> pd.DataFrame:
    missing = [q for q in items if q not in responses.columns]
    if missing:
        raise KeyError(f"missing item columns: {missing}")
    X = responses[items].to_numpy()
    if np.isnan(X).any():
        raise ValueError("NaN in responses; impute or drop before scoring")
    X = X.astype(int)
    if X.min() < 0 or X.max() > N_CATEGORIES - 1:
        raise ValueError(f"responses must be 0..{N_CATEGORIES - 1}")

    theta = np.linspace(-span, span, n_quad)
    prior = np.exp(-0.5 * theta ** 2)
    prior /= prior.sum()

    loglik = np.zeros((X.shape[0], n_quad))
    for j in range(len(items)):
        probs = category_probs(a[j], b[j], theta)
        loglik += np.log(probs[X[:, j], :])

    post = np.exp(loglik) * prior
    post /= post.sum(axis=1, keepdims=True)
    eap = post @ theta
    var = post @ (theta ** 2) - eap ** 2
    return pd.DataFrame(
        {"theta": eap, "theta_se": np.sqrt(np.clip(var, 0, None))},
        index=responses.index,
    )


def marginal_reliability(
    theta_se: np.ndarray,
    theta: np.ndarray | None = None,
    *,
    denominator: str = "observed",
) -> float:
    """1 - mean(SE^2) / variance. denominator: "observed" (var of theta_hat) or "prior" (=1)."""
    se2 = float(np.mean(np.asarray(theta_se) ** 2))
    if denominator == "prior":
        return float(1.0 - se2)
    if denominator != "observed":
        raise ValueError("denominator must be 'observed' or 'prior'")
    if theta is None:
        raise ValueError("denominator='observed' requires the theta estimates")
    return float(1.0 - se2 / np.var(np.asarray(theta), ddof=1))


def test_information(a: np.ndarray, b: np.ndarray, theta: np.ndarray) -> np.ndarray:
    info = np.zeros_like(theta, dtype=float)
    for j in range(len(a)):
        probs = category_probs(a[j], b[j], theta)
        k = np.arange(N_CATEGORIES)[:, None]
        ek = (probs * k).sum(axis=0)
        ek2 = (probs * k ** 2).sum(axis=0)
        info += (a[j] ** 2) * (ek2 - ek ** 2)
    return info
