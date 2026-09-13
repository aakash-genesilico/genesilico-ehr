"""Seed the tenant reference data.

These are organisational facts about Texas Oncology and its facilities — the
same thing an administrator would type into the Admin Console on day one. No
clinical or financial data is seeded: patients arrive from Ontada, packages are
built by users, and coverage figures come from the payer.
"""
import asyncio

from app import db

CENTERS = [
    dict(id="cc-txo-austin", name="Texas Oncology — Austin", city="Austin", state="TX",
         organization_id="Organization/txo-austin-001", ehr_vendor="ontada-ikm", status="active"),
]

HOSPITALS = [
    dict(id="hosp-st-davids", name="St. David's Medical Center", cancer_center_id="cc-txo-austin",
         city="Austin", state="TX", npi="1467892034", beds=435, type="hospital", status="active"),
    dict(id="hosp-txo-austin-infusion", name="Texas Oncology Austin Infusion Suite",
         cancer_center_id="cc-txo-austin", city="Austin", state="TX", npi="1932847561",
         beds=24, type="infusion-center", status="active"),
]


async def main() -> None:
    await db.init_db()
    async with db.SessionLocal() as s:
        for row in CENTERS:
            if await s.get(db.CancerCenter, row["id"]) is None:
                s.add(db.CancerCenter(**row))
        for row in HOSPITALS:
            if await s.get(db.Hospital, row["id"]) is None:
                s.add(db.Hospital(**row))
        await s.commit()
    print(f"seeded {len(CENTERS)} cancer center(s), {len(HOSPITALS)} facility/ies")


if __name__ == "__main__":
    asyncio.run(main())
