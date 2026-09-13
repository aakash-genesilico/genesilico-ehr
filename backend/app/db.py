"""Persistence. SQLite locally, Postgres by changing DATABASE_URL only."""
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from . import config

engine = create_async_engine(config.DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def from_epoch(ts: float) -> datetime:
    """Epoch seconds -> tz-aware UTC. The OAuth client speaks epoch."""
    return datetime.fromtimestamp(float(ts), timezone.utc)


def as_aware(dt: datetime) -> datetime:
    """Force a DB-read datetime to tz-aware UTC.

    SQLite has no timezone type, so `DateTime(timezone=True)` round-trips a
    tz-aware value to a NAIVE one. Comparing that against utcnow() raises
    "can't compare offset-naive and offset-aware datetimes" — which is exactly
    what /ontada/status hit the first time a token was ever stored. Postgres
    does preserve the offset, so this is a no-op there; call it on every
    datetime read back from the DB so the code behaves the same on both.
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class CancerCenter(Base):
    __tablename__ = "cancer_centers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(8), default="")
    organization_id: Mapped[str] = mapped_column(String(255), default="")
    ehr_vendor: Mapped[str] = mapped_column(String(32), default="none")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Hospital(Base):
    __tablename__ = "hospitals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    cancer_center_id: Mapped[str] = mapped_column(ForeignKey("cancer_centers.id"))
    city: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(8), default="")
    npi: Mapped[str] = mapped_column(String(16), default="")
    beds: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(String(32), default="hospital")
    status: Mapped[str] = mapped_column(String(32), default="active")


class Casebook(Base):
    __tablename__ = "casebooks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(255))
    mrn: Mapped[str] = mapped_column(String(64), default="")
    birth_date: Mapped[str] = mapped_column(String(16), default="")
    gender: Mapped[str] = mapped_column(String(16), default="")
    primary_diagnosis: Mapped[str] = mapped_column(Text, default="")
    diagnosis_code: Mapped[str] = mapped_column(String(16), default="")
    stage: Mapped[str] = mapped_column(String(16), default="")
    cancer_center_id: Mapped[str] = mapped_column(String(64), default="")
    hospital_id: Mapped[str] = mapped_column(String(64), default="")
    oncologist: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    ontada_fhir_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # The FHIR bundle exactly as the gateway returned it. Kept whole so a
    # completeness result can always be traced back to its source resource.
    fhir_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PreAuthPackage(Base):
    __tablename__ = "preauth_packages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    casebook_id: Mapped[str] = mapped_column(String(64))
    patient_name: Mapped[str] = mapped_column(String(255), default="")
    mrn: Mapped[str] = mapped_column(String(64), default="")
    regimen: Mapped[str] = mapped_column(Text, default="")
    payer_name: Mapped[str] = mapped_column(String(255), default="")
    payer_id: Mapped[str] = mapped_column(String(64), default="")
    member_id: Mapped[str] = mapped_column(String(64), default="")
    group_number: Mapped[str] = mapped_column(String(64), default="")
    hospital_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="drafting")
    lines: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    events: Mapped[list] = mapped_column(JSON, default=list)
    # Raw 271 from the last eligibility check — the provenance receipt.
    eligibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthToken(Base):
    """One row per connected EHR tenant. Refresh token is what keeps the
    backend working after the practitioner closes the browser."""

    __tablename__ = "oauth_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(Text, default="")
    patient_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fhir_base: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


__all__ = [
    "Base", "CancerCenter", "Hospital", "Casebook", "PreAuthPackage", "OAuthToken",
    "SessionLocal", "engine", "init_db", "get_session", "select", "utcnow", "from_epoch",
]
