"""Casebooks. Created by users, stored here, optionally bound to a real
Ontada FHIR Patient — in which case the pulled bundle is kept verbatim."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config, db
from ..errors import ApiError, Unconfigured, UpstreamError
from ..integrations import stedi

from .. import schemas as S

router = APIRouter(prefix="/casebooks", tags=["casebooks"])


class CasebookIn(BaseModel):
    patient_name: str = Field(..., min_length=1)
    mrn: str = ""
    birth_date: str = ""
    gender: str = ""
    primary_diagnosis: str = ""
    diagnosis_code: str = ""
    stage: str = ""
    cancer_center_id: str = ""
    hospital_id: str = ""
    oncologist: str = ""
    ontada_fhir_id: str | None = None
    fhir_snapshot: dict = Field(default_factory=dict)


def _out(c: db.Casebook) -> dict:
    snap = c.fhir_snapshot or {}
    return {
        "id": c.id, "patientName": c.patient_name, "mrn": c.mrn,
        "birthDate": c.birth_date, "gender": c.gender,
        "primaryDiagnosis": c.primary_diagnosis, "diagnosisCode": c.diagnosis_code,
        "stage": c.stage, "cancerCenterId": c.cancer_center_id,
        "hospitalId": c.hospital_id, "oncologist": c.oncologist,
        "status": c.status, "ontadaFhirId": c.ontada_fhir_id,
        "resourceCounts": snap.get("counts") or {},
        # No CancerAI/Digital Twin endpoint is wired, so these stay null rather
        # than carrying a number nobody computed.
        "cancerAiConfidence": None,
        "dtEfficacyScore": None,
        "createdAt": c.created_at.isoformat(), "updatedAt": c.updated_at.isoformat(),
    }


@router.get("", responses={200: {"model": S.CasebookList}, **S.ERRORS})
async def list_casebooks(session: AsyncSession = Depends(db.get_session)):
    rows = (await session.execute(
        db.select(db.Casebook).order_by(db.Casebook.updated_at.desc()))).scalars().all()
    return {"count": len(rows), "results": [_out(c) for c in rows]}


@router.post("", status_code=201, responses={201: {"model": S.CasebookOut}, **S.ERRORS})
async def create_casebook(body: CasebookIn, session: AsyncSession = Depends(db.get_session)):
    cb = db.Casebook(id=f"cb-{uuid.uuid4().hex[:8]}", **body.model_dump())
    cb.status = "ai-ready" if body.ontada_fhir_id else "draft"
    session.add(cb)
    await session.commit()
    return _out(cb)


@router.get("/{casebook_id}", responses={200: {"model": S.CasebookOut}, **S.ERRORS})
async def get_casebook(casebook_id: str, session: AsyncSession = Depends(db.get_session)):
    cb = await session.get(db.Casebook, casebook_id)
    if cb is None:
        raise ApiError(f"No casebook {casebook_id}", status=404)
    return {**_out(cb), "fhirSnapshot": cb.fhir_snapshot or {}}


@router.get("/{casebook_id}/packages", responses={200: {"model": S.CasebookPackageList}, **S.ERRORS})
async def casebook_packages(casebook_id: str, session: AsyncSession = Depends(db.get_session)):
    """Pre-auth packages belonging to this patient, newest first."""
    rows = (await session.execute(
        db.select(db.PreAuthPackage)
        .where(db.PreAuthPackage.casebook_id == casebook_id)
        .order_by(db.PreAuthPackage.created_at.desc())
    )).scalars().all()
    return {
        "count": len(rows),
        "results": [{"id": p.id, "payer": p.payer_name, "memberId": p.member_id,
                     "regimen": p.regimen, "status": p.status,
                     "lines": len(p.lines or []),
                     "hasEligibility": bool((p.eligibility or {}).get("raw_271")),
                     "createdAt": p.created_at.isoformat()} for p in rows],
    }


@router.post("/{casebook_id}/discover-coverage", responses={200: {"model": S.CoverageDiscovery}, **S.ERRORS})
async def discover_coverage(casebook_id: str, session: AsyncSession = Depends(db.get_session)):
    """Find every policy this patient is covered under.

    Answers a question the chart usually cannot: is the payer we are about to
    bill actually the primary, and is the patient a dependent on a plan nobody
    recorded? Getting that order wrong is a denial.
    """
    if not config.STEDI_API_KEY:
        raise Unconfigured("Stedi insurance discovery", "Set STEDI_API_KEY in backend/.env")

    cb = await session.get(db.Casebook, casebook_id)
    if cb is None:
        raise ApiError(f"No casebook {casebook_id}", status=404)
    if not (cb.patient_name and cb.birth_date):
        raise ApiError("Discovery needs the patient's name and date of birth.", status=422)

    first, _, last = (cb.patient_name or "").partition(" ")
    try:
        result = await stedi.discover_coverage({
            "first_name": first,
            "last_name": last or first,
            "dob": cb.birth_date,
            "state": "TX",
            "date_of_service": db.utcnow().date().isoformat(),
        })
    except Exception as exc:
        raise UpstreamError("stedi", str(exc)) from exc

    # Flag anything that is not the policy the active package is billing.
    pkgs = (await session.execute(
        db.select(db.PreAuthPackage).where(db.PreAuthPackage.casebook_id == casebook_id)
    )).scalars().all()
    billing = {p.member_id for p in pkgs if p.member_id}
    for item in result.get("items", []):
        item["on_file"] = item["member_id"] in billing

    return result
