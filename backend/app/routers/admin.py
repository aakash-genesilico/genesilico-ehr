"""Cancer centers and hospitals — this platform's own reference data.

These are not clinical records pulled from anywhere; they are the tenant
configuration an administrator enters. They live in our database and are
created through this API.
"""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import db
from ..errors import ApiError

from .. import schemas as S

router = APIRouter(prefix="/admin", tags=["admin"])


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class CancerCenterIn(BaseModel):
    name: str = Field(..., min_length=2)
    city: str = ""
    state: str = ""
    organization_id: str = ""
    ehr_vendor: str = "none"
    status: str = "active"


class HospitalIn(BaseModel):
    name: str = Field(..., min_length=2)
    cancer_center_id: str
    city: str = ""
    state: str = ""
    npi: str = ""
    beds: int = 0
    type: str = "hospital"
    status: str = "active"


def _center_out(c: db.CancerCenter, sites: list[db.Hospital]) -> dict:
    return {
        "id": c.id, "name": c.name, "city": c.city, "state": c.state,
        "organizationId": c.organization_id, "ehrVendor": c.ehr_vendor,
        "status": c.status, "createdAt": c.created_at.isoformat(),
        "hospitalIds": [h.id for h in sites],
    }


def _hospital_out(h: db.Hospital) -> dict:
    return {
        "id": h.id, "name": h.name, "cancerCenterId": h.cancer_center_id,
        "city": h.city, "state": h.state, "npi": h.npi, "beds": h.beds,
        "type": h.type, "status": h.status,
    }


@router.get("/cancer-centers", responses={200: {"model": S.CancerCenterList}, **S.ERRORS})
async def list_centers(session: AsyncSession = Depends(db.get_session)):
    centers = (await session.execute(db.select(db.CancerCenter))).scalars().all()
    hospitals = (await session.execute(db.select(db.Hospital))).scalars().all()
    by_center: dict[str, list] = {}
    for h in hospitals:
        by_center.setdefault(h.cancer_center_id, []).append(h)
    return {"count": len(centers),
            "results": [_center_out(c, by_center.get(c.id, [])) for c in centers]}


@router.post("/cancer-centers", status_code=201, responses={201: {"model": S.CancerCenterOut}, **S.ERRORS})
async def create_center(body: CancerCenterIn, session: AsyncSession = Depends(db.get_session)):
    center = db.CancerCenter(id=_slug("cc"), **body.model_dump())
    session.add(center)
    await session.commit()
    return _center_out(center, [])


@router.get("/hospitals", responses={200: {"model": S.HospitalList}, **S.ERRORS})
async def list_hospitals(cancer_center_id: str | None = None,
                         session: AsyncSession = Depends(db.get_session)):
    stmt = db.select(db.Hospital)
    if cancer_center_id:
        stmt = stmt.where(db.Hospital.cancer_center_id == cancer_center_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {"count": len(rows), "results": [_hospital_out(h) for h in rows]}


@router.post("/hospitals", status_code=201, responses={201: {"model": S.HospitalOut}, **S.ERRORS})
async def create_hospital(body: HospitalIn, session: AsyncSession = Depends(db.get_session)):
    if await session.get(db.CancerCenter, body.cancer_center_id) is None:
        raise ApiError(f"No cancer center with id {body.cancer_center_id}", status=404)
    hospital = db.Hospital(id=_slug("hosp"), **body.model_dump())
    session.add(hospital)
    await session.commit()
    return _hospital_out(hospital)
