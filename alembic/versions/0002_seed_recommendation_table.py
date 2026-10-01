"""seed recommendation table from rules.evaluate() over all 9 band x phenotype cells

Revision ID: 0002_seed_recommendation_table
Revises: 0001_initial_schema
Create Date: 2026-09-19
"""
from __future__ import annotations

import itertools
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0002_seed_recommendation_table"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

recommendation_table = sa.table(
    "recommendation",
    sa.column("rec_id", sa.Uuid),
    sa.column("severity_level", sa.String),
    sa.column("phenotype", sa.String),
    sa.column("rule_id", sa.String),
    sa.column("recommendation_text", sa.Text),
    sa.column("evidence", sa.Text),
    sa.column("source", sa.String),
    sa.column("seeded_at", sa.DateTime(timezone=True)),
)


def _source_label(evidence: str) -> str:
    has_msd = "MSD" in evidence
    has_aaha = "AAHA" in evidence
    if has_msd and has_aaha:
        return "MSD+AAHA"
    if has_aaha:
        return "AAHA"
    return "MSD"


def upgrade() -> None:
    import rules  # rules.py is never modified by this migration, only read

    now = datetime.now(timezone.utc)
    rows = []
    for band, phenotype in itertools.product(rules.SEVERITY_BANDS, rules.PHENOTYPE_LABELS):
        rec = rules.evaluate(
            band, phenotype, flag_irt=False, flag_rf=False, theta_se=0.0, rf_confidence=1.0
        )
        rows.append({
            "rec_id": uuid.uuid4(),
            "severity_level": band,
            "phenotype": phenotype,
            "rule_id": rec.rule_id,
            "recommendation_text": rec.action,
            "evidence": rec.evidence,
            "source": _source_label(rec.evidence),
            "seeded_at": now,
        })

    op.bulk_insert(recommendation_table, rows)


def downgrade() -> None:
    op.execute(recommendation_table.delete())
