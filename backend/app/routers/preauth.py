"""Pre-authorisation packages.

The honest boundary of this router: it can build a package, price it against a
REAL 271 benefit response, and record the result. It cannot submit a prior
authorisation, because no 278 transport exists in this integration — see
/api/capabilities. `submit` therefore returns 501 with the reason rather than
minting an authorisation number nobody issued.
"""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config, db
from ..errors import ApiError, Unconfigured, UpstreamError
from ..integrations import stedi
from ..services import benefits

from .. import schemas as S

router = APIRouter(prefix="/preauth", tags=["preauth"])


class PackageIn(BaseModel):
    casebook_id: str
    regimen: str = ""
    payer_name: str = ""
    member_id: str = ""
    group_number: str = ""
    hospital_id: str = ""
    lines: list[dict] = Field(default_factory=list)


def _out(p: db.PreAuthPackage) -> dict:
    return {
        "id": p.id, "casebookId": p.casebook_id, "patientName": p.patient_name,
        "mrn": p.mrn, "regimen": p.regimen, "payer": p.payer_name,
        "payerId": p.payer_id, "memberId": p.member_id, "groupNumber": p.group_number,
        "hospitalId": p.hospital_id, "status": p.status,
        "lines": p.lines or [], "evidence": p.evidence or [], "events": p.events or [],
        "eligibility": p.eligibility,
        "createdAt": p.created_at.isoformat(), "updatedAt": p.updated_at.isoformat(),
        "submittedAt": p.submitted_at.isoformat() if p.submitted_at else None,
    }


def _event(p: db.PreAuthPackage, actor: str, action: str, kind="info", detail=None) -> None:
    events = list(p.events or [])
    events.append({"id": uuid.uuid4().hex[:8], "at": db.utcnow().isoformat(),
                   "actor": actor, "action": action, "kind": kind, "detail": detail})
    p.events = events


@router.get("", responses={200: {"model": S.PackageList}, **S.ERRORS})
async def list_packages(session: AsyncSession = Depends(db.get_session)):
    rows = (await session.execute(
        db.select(db.PreAuthPackage).order_by(db.PreAuthPackage.updated_at.desc()))).scalars().all()
    return {"count": len(rows), "results": [_out(p) for p in rows]}


@router.post("", status_code=201, responses={201: {"model": S.PackageOut}, **S.ERRORS})
async def create_package(body: PackageIn, session: AsyncSession = Depends(db.get_session)):
    cb = await session.get(db.Casebook, body.casebook_id)
    if cb is None:
        raise ApiError(f"No casebook {body.casebook_id}", status=404)

    pkg = db.PreAuthPackage(
        id=f"pa-{uuid.uuid4().hex[:8]}",
        casebook_id=cb.id, patient_name=cb.patient_name, mrn=cb.mrn,
        regimen=body.regimen, payer_name=body.payer_name, member_id=body.member_id,
        group_number=body.group_number, hospital_id=body.hospital_id or cb.hospital_id,
        lines=body.lines, evidence=[], events=[],
    )
    _event(pkg, "system", f"Package created from casebook {cb.id}")
    session.add(pkg)
    await session.commit()
    return _out(pkg)


@router.get("/{package_id}", responses={200: {"model": S.PackageOut}, **S.ERRORS})
async def get_package(package_id: str, session: AsyncSession = Depends(db.get_session)):
    p = await session.get(db.PreAuthPackage, package_id)
    if p is None:
        raise ApiError(f"No package {package_id}", status=404)
    return _out(p)


class LinesIn(BaseModel):
    lines: list[dict]


@router.post("/{package_id}/lines", responses={200: {"model": S.PackageOut}, **S.ERRORS})
async def set_lines(package_id: str, body: LinesIn,
                    session: AsyncSession = Depends(db.get_session)):
    """Replace the billable lines — this is how a drug tier gets assigned."""
    p = await session.get(db.PreAuthPackage, package_id)
    if p is None:
        raise ApiError(f"No package {package_id}", status=404)
    p.lines = body.lines
    await session.commit()
    return _out(p)


@router.get("/{package_id}/benefits", responses={200: {"model": S.BenefitsResponse}, **S.ERRORS})
async def package_benefits(package_id: str, network: str = "in",
                           session: AsyncSession = Depends(db.get_session)):
    """Parsed benefits from the 271 already stored on this package."""
    p = await session.get(db.PreAuthPackage, package_id)
    if p is None:
        raise ApiError(f"No package {package_id}", status=404)
    raw = (p.eligibility or {}).get("raw_271")
    if not raw:
        raise ApiError("No eligibility response stored on this package yet. Run a coverage check.",
                       status=428, code="no_eligibility")
    parsed = benefits.parse(raw)
    return {
        "benefits": parsed,
        "estimate": benefits.estimate(p.lines or [], parsed, network=network),
        "source": (p.eligibility or {}).get("source") or {"kind": "live"},
    }


@router.post("/{package_id}/coverage", responses={200: {"model": S.CoverageRunResponse}, **S.ERRORS})
async def run_coverage(package_id: str, session: AsyncSession = Depends(db.get_session)):
    """Run a real 270 for this package and price its lines off the 271."""
    if not config.STEDI_API_KEY:
        raise Unconfigured("Stedi eligibility", "Set STEDI_API_KEY in backend/.env")

    p = await session.get(db.PreAuthPackage, package_id)
    if p is None:
        raise ApiError(f"No package {package_id}", status=404)
    cb = await session.get(db.Casebook, p.casebook_id)
    if cb is None:
        raise ApiError("The casebook behind this package is gone.", status=409)
    if not (p.payer_name and p.member_id):
        raise ApiError("Package needs a payer and a member id before coverage can run.",
                       status=422)

    first, _, last = (cb.patient_name or "").partition(" ")
    params = {
        "payer": p.payer_name,
        "member_id": p.member_id,
        "first_name": first,
        "last_name": last or first,
        "provider_npi": config.PROVIDER_NPI or None,
        "provider_name": config.PROVIDER_NAME,
        "service_type_codes": ["30"],
    }
    if cb.birth_date:
        params["dob"] = cb.birth_date
    if p.group_number:
        params["group_number"] = p.group_number
    params = {k: v for k, v in params.items() if v}

    try:
        elig = await stedi.check_eligibility(params)
    except Exception as exc:
        raise UpstreamError("stedi", str(exc)) from exc

    raw = elig.get("raw_271") or {}
    parsed = benefits.parse(raw)
    priced = benefits.estimate(p.lines or [], parsed)
    p.eligibility = {"raw_271": raw, "source": {"kind": "live", "mode": config.stedi_mode()}}
    p.lines = priced["lines"]
    p.payer_id = elig.get("resolved_payer_id") or p.payer_id
    if elig.get("errors"):
        _event(p, "Stedi", "Payer rejected the eligibility request", kind="error",
               detail=elig["errors"][0].get("description"))
    else:
        _event(p, "Stedi", "Eligibility 270/271 completed", kind="success",
               detail=f"Trace {elig.get('trace')}")
    await session.commit()

    return {"package": _out(p), "benefits": parsed, "estimate": priced,
            "mode": config.stedi_mode()}


@router.post("/{package_id}/submit", status_code=501, responses={501: {"model": S.ErrorEnvelope, "description": "Always. There is no X12 278 channel."}})
async def submit(package_id: str):
    """Deliberately unimplemented.

    Submitting a prior authorisation is an X12 278 transaction. Stedi exposes
    no 278 endpoint — verified against both the test and the production key,
    every candidate path returns 404. Returning a fabricated authorisation
    number here would be the single most damaging thing this service could do,
    so it refuses instead.
    """
    raise ApiError(
        "Prior-authorisation submission is not available. Stedi exposes no X12 278 "
        "endpoint, so there is no channel to send this package to the payer. Options: "
        "a clearinghouse that supports 278, the payer's own portal, or a Da Vinci PAS "
        "FHIR endpoint if the payer offers one.",
        status=501, code="not_implemented",
        detail={"package_id": package_id, "verified": "278 paths 404 on test and production keys"},
    )
