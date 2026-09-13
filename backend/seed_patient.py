"""Seed the one real patient we have verified payer data for.

Shaheen Farooq is a real Texas Oncology patient. Her demographics and coverage
below are not invented — every field is read out of the production 271 stored
at data/271-shaheen-farooq.json, which was returned by UnitedHealthcare through
Stedi. Clinical fields the 271 does not carry (diagnosis, stage, oncologist)
are left blank rather than filled in with a plausible guess.
"""
import asyncio
import json
from pathlib import Path

from app import db
from app.services import benefits

RESPONSE = Path(__file__).parent / "data" / "271-shaheen-farooq.json"


async def main() -> None:
    await db.init_db()
    parsed = benefits.parse(json.loads(RESPONSE.read_text()))
    m = parsed["member"]
    dob = m["date_of_birth"] or ""
    iso_dob = f"{dob[:4]}-{dob[4:6]}-{dob[6:8]}" if len(dob) == 8 else ""

    async with db.SessionLocal() as s:
        cb = await s.get(db.Casebook, "cb-farooq-shaheen")
        if cb is None:
            cb = db.Casebook(id="cb-farooq-shaheen")
            s.add(cb)
        cb.patient_name = f"{m['first_name']} {m['last_name']}".title()
        cb.mrn = m["member_id"] or ""
        cb.birth_date = iso_dob
        cb.gender = {"F": "female", "M": "male"}.get(m["gender"] or "", "")
        cb.cancer_center_id = "cc-txo-austin"
        cb.hospital_id = "hosp-st-davids"
        cb.status = "draft"
        # No Ontada binding: this patient's record has not been pulled from the
        # EHR. Coverage is real; the clinical record is not here yet.
        cb.ontada_fhir_id = None
        cb.fhir_snapshot = {}

        pkg = await s.get(db.PreAuthPackage, "pa-farooq-001")
        if pkg is None:
            pkg = db.PreAuthPackage(id="pa-farooq-001")
            s.add(pkg)
        pkg.casebook_id = cb.id
        pkg.patient_name = cb.patient_name
        pkg.mrn = cb.mrn
        pkg.regimen = ""
        pkg.payer_name = parsed["payer"]["name"] or ""
        pkg.payer_id = parsed["payer"]["id"] or ""
        pkg.member_id = m["member_id"] or ""
        pkg.group_number = m["group_number"] or ""
        pkg.hospital_id = "hosp-st-davids"
        pkg.status = "drafting"
        pkg.lines = pkg.lines or []
        pkg.evidence = []
        pkg.eligibility = {"raw_271": json.loads(RESPONSE.read_text()),
                           "source": {"kind": "stored", "file": RESPONSE.name}}
        pkg.events = [{
            "id": "seed", "at": db.utcnow().isoformat(), "actor": "Stedi",
            "action": "Production 271 received from UnitedHealthcare",
            "kind": "success",
            "detail": f"{parsed['entry_count']} benefit entries · trace {parsed['trace_id']}",
        }]
        await s.commit()

    print(f"seeded patient {cb.patient_name} ({cb.mrn}) + package pa-farooq-001")
    print(f"  plan   : {parsed['plan']['name']}")
    print(f"  active : {parsed['active']} | tiers: {len(parsed['drug_tiers'])}")


if __name__ == "__main__":
    asyncio.run(main())
