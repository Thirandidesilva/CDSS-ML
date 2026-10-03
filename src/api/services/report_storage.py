"""Owns the on-disk path convention for rendered vet-report PDFs. Filesystem, not the
DB, per the storage-location decision — Report.filepath just records where to find it.
"""
from __future__ import annotations

import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def reports_dir() -> Path:
    from ..config import get_settings

    path = ROOT / get_settings().reports_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_pdf_path(report_id: uuid.UUID) -> Path:
    return reports_dir() / f"{report_id}.pdf"


def save_report_pdf(report_id: uuid.UUID, pdf_bytes: bytes) -> str:
    path = report_pdf_path(report_id)
    path.write_bytes(pdf_bytes)
    return str(path)
