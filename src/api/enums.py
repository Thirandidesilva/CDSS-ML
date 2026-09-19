"""Shared enums/constants — the single source of truth for values reused across models.py, schemas/, and routers/."""
from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import rules  # noqa: E402


# str + Enum: members behave like plain strings (== "owner" works) but are still
# type-checked/autocompletable, and JSON-serialise as their .value automatically.
class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"  # soft delete — the row stays, this just marks it gone


class DogStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class AssessmentStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class DogGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class ReportStatus(str, Enum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class OtpPurpose(str, Enum):
    FORGET_USERNAME = "forget_username"
    FORGET_PASSWORD = "forget_password"


# Not redeclared: these wrap rules.py's own constants directly, so the DB's valid-value
# set can never drift from the rule engine's.
# Enum(name, {MEMBER_NAME: value, ...}, type=str) is the "functional" way to build an
# Enum class from data instead of writing out each member by hand — same result as the
# classes above, just generated from rules.SEVERITY_BANDS/PHENOTYPE_LABELS at import time.
SeverityBand = Enum("SeverityBand", {b.upper(): b for b in rules.SEVERITY_BANDS}, type=str)
Phenotype = Enum("Phenotype", {p.upper().replace("-", "_"): p for p in rules.PHENOTYPE_LABELS}, type=str)
