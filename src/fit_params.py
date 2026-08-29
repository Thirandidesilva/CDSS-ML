"""Fits GRM item parameters (discrimination, thresholds) on cohort responses via marginal ML / EM."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import irt  # noqa: E402

N_QUAD = 61
SPAN = 4.0


def _quadrature() -> tuple[np.ndarray, np.ndarray]:
    theta = np.linspace(-SPAN, SPAN, N_QUAD)
    prior = np.exp(-0.5 * theta ** 2)
    prior /= prior.sum()
    return theta, prior


def _init_params(X: np.ndarray, n_items: int) -> tuple[np.ndarray, np.ndarray]:
    """Thresholds from empirical P(Y>=k) at a=1, theta=0: b_k = logit(1 - p_k)."""
    a = np.ones(n_items)
    b = np.empty((n_items, 4))
    for j in range(n_items):
        for k in range(1, 5):
            p = np.clip(np.mean(X[:, j] >= k), 1e-3, 1 - 1e-3)
            b[j, k - 1] = np.log((1 - p) / p)
        b[j] = np.sort(b[j])
    return a, b


def _unpack(v: np.ndarray) -> tuple[float, np.ndarray]:
    """alpha -> a=exp(alpha) > 0; beta1, deltas -> strictly increasing b1..b4."""
    a = np.exp(v[0])
    b = np.empty(4)
    b[0] = v[1]
    b[1:] = b[0] + np.cumsum(np.exp(v[2:5]))
    return a, b


def _pack(a: float, b: np.ndarray) -> np.ndarray:
    return np.concatenate([[np.log(a), b[0]], np.log(np.diff(b))])


RIDGE_ALPHA = 0.05  # weak prior pulling weak items' discrimination toward 1, not 0


def _neg_expected_ll(v: np.ndarray, r: np.ndarray, theta_grid: np.ndarray) -> float:
    a, b = _unpack(v)
    probs = np.clip(irt.category_probs(a, b, theta_grid), 1e-12, 1.0)
    return -float(np.sum(r * np.log(probs))) + RIDGE_ALPHA * v[0] ** 2


def fit_grm_params(responses: pd.DataFrame, items: list[str] | None = None,
                    max_iter: int = 200, tol: float = 1e-5,
                    init: tuple[np.ndarray, np.ndarray] | None = None,
                    return_ll: bool = False):
    """Marginal maximum likelihood via EM (Bock-Aitkin). E-step: posterior over a fixed
    theta grid given current item parameters. M-step: per-item weighted ordinal
    regression on the expected category counts, reparametrised so a > 0 and
    b1 < b2 < b3 < b4 hold by construction rather than by constraint.
    """
    items = items or irt.ITEMS_ALL
    X = responses[items].to_numpy(int)
    n, J = X.shape
    theta_grid, prior = _quadrature()
    if init is not None:
        a, b = init
        a, b = a.copy(), b.copy()
    else:
        a, b = _init_params(X, J)
    log_prior = np.log(prior)

    prev_ll = -np.inf
    ll = prev_ll
    for _ in range(max_iter):
        loglik = np.zeros((n, N_QUAD))
        for j in range(J):
            probs = np.clip(irt.category_probs(a[j], b[j], theta_grid), 1e-12, 1.0)
            loglik += np.log(probs[X[:, j], :])

        joint = loglik + log_prior[None, :]
        marginal = logsumexp(joint, axis=1)
        ll = float(marginal.sum())
        post = np.exp(joint - marginal[:, None])

        for j in range(J):
            r = np.zeros((irt.N_CATEGORIES, N_QUAD))
            for c in range(irt.N_CATEGORIES):
                mask = X[:, j] == c
                if mask.any():
                    r[c] = post[mask].sum(axis=0)
            v0 = _pack(a[j], b[j])
            bounds = [(np.log(0.05), np.log(10.0)), (-6.0, 6.0),
                      (-3.0, 3.0), (-3.0, 3.0), (-3.0, 3.0)]
            res = minimize(_neg_expected_ll, v0, args=(r, theta_grid),
                            method="L-BFGS-B", bounds=bounds)
            a[j], b[j] = _unpack(res.x)

        if abs(ll - prev_ll) < tol:
            break
        prev_ll = ll

    params = pd.DataFrame({
        "item": items,
        "discrimination_a": a,
        "b1": b[:, 0], "b2": b[:, 1], "b3": b[:, 2], "b4": b[:, 3],
    })
    return (params, ll) if return_ll else params


def check_stability(responses: pd.DataFrame, items: list[str] | None = None,
                     n_restarts: int = 10, seed: int = 0):
    """Reruns EM from n_restarts random perturbations of the initial guess.
    Agreement across restarts (log-likelihood and per-item discrimination) is the
    evidence the fit is a real optimum, not an artifact of one starting point.
    Returns (best_params, best_ll, ll_spread, a_spread_per_item).
    """
    items = items or irt.ITEMS_ALL
    X = responses[items].to_numpy(int)
    n, J = X.shape
    a0, b0 = _init_params(X, J)

    rng = np.random.default_rng(seed)
    runs = [fit_grm_params(responses, items, init=(a0, b0), return_ll=True)]
    for _ in range(n_restarts):
        a_start = a0 * np.exp(rng.normal(0, 0.3, size=J))
        b_start = np.sort(b0 + rng.normal(0, 0.5, size=b0.shape), axis=1)
        runs.append(fit_grm_params(responses, items, init=(a_start, b_start), return_ll=True))

    lls = np.array([ll for _, ll in runs])
    a_mat = np.array([p["discrimination_a"].to_numpy() for p, _ in runs])

    best_idx = int(np.argmax(lls))
    ll_spread = float(lls.max() - lls.min())
    a_spread = a_mat.max(axis=0) - a_mat.min(axis=0)

    print(f"stability check: {n_restarts + 1} starts (1 deterministic + {n_restarts} random)")
    print(f"  log-likelihood: min {lls.min():.3f}  max {lls.max():.3f}  spread {ll_spread:.4f}")
    print(f"  best start: {'deterministic' if best_idx == 0 else f'random restart {best_idx}'}")
    print("  discrimination spread per item (max-min across all starts):")
    for j, q in enumerate(items):
        print(f"    {q}: {a_spread[j]:.4f}")

    return runs[best_idx][0], lls[best_idx], ll_spread, dict(zip(items, a_spread))


if __name__ == "__main__":
    responses = pd.read_csv(ROOT / "data" / "raw" / "responses.csv")
    best_params, best_ll, ll_spread, a_spread = check_stability(responses, n_restarts=10, seed=0)

    dest = ROOT / "data" / "reference" / "params_own.csv"
    best_params.to_csv(dest, index=False)
    print(f"\nwrote {dest} (log-likelihood {best_ll:.3f})")
    print(best_params.sort_values("discrimination_a").to_string(index=False))
