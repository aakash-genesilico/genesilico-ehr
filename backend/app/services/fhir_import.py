"""Map a FHIR R4 bundle onto casebook fields.

Deliberately conservative. A field the bundle does not carry stays empty — an
absent diagnosis must remain visibly absent, because a casebook that looks
complete but is not is worse than one that is honestly blank.

Written against the R4 spec, and since 2026-09-13 exercised against a REAL
Ontada payload (the (g)(10) certification patient, see docs/ONTADA-FINDINGS.md).
That first real run corrected three things the hand-written test bundles had
not: a contained payor Organization, an SDOH finding outranking the cancer
diagnosis, and an unmapped plan number. `tests/test_fhir_import.py` covers the
mapping shape only.
"""
from __future__ import annotations

from typing import Any

# Condition.clinicalStatus values that mean "this is still the problem".
_ACTIVE = {"active", "recurrence", "relapse"}

# Categories that describe CONTEXT around a patient, not the disease being
# treated. Real Ontada data ranks these identically to a diagnosis otherwise:
# the certification patient carries "Food insecurity" (sdoh, Z59.41, recorded
# 2025) alongside "Primary malignant neoplasm of colon" (C18.2, recorded 2022),
# both active and both problem-list-item — so a plain recency sort picks the
# food insecurity as the primary diagnosis. For a prior-auth package that is
# not a near miss, it is the wrong code on the form.
_CONTEXT_CATEGORIES = {"sdoh", "health-concern", "social-history"}

# ICD-10 Z-codes are "factors influencing health status", never the condition
# being authorised. Kept separate from the category check because a payload can
# carry the Z-code without categorising it.
def _is_context_code(code: str) -> bool:
    return code.upper().startswith("Z")
# The BASE icd-10 URI, not icd-10-cm. _code_from matches by prefix, so this one
# constant covers both `.../sid/icd-10` and `.../sid/icd-10-cm`. Ontada emits the
# former; the old icd-10-cm constant matched neither of Ontada's codings, so every
# ICD-10 lookup silently returned "" and the mapper fell back to SNOMED — putting
# a SNOMED code where the pre-auth form needs ICD-10. Measured 2026-09-13.
ICD10 = "http://hl7.org/fhir/sid/icd-10"
SNOMED = "http://snomed.info/sct"


def _codings(cc: dict | None) -> list[dict]:
    return (cc or {}).get("coding") or []


def _text(cc: dict | None) -> str:
    cc = cc or {}
    if cc.get("text"):
        return cc["text"]
    for c in _codings(cc):
        if c.get("display"):
            return c["display"]
    return ""


def _code_from(cc: dict | None, system: str) -> str:
    for c in _codings(cc):
        if (c.get("system") or "").startswith(system):
            return c.get("code") or ""
    return ""


def patient_fields(patient: dict) -> dict:
    """Demographics from a FHIR Patient."""
    name = (patient.get("name") or [{}])[0]
    given = " ".join(name.get("given") or []).strip()
    family = (name.get("family") or "").strip()

    mrn = ""
    for ident in patient.get("identifier") or []:
        code = next((c.get("code") for c in _codings(ident.get("type"))), None)
        if code == "MR":
            mrn = ident.get("value") or ""
            break
    if not mrn and patient.get("identifier"):
        mrn = patient["identifier"][0].get("value") or ""

    return {
        "patient_name": " ".join(p for p in (given, family) if p),
        "mrn": mrn,
        "birth_date": patient.get("birthDate") or "",
        "gender": patient.get("gender") or "",
        "ontada_fhir_id": f"Patient/{patient['id']}" if patient.get("id") else None,
    }


def primary_condition(conditions: list[dict]) -> dict:
    """Best candidate for the primary diagnosis.

    Prefers an active, encounter-diagnosis-ranked condition carrying an ICD-10
    code. Returns blanks rather than picking arbitrarily when nothing qualifies.
    """
    def score(c: dict) -> tuple:
        status = next((x.get("code") for x in _codings(c.get("clinicalStatus"))), "")
        cats = {x.get("code") for cat in (c.get("category") or []) for x in _codings(cat)}
        icd = _code_from(c.get("code"), ICD10)
        # Context outranked by anything clinical, BEFORE recency is consulted —
        # otherwise a recently-recorded SDOH finding wins on date alone.
        clinical = not (cats & _CONTEXT_CATEGORIES) and not _is_context_code(icd)
        return (
            clinical,
            status in _ACTIVE,
            "encounter-diagnosis" in cats or "problem-list-item" in cats,
            bool(icd),
            c.get("recordedDate") or c.get("onsetDateTime") or "",
        )

    ranked = sorted((c for c in conditions if c.get("code")), key=score, reverse=True)
    if not ranked:
        return {"primary_diagnosis": "", "diagnosis_code": "", "stage": ""}

    top = ranked[0]
    stage = ""
    for st in top.get("stage") or []:
        stage = _text(st.get("summary")) or stage

    return {
        "primary_diagnosis": _text(top.get("code")),
        "diagnosis_code": _code_from(top.get("code"), ICD10) or _code_from(top.get("code"), SNOMED),
        "stage": stage,
    }


def coverage_fields(coverages: list[dict], contained: dict[str, dict] | None = None) -> dict:
    """Payer, member ID and group — the fields the 270 matches on.

    This is the highest-value thing in the bundle: today they are typed by hand
    and a typo comes back as an AAA rejection from the payer.
    """
    contained = dict(contained or {})
    active = [c for c in coverages if (c.get("status") or "active") == "active"] or coverages
    if not active:
        return {"payer_name": "", "member_id": "", "member_id_alternates": [],
                "group_number": "", "plan_number": ""}

    cov = active[0]

    # Real Ontada Coverage carries the payor as a CONTAINED Organization
    # (`payor: [{reference: "#payor-org"}]` with the Organization inside the
    # Coverage itself), not as a separate resource with a display name. Merge
    # the resource's own `contained` in, or payer_name silently stays empty —
    # which is what happened on the first real payload.
    for r in cov.get("contained") or []:
        if r.get("id"):
            contained.setdefault(r["id"], r)

    # FHIR offers two member identifiers and payers differ on which they match.
    # subscriberId is the canonical "insurer assigned ID for the subscriber";
    # an identifier typed MB is the Member Number. We lead with subscriberId
    # and carry the rest as alternates rather than dropping them, so a UI can
    # offer the other one when the payer answers with an AAA rejection.
    member_id = cov.get("subscriberId") or ""
    alternates = [i["value"] for i in (cov.get("identifier") or [])
                  if i.get("value") and i["value"] != member_id]
    if not member_id and alternates:
        member_id, alternates = alternates[0], alternates[1:]

    payer_name = ""
    for payor in cov.get("payor") or []:
        payer_name = payor.get("display") or ""
        ref = (payor.get("reference") or "").lstrip("#")
        if not payer_name and ref in contained:
            payer_name = contained[ref].get("name") or ""
        if payer_name:
            break

    group = plan = ""
    for cls in cov.get("class") or []:
        kind = next((c.get("code") for c in _codings(cls.get("type"))), "")
        if kind == "group" and not group:
            group = cls.get("value") or ""
        elif kind == "plan" and not plan:
            plan = cls.get("value") or ""

    return {"payer_name": payer_name, "member_id": member_id,
            "member_id_alternates": alternates,
            "group_number": group, "plan_number": plan}


def practitioner_name(care_teams: list[dict], encounters: list[dict]) -> str:
    for ct in care_teams:
        for part in ct.get("participant") or []:
            display = (part.get("member") or {}).get("display")
            if display:
                return display
    for enc in encounters:
        for part in enc.get("participant") or []:
            display = (part.get("individual") or {}).get("display")
            if display:
                return display
    return ""


def to_casebook(resources: dict[str, list[dict]]) -> dict:
    """Whole-bundle -> casebook payload, plus the coverage the pre-auth needs."""
    patients = resources.get("Patient") or []
    if not patients:
        raise ValueError("Bundle carries no Patient resource")

    contained = {
        r["id"]: r
        for r in (resources.get("Organization") or [])
        if r.get("id")
    }

    fields = patient_fields(patients[0])
    fields.update(primary_condition(resources.get("Condition") or []))
    fields["oncologist"] = practitioner_name(
        resources.get("CareTeam") or [], resources.get("Encounter") or []
    )
    coverage = coverage_fields(resources.get("Coverage") or [], contained)

    return {
        "casebook": fields,
        "coverage": coverage,
        "counts": {k: len(v) for k, v in resources.items()},
        # Which target fields the bundle could not fill. The UI shows these as
        # gaps rather than letting a blank pass for a value.
        # `member_id_alternates` is legitimately empty when the payload carries
        # one identifier, so it is not a gap.
        "unmapped": [k for k, v in {**fields, **coverage}.items()
                     if not v and k not in ("ontada_fhir_id", "member_id_alternates")],
    }
