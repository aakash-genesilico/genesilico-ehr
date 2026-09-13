"""Shape tests for the FHIR -> casebook mapper.

These bundles are hand-written to the FHIR R4 spec to exercise the mapping
logic. They are NOT Ontada data and make no claim about what Ontada returns —
no token has been issued for this app yet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import fhir_import as fi  # noqa: E402

ICD10 = "http://hl7.org/fhir/sid/icd-10-cm"


def _patient():
    return {
        "resourceType": "Patient", "id": "abc-123",
        "name": [{"given": ["Aakash"], "family": "Sample"}],
        "birthDate": "1966-09-25", "gender": "female",
        "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "TXO-99001"}],
    }


def test_patient_fields():
    f = fi.patient_fields(_patient())
    assert f["patient_name"] == "Aakash Sample"
    assert f["mrn"] == "TXO-99001"
    assert f["ontada_fhir_id"] == "Patient/abc-123"


def test_primary_condition_prefers_active_icd10():
    conds = [
        {"code": {"text": "Resolved thing", "coding": [{"system": ICD10, "code": "Z00.0"}]},
         "clinicalStatus": {"coding": [{"code": "resolved"}]}},
        {"code": {"text": "Adenocarcinoma of lung", "coding": [{"system": ICD10, "code": "C34.11"}]},
         "clinicalStatus": {"coding": [{"code": "active"}]},
         "category": [{"coding": [{"code": "encounter-diagnosis"}]}],
         "stage": [{"summary": {"text": "IIIB"}}]},
    ]
    c = fi.primary_condition(conds)
    assert c["diagnosis_code"] == "C34.11"
    assert c["stage"] == "IIIB"


def test_primary_condition_blank_when_nothing_usable():
    assert fi.primary_condition([])["primary_diagnosis"] == ""


def test_coverage_fields_resolve_contained_payer():
    cov = [{
        "status": "active", "subscriberId": "771900671646",
        "payor": [{"reference": "#org1"}],
        "class": [{"type": {"coding": [{"code": "group"}]}, "value": "78800317"}],
    }]
    got = fi.coverage_fields(cov, {"org1": {"name": "UnitedHealthcare"}})
    assert got == {"payer_name": "UnitedHealthcare", "member_id": "771900671646",
                   "member_id_alternates": [], "group_number": "78800317",
                   "plan_number": ""}


# --------------------------------------------------------------------------- #
# The four cases below are NOT hypothetical. Each is a defect the hand-written
# bundles above missed and the first real Ontada payload exposed on 2026-09-13
# (the (g)(10) certification patient). They are regression tests, so a future
# refactor cannot quietly reintroduce any of them.
# --------------------------------------------------------------------------- #

def test_payor_contained_inside_the_coverage_itself():
    """Ontada puts the payor Organization in Coverage.contained, not alongside.

    The old mapper only consulted a caller-supplied dict, so payer_name — one of
    the three fields the 270 matches on — came back empty against real data.
    """
    cov = [{
        "status": "active", "subscriberId": "9876543",
        "payor": [{"reference": "#payor-org"}],
        "contained": [{"resourceType": "Organization", "id": "payor-org",
                       "name": "zzAetna"}],
        "class": [{"type": {"coding": [{"code": "plan"}]}, "value": "765432"},
                  {"type": {"coding": [{"code": "group"}]}, "value": "345678"}],
        "identifier": [{"value": "123456"}],
    }]
    got = fi.coverage_fields(cov)
    assert got["payer_name"] == "zzAetna"
    assert got["plan_number"] == "765432"      # was never mapped at all
    assert got["group_number"] == "345678"
    # The second identifier is carried, not dropped — a payer that rejects the
    # subscriberId may match on the member number instead.
    assert got["member_id"] == "9876543"
    assert got["member_id_alternates"] == ["123456"]


def test_sdoh_finding_never_outranks_the_cancer_diagnosis():
    """Recency alone must not promote an SDOH finding to primary diagnosis.

    Real data: food insecurity (active, problem-list-item, recorded 2025) vs
    colon cancer (active, problem-list-item, recorded 2022). Both tied on every
    other term, so the newer one won and the pre-auth carried Z59.41.
    """
    conds = [
        {"code": {"text": "Food insecurity",
                  "coding": [{"system": fi.ICD10, "code": "Z59.41"}]},
         "clinicalStatus": {"coding": [{"code": "active"}]},
         "category": [{"coding": [{"code": "problem-list-item"}, {"code": "sdoh"}]}],
         "recordedDate": "2025-06-18T07:21:06-07:00"},
        {"code": {"text": "Primary cancer of colon",
                  "coding": [{"system": fi.ICD10, "code": "C18.2"}]},
         "clinicalStatus": {"coding": [{"code": "active"}]},
         "category": [{"coding": [{"code": "problem-list-item"},
                                  {"code": "encounter-diagnosis"}]}],
         "recordedDate": "2022-10-14T18:15:57-07:00"},
    ]
    assert fi.primary_condition(conds)["diagnosis_code"] == "C18.2"


def test_health_concern_alone_is_not_a_diagnosis():
    conds = [{"code": {"text": "Concerned"},
              "clinicalStatus": {"coding": [{"code": "active"}]},
              "category": [{"coding": [{"code": "health-concern"}]}]},
             {"code": {"text": "Rectal hemorrhage",
                       "coding": [{"system": fi.ICD10, "code": "K62.5"}]},
              "clinicalStatus": {"coding": [{"code": "active"}]},
              "category": [{"coding": [{"code": "problem-list-item"}]}]}]
    assert fi.primary_condition(conds)["diagnosis_code"] == "K62.5"


def test_icd10_matches_the_base_uri_not_just_icd_10_cm():
    """Ontada emits .../sid/icd-10; the constant used to be .../sid/icd-10-cm.

    Nothing matched, so every diagnosis_code silently fell back to SNOMED — a
    code system the pre-auth form cannot use.
    """
    for system in ("http://hl7.org/fhir/sid/icd-10",
                   "http://hl7.org/fhir/sid/icd-10-cm"):
        cond = [{"code": {"coding": [{"system": "http://snomed.info/sct",
                                      "code": "93761005"},
                                     {"system": system, "code": "C18.2"}]},
                 "clinicalStatus": {"coding": [{"code": "active"}]},
                 "category": [{"coding": [{"code": "problem-list-item"}]}]}]
        assert fi.primary_condition(cond)["diagnosis_code"] == "C18.2", system


def test_to_casebook_reports_unmapped():
    out = fi.to_casebook({"Patient": [_patient()]})
    # No Condition and no Coverage in the bundle, so those must be reported
    # missing rather than silently blank.
    assert "primary_diagnosis" in out["unmapped"]
    assert "member_id" in out["unmapped"]
    assert out["casebook"]["patient_name"] == "Aakash Sample"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}")
        except Exception:
            failed += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
