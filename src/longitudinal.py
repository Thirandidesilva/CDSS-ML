"""Tracks per-item and theta changes across two submissions to flag real vs. noise-level change."""
from __future__ import annotations

SENTINEL_ITEMS = ["Q8", "Q5", "Q4", "Q12", "Q13", "Q6"]


def track_sentinel_items(before: dict, after: dict) -> dict:
    # TODO: per-item category change on SENTINEL_ITEMS between two submissions
    raise NotImplementedError


def track_theta_change(theta_before: float, theta_after: float,
                        se_before: float, se_after: float) -> dict:
    # TODO: delegate to rules.detectable_change() once rules.py is implemented
    raise NotImplementedError
