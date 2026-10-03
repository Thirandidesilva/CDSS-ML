"""Detects which evidence sources a recommendation's text actually cites, so the PDF
only shows a "Source: ..." pill for citations that are really there — never both by
default. Generalizes the same substring-check idea already used once, ad hoc, in
alembic/versions/0002_seed_recommendation_table.py's _source_label() — but that file is
a migration and must never be imported by application code, so this is its own home.
"""
from __future__ import annotations

_LABELS = {"MSD": "MSD Veterinary Manual", "AAHA": "AAHA Behaviour Management Guidelines"}


def detect_sources(*texts: str) -> list[str]:
    """Returns display labels (e.g. "MSD Veterinary Manual") for each citation actually
    present across all given texts, in fixed MSD-then-AAHA order."""
    combined = " ".join(texts)
    return [label for code, label in _LABELS.items() if code in combined]
