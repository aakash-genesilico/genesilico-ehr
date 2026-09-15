"""What a casebook is still missing — computed now, not frozen at import.

`routers/ontada.py` used to stamp `gaps-pending` or `ai-ready` once, at import,
and nothing ever revisited it. So a casebook whose gaps had since been filled
went on advertising "Gaps pending" for ever, and — worse for trust — one that
lost a value later went on claiming to be ready. The status is a fact about the
record's current contents, so it is derived from them.

Scope is deliberately the same as the import check, minus one field:
`plan_number` is mapped out of the Coverage but has no column on either model,
so a gap on it could never be cleared by anyone and would pin every imported
casebook to "Gaps pending" permanently.
"""
from __future__ import annotations

from .. import db

# Filled from the FHIR Patient and Condition, or typed by a person afterwards.
CASEBOOK_FIELDS: tuple[tuple[str, str], ...] = (
    ("patient_name", "patient name"),
    ("mrn", "MRN"),
    ("birth_date", "date of birth"),
    ("gender", "gender"),
    ("primary_diagnosis", "primary diagnosis"),
    ("diagnosis_code", "ICD-10 code"),
    ("stage", "stage"),
    ("oncologist", "oncologist"),
)

# Read off the Coverage and carried on the pre-auth package. A payer rejects a
# 270 outright when these are wrong, so a blank one is a real blocker.
COVERAGE_FIELDS: tuple[tuple[str, str], ...] = (
    ("payer_name", "payer"),
    ("member_id", "member ID"),
    ("group_number", "group number"),
)


def missing(cb: db.Casebook, pkg: db.PreAuthPackage | None = None) -> list[str]:
    """Human-readable names of the fields still empty, in a fixed order."""
    out = [label for attr, label in CASEBOOK_FIELDS if not (getattr(cb, attr, "") or "").strip()]
    if pkg is not None:
        out += [label for attr, label in COVERAGE_FIELDS
                if not (getattr(pkg, attr, "") or "").strip()]
    return out


def status_for(cb: db.Casebook, pkg: db.PreAuthPackage | None = None) -> str:
    """The casebook's status as its contents justify right now.

    A casebook with no chart behind it keeps whatever it was given — there is
    nothing to be complete against. Anything a person set deliberately and that
    sits beyond the import's own pair is left alone, so a later workflow state
    is never overwritten by this.
    """
    if not cb.ontada_fhir_id:
        return cb.status or "draft"
    if cb.status not in ("", None, "gaps-pending", "ai-ready", "ingesting"):
        return cb.status
    return "gaps-pending" if missing(cb, pkg) else "ai-ready"
