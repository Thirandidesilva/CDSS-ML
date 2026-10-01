"""Loads the raw survey export into responses.csv (Q4-Q15, ints 0-4) and demographics.csv."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

LIKERT = {"Never": 0, "Rarely": 1, "Sometimes": 2, "Often": 3, "Always": 4}
ITEMS_ALL = [f"Q{i}" for i in range(4, 16)]


def load_responses() -> pd.DataFrame:
    export = pd.read_excel(RAW / "survey_export.xlsx")
    mapping = pd.read_csv(RAW / "item_mapping.csv").set_index("item")

    out = pd.DataFrame({"ID": export["ID"]})
    for q in ITEMS_ALL:
        col = mapping.loc[q, "export_column_header"]
        matches = [c for c in export.columns if c.strip() == col]
        if len(matches) != 1:
            raise KeyError(f"{q}: expected exactly one export column matching {col!r}, found {matches}")
        raw = export[matches[0]]
        if raw.isna().any():
            raise ValueError(f"{q}: missing values in export column {col!r}")
        coded = raw.map(LIKERT)
        if coded.isna().any():
            bad = sorted(set(raw[coded.isna()]))
            raise ValueError(f"{q}: unrecognised response values {bad}")
        out[q] = coded.astype(int)

    if len(out) != 163:
        raise ValueError(f"expected 163 rows, got {len(out)}")
    if out["ID"].duplicated().any():
        raise ValueError("duplicate IDs in export")
    if out[ITEMS_ALL].isna().any().any():
        raise ValueError("nulls in coded responses")
    if (out[ITEMS_ALL].min().min() < 0) or (out[ITEMS_ALL].max().max() > 4):
        raise ValueError("coded responses outside 0-4")

    return out


def load_demographics() -> pd.DataFrame:
    export = pd.read_excel(RAW / "survey_export.xlsx")
    demo_cols = [c for c in export.columns[1:4]]
    demo = export[["ID"] + demo_cols].copy()
    demo.columns = ["ID", "breed", "age", "gender"]
    return demo


if __name__ == "__main__":
    responses = load_responses()
    responses.to_csv(RAW / "responses.csv", index=False)
    print(f"wrote {RAW / 'responses.csv'} shape {responses.shape}")

    demographics = load_demographics()
    demographics.to_csv(RAW / "demographics.csv", index=False)
    print(f"wrote {RAW / 'demographics.csv'} shape {demographics.shape}")
