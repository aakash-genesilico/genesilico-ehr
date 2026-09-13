"""Response models — these exist so the OpenAPI spec describes real shapes.

Without them FastAPI documents every endpoint as "returns an object", which
tells an integrator nothing. Models here are attached for *documentation*
(`responses={...: {"model": X}}`) rather than as `response_model`, because
several endpoints deliberately pass upstream payloads through untouched and a
response_model would silently strip fields the caller needs.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------- errors
class ErrorBody(BaseModel):
    code: str = Field(..., description="Machine-readable: unconfigured, upstream_error, "
                                       "ontada_not_connected, form_invalid, not_implemented …")
    message: str = Field(..., description="Human-readable. Upstream messages are kept verbatim.")
    detail: Any | None = None


class ErrorEnvelope(BaseModel):
    """Every non-2xx response from this API has exactly this shape."""
    error: ErrorBody


ERRORS: dict = {
    400: {"model": ErrorEnvelope, "description": "Bad request"},
    404: {"model": ErrorEnvelope, "description": "Not found"},
    422: {"model": ErrorEnvelope, "description": "Validation failed"},
    428: {"model": ErrorEnvelope, "description": "A precondition is unmet — typically Ontada is not connected"},
    501: {"model": ErrorEnvelope, "description": "Deliberately not implemented; the reason is in the message"},
    502: {"model": ErrorEnvelope, "description": "An upstream (Stedi, Ontada) failed"},
    503: {"model": ErrorEnvelope, "description": "A capability is not configured"},
}


# --------------------------------------------------------------- health
class Health(BaseModel):
    status: str
    env: str


class CapabilityFlag(BaseModel):
    available: bool
    real: bool | None = None
    reason: str | None = None
    note: str | None = None


class StediCapabilities(BaseModel):
    mode: Literal["test", "production", "unconfigured"]
    payer_search: CapabilityFlag
    eligibility_270_271: CapabilityFlag
    claim_status_276_277: CapabilityFlag
    insurance_discovery: CapabilityFlag
    prior_auth_278: CapabilityFlag


class OntadaCapabilities(BaseModel):
    configured: bool
    fhir_base: str | None
    client_auth: str | None
    grant_types: list[str]
    service_to_service: CapabilityFlag


class Capabilities(BaseModel):
    """What this deployment can genuinely do. The UI reads it to disable
    controls rather than let them fail when pressed."""
    stedi: StediCapabilities
    ontada: OntadaCapabilities
    cancerai_digital_twin: CapabilityFlag


# --------------------------------------------------------------- admin
class CancerCenterOut(BaseModel):
    id: str
    name: str
    city: str
    state: str
    organizationId: str
    ehrVendor: str
    status: str
    createdAt: str
    hospitalIds: list[str]


class HospitalOut(BaseModel):
    id: str
    name: str
    cancerCenterId: str
    city: str
    state: str
    npi: str
    beds: int
    type: str
    status: str


class CancerCenterList(BaseModel):
    count: int
    results: list[CancerCenterOut]


class HospitalList(BaseModel):
    count: int
    results: list[HospitalOut]


# --------------------------------------------------------------- casebooks
class CasebookOut(BaseModel):
    id: str
    patientName: str
    mrn: str
    birthDate: str
    gender: str
    primaryDiagnosis: str
    diagnosisCode: str
    stage: str
    cancerCenterId: str
    hospitalId: str
    oncologist: str
    status: str
    ontadaFhirId: str | None
    resourceCounts: dict[str, int]
    cancerAiConfidence: float | None = Field(None, description="Always null — gSage is not wired to this module")
    dtEfficacyScore: float | None = Field(None, description="Always null — gSage is not wired to this module")
    createdAt: str
    updatedAt: str


class CasebookList(BaseModel):
    count: int
    results: list[CasebookOut]


class CasebookPackageRow(BaseModel):
    id: str
    payer: str
    memberId: str
    regimen: str
    status: str
    lines: int
    hasEligibility: bool
    createdAt: str


class CasebookPackageList(BaseModel):
    count: int
    results: list[CasebookPackageRow]


# --------------------------------------------------------------- pre-auth
class PreAuthLineOut(BaseModel):
    id: str
    description: str
    code: str = ""
    category: str | None = None
    units: int | None = None
    billed_cents: int
    drug_tier: int | None = Field(None, description="Formulary tier. The 271 prices by tier but never "
                                                    "states which tier a HCPCS code is in.")
    tier_kind: str | None = None
    patient_estimate_cents: int | None = Field(None, description="null means the line could not be priced")
    estimate_basis: str | None = None
    capped_by_oop: bool | None = None
    estimated: bool | None = None


class PreAuthEventOut(BaseModel):
    id: str
    at: str
    actor: str
    action: str
    kind: Literal["info", "success", "warning", "error"]
    detail: str | None = None


class PackageOut(BaseModel):
    id: str
    casebookId: str
    patientName: str
    mrn: str
    regimen: str
    payer: str
    payerId: str
    memberId: str
    groupNumber: str
    hospitalId: str
    status: str
    lines: list[PreAuthLineOut]
    evidence: list[Any]
    events: list[PreAuthEventOut]
    eligibility: dict[str, Any] | None = Field(None, description="Carries the raw 271 under `raw_271`")
    createdAt: str
    updatedAt: str
    submittedAt: str | None


class PackageList(BaseModel):
    count: int
    results: list[PackageOut]


# --------------------------------------------------------------- benefits
class Accumulator(BaseModel):
    kind: Literal["out_of_pocket", "deductible"]
    level: str = Field(..., description="individual | family")
    network: Literal["in", "out", "na"]
    basis: str = Field(..., description="service year | year to date | remaining")
    amount: float
    service_types: list[str]


class DrugTier(BaseModel):
    kind: Literal["provider_administered", "specialty", "pharmacy"]
    tier: int
    label: str = Field(..., description="Payer's own wording, e.g. 'PROVIDER ADMINISTERED DRUG TIER 9'")
    in_network: float | None
    out_of_network: float | None
    varies_by_location: bool


class ParsedBenefits(BaseModel):
    """A real 271 reduced to what a pre-auth screen needs.

    A commercial plan can carry 700+ benefit lines with no coinsurance and no
    deductible at all — oncology is priced by drug tier. Hence `drug_tiers`.
    """
    active: bool | None
    payer: dict[str, Any]
    plan: dict[str, Any]
    member: dict[str, Any]
    accumulators: list[Accumulator]
    drug_tiers: list[DrugTier]
    coinsurance: list[dict[str, Any]]
    limitations: list[dict[str, Any]]
    referrals: list[dict[str, Any]]
    errors: list[dict[str, Any]] = Field(..., description="The payer's own AAA rejections, verbatim")
    trace_id: str | None
    mode: str | None
    entry_count: int


class EstimateTotals(BaseModel):
    billed_cents: int
    patient_estimate_cents: int
    lines_estimated: int
    lines_unknown: int


class Estimate(BaseModel):
    lines: list[PreAuthLineOut]
    network: str
    oop_remaining: float | None = Field(None, description="Caps the running total. A real figure from the payer.")
    totals: EstimateTotals
    disclaimer: str


class BenefitsResponse(BaseModel):
    benefits: ParsedBenefits
    estimate: Estimate
    source: dict[str, Any]


class CoverageRunResponse(BaseModel):
    package: PackageOut
    benefits: ParsedBenefits
    estimate: Estimate
    mode: str


# --------------------------------------------------------------- discovery
class DiscoveredCoverage(BaseModel):
    payer_name: str
    payer_id: str
    member_id: str
    group_number: str
    subscriber_name: str
    patient_is_dependent: bool = Field(..., description="True when the patient is covered under "
                                                        "somebody else's policy")
    dependent_name: str
    on_file: bool = Field(..., description="False means no package is billing this policy")


class CoverageDiscovery(BaseModel):
    available: bool
    reason: str | None = None
    found: int | None = None
    distinct_policies: int | None = None
    items: list[DiscoveredCoverage]
    warnings: list[str] | None = None
    discovery_id: str | None = None


# --------------------------------------------------------------- payers
class PayerRow(BaseModel):
    stedi_id: str
    payer_id: str
    name: str
    aliases: list[str] = []
    eligibility_support: str | None = None


class PayerSearch(BaseModel):
    query: str
    count: int
    results: list[PayerRow]
    source: str


# --------------------------------------------------------------- ontada
class OntadaFiles(BaseModel):
    """Attachment metadata. Bytes come from /ontada/file/{binary_id}.

    `errors` is per source resource type, so one unreadable type never makes the
    whole list look empty.
    """
    count: int
    files: list[dict]
    errors: dict[str, str] = {}
    withheld_note: str | None = None


class OntadaSummary(BaseModel):
    """A chart phrased for a reviewer. `gaps` is load-bearing: it is what stops
    a short summary from reading as a complete one."""
    narrative: str
    patient: dict
    problems: list[dict]
    regimen: list[dict]
    dosing_basis: list[dict]
    labs: list[dict]
    evidence: dict
    gaps: list[str]


class OntadaStatus(BaseModel):
    configured: bool
    connected: bool
    fhir_base: str | None
    grant_types: list[str]
    launch_context: str
    fhir_user: str | None = None
    panel_search_supported: bool
    panel_search_reason: str
    reason: str | None = None
    expired: bool | None = None
    can_refresh: bool | None = None
    expires_at: str | None = None
    scope: str | None = None
    patient_context: str | None = None


class OntadaAuthorize(BaseModel):
    url: str = Field(..., description="Open in a real browser — the endpoint is behind a WAF")
    state: str


class OntadaImport(BaseModel):
    casebook_id: str
    created: bool
    package_id: str | None
    counts: dict[str, int]
    coverage: dict[str, Any]
    unmapped: list[str] = Field(..., description="Target fields the bundle could not fill")
    withheld_note: str | None = None


# --------------------------------------------------------------- policy form
class FormField(BaseModel):
    id: str
    label: str
    type: Literal["text", "select", "date", "checkbox", "tel", "number"]
    required: bool = False
    value: Any | None = None
    options: list[dict[str, Any]] | None = None
    help: str | None = None
    pattern: str | None = None
    maxLength: int | None = None
    visible_when: dict[str, Any] | None = Field(None, description="Show only when these values hold")
    sensitive: bool | None = None
    x12: str | None = Field(None, description="The X12 element this field maps onto — the contract "
                                               "between the form and the 270 it produces")


class FormSection(BaseModel):
    id: str
    title: str
    fields: list[FormField]


class PolicyForm(BaseModel):
    """Field schema for one payer.

    A Medicare MBI, a BlueCard alpha prefix, a TRICARE sponsor SSN and a
    commercial member ID are not interchangeable. `family` says which set of
    rules applies and `why` says how it was decided.
    """
    form_id: str | None = None
    form_version: str | None = None
    family: dict[str, Any] = Field(..., description="{id, label, why} — which plan-family rules apply")
    payer: dict[str, Any] | None = None
    sections: list[FormSection]
    prefill: dict[str, Any] | None = Field(None, description="Values already known, and where each came "
                                                              "from, so a prefilled field is never mistaken "
                                                              "for one the clinician typed")
    consent_text: str | None = Field(None, description="Attestation the user must accept before a real "
                                                        "payer call is made on this patient")
    sources: list[dict[str, Any]] | None = Field(None, description="Citations for the payer-specific rules "
                                                                    "this form enforces (CMS, X12, BlueCard …)")


class EligibilityRun(BaseModel):
    source: dict[str, Any] = Field(..., description='{"kind":"live"|"replay", …}')
    benefits: ParsedBenefits
    estimate: Estimate | None = None


class ReplayRow(BaseModel):
    file: str
    payer: str
    member_id: str
    name: str
    plan: str
    mode: str
    entries: int


class ReplayList(BaseModel):
    count: int
    results: list[ReplayRow]
