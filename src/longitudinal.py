"""Tracks per-item and theta changes across two submissions to flag real vs. noise-level change."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import rules        # noqa: E402
import run_pipeline  # noqa: E402

SENTINEL_ITEMS = ["Q8", "Q5", "Q4", "Q12", "Q13", "Q6"]


def track_sentinel_items(before: dict, after: dict) -> dict:
    """Tier 1: per-item category change (before -> after) on each sentinel item."""
    b = run_pipeline.encode(before).iloc[0]
    a = run_pipeline.encode(after).iloc[0]
    changes = {}
    for q in SENTINEL_ITEMS:
        delta = int(a[q]) - int(b[q])
        changes[q] = {"before": int(b[q]), "after": int(a[q]), "delta": delta, "changed": delta != 0}
    return changes


def track_theta_change(theta_before: float, theta_after: float,
                        se_before: float, se_after: float) -> dict:
    """Tiers 2-3: theta delta against MDC95, delegated to rules.detectable_change()."""
    return rules.detectable_change(theta_before, theta_after, se_before, se_after)
