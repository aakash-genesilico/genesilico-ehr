/**
 * Typed client for the GeneSilico EHR backend.
 *
 * Every call goes to a real service. When a capability is not wired the API
 * answers with a structured error carrying the reason — the UI renders that
 * reason rather than falling back to invented data.
 */

// `??` would let an EMPTY string through, and an empty base silently rewrites
// every call into a same-origin path that 404s against the Next dev server —
// which looks exactly like "the API returned nothing" rather than a config bug.
// Treat blank as unset.
/** Build a query string from defined values only, so an absent id sends nothing
 *  rather than the literal string "undefined". */
function qp(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : "";
}

export interface OntadaFile {
  readonly binary_id: string;
  readonly url: string;
  readonly content_type: string;
  readonly title: string;
  readonly size: number | null;
  readonly created: string;
  readonly has_inline_data: boolean;
  /** We have a handle to try — NOT a promise the bytes exist. */
  readonly addressable: boolean;
  readonly source_type: string;
  readonly source_id: string;
  readonly label: string;
  readonly date: string;
  readonly status: string;
}
export interface OntadaFileList {
  readonly count: number;
  readonly files: OntadaFile[];
  readonly errors: Record<string, string>;
  readonly withheld_note: string | null;
}

export interface SummaryProblem {
  readonly display: string; readonly icd10: string; readonly snomed: string;
  readonly status: string; readonly onset: string; readonly stage: string;
  /** "chart" when the Condition carried the stage, "entered by hand" when a
   *  person supplied it. A payer citation may only rest on the first. */
  readonly stage_source?: string;
}
export interface SummaryDrug {
  readonly drug: string; readonly rxnorm: string; readonly orders: number;
  readonly administered: number; readonly first: string; readonly last: string;
  readonly statuses: string[]; readonly notes: string[];
}
export interface SummaryMeasure {
  readonly label: string; readonly value: number; readonly unit: string; readonly as_of: string;
}
export interface SummaryLab {
  readonly test: string; readonly value: number | null; readonly unit: string;
  readonly text: string; readonly as_of: string; readonly interpretation: string;
}
export interface SummaryEvidenceKind {
  readonly kind: string; readonly count: number; readonly latest: string;
}
export interface ClinicalSummary {
  readonly narrative: string;
  readonly patient: { name: string; gender: string; birth_date: string; age: number | null };
  readonly problems: SummaryProblem[];
  readonly regimen: SummaryDrug[];
  readonly dosing_basis: SummaryMeasure[];
  readonly labs: SummaryLab[];
  readonly evidence: { documents: SummaryEvidenceKind[]; reports: SummaryEvidenceKind[] };
  readonly gaps: string[];
}

/** One FHIR resource, left deliberately open — the shape is the server's, not
 *  ours, and narrowing it here would drop fields the viewer wants to show. */
export interface FhirResource {
  readonly resourceType?: string;
  readonly id?: string;
  readonly [key: string]: unknown;
}

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8090/api";

export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: unknown;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail?: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.detail = body.detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    // A dead backend is its own diagnosis; don't dress it up as a 500.
    throw new ApiError(0, {
      code: "backend_unreachable",
      message: `Cannot reach the API at ${API_BASE}. Start it with: cd backend && ./.venv/bin/python -m uvicorn app.main:app --port 8090`,
    });
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.error ?? { code: "http_error", message: res.statusText });
  }
  return res.json() as Promise<T>;
}

const get = <T,>(p: string) => request<T>(p);
const post = <T,>(p: string, body?: unknown) =>
  request<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

/* ---------------------------------------------------------------- types */

export interface Capabilities {
  stedi: {
    mode: "test" | "production" | "unconfigured";
    payer_search: { available: boolean };
    eligibility_270_271: { available: boolean; note?: string };
    claim_status_276_277: { available: boolean; reason: string | null };
    insurance_discovery: { available: boolean; reason: string | null };
    prior_auth_278: { available: boolean; reason: string };
  };
  ontada: {
    configured: boolean;
    fhir_base: string | null;
    client_auth: string | null;
    grant_types: string[];
    service_to_service: { available: boolean; reason: string };
  };
  cancerai_digital_twin: { available: boolean; reason: string };
}

export interface OntadaPatient {
  id: string;
  name: string;
  mrn: string;
  birth_date: string;
  gender: string;
  /** A real chart carries an MR identifier; a portal login account does not. */
  has_mrn: boolean;
}

export interface OntadaPatients {
  count: number;
  results: OntadaPatient[];
  panel_total: number;
  charts_total: number;
  filter_note: string;
}

export interface OntadaStatus {
  configured: boolean;
  connected: boolean;
  fhir_base: string | null;
  grant_types: string[];
  launch_context: string;
  panel_search_supported: boolean;
  panel_search_reason: string;
  reason?: string;
  expired?: boolean;
  can_refresh?: boolean;
  expires_at?: string;
  scope?: string;
  patient_context?: string | null;
  fhir_user?: string | null;
  /** What the backend's background token keeper has been doing. `reauth_required`
   *  is the one to act on: the grant is gone and only a browser login restores it. */
  keeper?: {
    enabled: boolean;
    every_seconds: number;
    renews_at_t_minus_seconds: number;
    last_refresh_at?: string | null;
    last_refresh_reason?: string | null;
    rotated?: boolean;
    reauth_required?: boolean;
    last_error?: string | null;
    failures?: number;
    refreshes?: number;
  };
}

export interface CancerCenter {
  id: string;
  name: string;
  city: string;
  state: string;
  organizationId: string;
  ehrVendor: string;
  status: string;
  createdAt: string;
  hospitalIds: string[];
}

export interface Hospital {
  id: string;
  name: string;
  cancerCenterId: string;
  city: string;
  state: string;
  npi: string;
  beds: number;
  type: string;
  status: string;
}

export interface Casebook {
  id: string;
  patientName: string;
  mrn: string;
  birthDate: string;
  gender: string;
  primaryDiagnosis: string;
  diagnosisCode: string;
  stage: string;
  cancerCenterId: string;
  hospitalId: string;
  oncologist: string;
  status: string;
  /** The fields still empty, in plain words — what "Gaps pending" is about. */
  gapFields?: string[];
  ontadaFhirId: string | null;
  resourceCounts: Record<string, number>;
  cancerAiConfidence: number | null;
  dtEfficacyScore: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface PreAuthLine {
  id: string;
  description: string;
  code: string;
  code_system?: string;
  category?: string;
  units?: number;
  billed_cents: number;
  /** Formulary tier for a provider-administered drug. The 271 prices by tier;
   *  which tier a HCPCS code falls in is not something the payer returns. */
  drug_tier?: number | null;
  tier_kind?: string;
  patient_estimate_cents?: number | null;
  estimate_basis?: string;
  capped_by_oop?: boolean;
  estimated?: boolean;
}

export interface PreAuthEvent {
  id: string;
  at: string;
  actor: string;
  action: string;
  kind: "info" | "success" | "warning" | "error";
  detail?: string | null;
}

export interface PreAuthPackage {
  id: string;
  casebookId: string;
  patientName: string;
  mrn: string;
  regimen: string;
  payer: string;
  payerId: string;
  memberId: string;
  groupNumber: string;
  hospitalId: string;
  status: string;
  lines: PreAuthLine[];
  evidence: unknown[];
  events: PreAuthEvent[];
  eligibility: Record<string, unknown> | null;
  createdAt: string;
  updatedAt: string;
  submittedAt: string | null;
}

/* ---- payer-specific intake form ---- */

export interface FormField {
  id: string;
  label: string;
  type: "text" | "select" | "date" | "checkbox" | "tel" | "number";
  required?: boolean;
  value?: string | boolean;
  options?: Array<{ value: string; label: string }>;
  help?: string;
  placeholder?: string;
  pattern?: string;
  maxLength?: number;
  /** Only shown when another field holds a given value. */
  visible_when?: Record<string, unknown>;
  sensitive?: boolean;
  source?: string;
  x12?: string;
}

export interface FormSection {
  id: string;
  title: string;
  fields: FormField[];
  help?: string;
}

export interface PolicyForm {
  family: { id: string; label: string; why?: string };
  payer?: { name?: string; payer_id?: string };
  sections: FormSection[];
  version?: string;
}

/* ---- parsed 271 ---- */

export interface Accumulator {
  kind: "out_of_pocket" | "deductible";
  level: string;
  network: "in" | "out" | "na";
  basis: string;
  amount: number;
}

export interface DrugTier {
  kind: "provider_administered" | "specialty" | "pharmacy";
  tier: number;
  label: string;
  in_network: number | null;
  out_of_network: number | null;
  varies_by_location: boolean;
}

export interface ParsedBenefits {
  active: boolean | null;
  payer: { name: string | null; id: string | null };
  plan: { name: string | null; insurance_type: string | null; period_start: string | null; period_end: string | null };
  member: {
    member_id: string | null; group_number: string | null;
    first_name: string | null; last_name: string | null;
    date_of_birth: string | null; gender: string | null;
    address?: { address1?: string; city?: string; state?: string; postalCode?: string } | null;
  };
  accumulators: Accumulator[];
  drug_tiers: DrugTier[];
  coinsurance: Array<{ percent: number; network: string; labels: string[] }>;
  limitations: Array<{ quantity: number | null; unit: string | null; service_types: string[]; labels: string[] }>;
  referrals: Array<{ role: string | null; name: string | null; contacts: string[] }>;
  errors: Array<{ code?: string; description?: string; resolution?: string }>;
  trace_id: string | null;
  mode: string | null;
  entry_count: number;
}

export interface Estimate {
  lines: PreAuthLine[];
  network: string;
  oop_remaining: number | null;
  totals: {
    billed_cents: number;
    patient_estimate_cents: number;
    lines_estimated: number;
    lines_unknown: number;
  };
  disclaimer: string;
}

export interface Replay {
  file: string;
  payer: string;
  member_id: string;
  name: string;
  plan: string;
  mode: string;
  entries: number;
}

export interface DiscoveredCoverage {
  payer_name: string;
  payer_id: string;
  member_id: string;
  group_number: string;
  subscriber_name: string;
  patient_is_dependent: boolean;
  dependent_name: string;
  on_file: boolean;
}

export interface CoverageDiscovery {
  available: boolean;
  reason?: string;
  found?: number;
  distinct_policies?: number;
  items: DiscoveredCoverage[];
  warnings?: string[];
  discovery_id?: string;
}

export interface CasebookPackage {
  id: string;
  payer: string;
  memberId: string;
  regimen: string;
  status: string;
  lines: number;
  hasEligibility: boolean;
  createdAt: string;
}

export interface Payer {
  payer_id: string;
  stedi_id?: string;
  name: string;
  aliases?: string[];
}

/* ---------------------------------------------------------------- calls */

export const api = {
  capabilities: () => get<Capabilities>("/capabilities"),

  cancerCenters: () => get<{ count: number; results: CancerCenter[] }>("/admin/cancer-centers"),
  createCancerCenter: (b: Record<string, unknown>) => post<CancerCenter>("/admin/cancer-centers", b),
  hospitals: (cancerCenterId?: string) =>
    get<{ count: number; results: Hospital[] }>(
      `/admin/hospitals${cancerCenterId ? `?cancer_center_id=${encodeURIComponent(cancerCenterId)}` : ""}`,
    ),
  createHospital: (b: Record<string, unknown>) => post<Hospital>("/admin/hospitals", b),

  ontadaStatus: () => get<OntadaStatus>("/ontada/status"),
  ontadaAuthorize: () => get<{ url: string; state: string }>("/ontada/authorize"),
  /** Finish a login by handing back the address the browser landed on — the
   *  registered redirect URI is an app that strips the query string. */
  ontadaComplete: (url: string) => post<OntadaStatus>("/ontada/complete", { url }),
  /** Exercise the refresh grant now, rather than waiting for the token to age out. */
  ontadaRefresh: () => post<OntadaStatus>("/ontada/refresh"),
  /** The practitioner's panel — how a caller finds the patient_id every other
   *  Ontada read needs. Portal login accounts are filtered out by default. */
  ontadaPatients: (q?: string, includeLogins = false) =>
    get<OntadaPatients>(`/ontada/patients${qp({ q, include_logins: includeLogins ? "true" : undefined })}`),
  ontadaRecord: (patientId?: string) =>
    get<Record<string, unknown>>(`/ontada/record${qp({ patient_id: patientId })}`),
  // The connection is provider-scoped, so every read names its patient. Without
  // patient_id the gateway drops the filter and answers for the whole store.
  ontadaFiles: (patientId: string) =>
    get<OntadaFileList>(`/ontada/files${qp({ patient_id: patientId })}`),
  /** Direct URL for an attachment's bytes. The backend proxies it, because the
   *  browser holds no Ontada token and a redirect to the FHIR server would 401. */
  ontadaFileUrl: (binaryId: string, download = false) =>
    `${API_BASE}/ontada/file/${encodeURIComponent(binaryId)}${download ? "?download=true" : ""}`,
  /** `casebookId` lets a hand-entered stage count towards the gaps; the value
   *  comes back marked `entered by hand`, never as something the chart said. */
  ontadaSummary: (patientId: string, casebookId?: string) =>
    get<ClinicalSummary>(`/ontada/summary${qp({ patient_id: patientId, casebook_id: casebookId })}`),
  ontadaResource: (resourceType: string, patientId: string) =>
    get<{ resourceType: string; count: number; items: FhirResource[]; withheld_note?: string | null }>(
      `/ontada/resource/${encodeURIComponent(resourceType)}${qp({ patient_id: patientId })}`,
    ),
  ontadaEverything: (patientId?: string) =>
    get<{ counts: Record<string, number>; pages: number }>(
      `/ontada/everything${qp({ patient_id: patientId })}`,
    ),
  ontadaImport: (patientId?: string) =>
    post<{
      casebook_id: string;
      created: boolean;
      package_id: string | null;
      counts: Record<string, number>;
      coverage: { payer_name: string; member_id: string; group_number: string };
      unmapped: string[];
    }>(`/ontada/import${qp({ patient_id: patientId })}`),

  payers: (q: string) => get<{ count: number; results: Payer[] }>(`/payers?q=${encodeURIComponent(q)}`),

  casebooks: () => get<{ count: number; results: Casebook[] }>("/casebooks"),
  casebook: (id: string) => get<Casebook & { fhirSnapshot: Record<string, unknown> }>(`/casebooks/${id}`),
  createCasebook: (b: Record<string, unknown>) => post<Casebook>("/casebooks", b),
  /** Correct a casebook by hand — stage above all, which no Ontada Condition carries. */
  updateCasebook: (id: string, patch: Record<string, unknown>) =>
    request<Casebook>(`/casebooks/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  casebookPackages: (id: string) =>
    get<{ count: number; results: CasebookPackage[] }>(`/casebooks/${id}/packages`),
  discoverCoverage: (id: string) => post<CoverageDiscovery>(`/casebooks/${id}/discover-coverage`),

  packages: () => get<{ count: number; results: PreAuthPackage[] }>("/preauth"),
  package: (id: string) => get<PreAuthPackage>(`/preauth/${id}`),
  createPackage: (b: Record<string, unknown>) => post<PreAuthPackage>("/preauth", b),
  runCoverage: (id: string) =>
    post<{ package: PreAuthPackage; benefits: ParsedBenefits; estimate: Estimate; mode: string }>(
      `/preauth/${id}/coverage`,
    ),
  packageBenefits: (id: string, network = "in") =>
    get<{ benefits: ParsedBenefits; estimate: Estimate; source: { kind: string; file?: string } }>(
      `/preauth/${id}/benefits?network=${network}`,
    ),
  updatePackageLines: (id: string, lines: PreAuthLine[]) =>
    post<PreAuthPackage>(`/preauth/${id}/lines`, { lines }),

  policyForm: (insurer: string, payerId = "", planType = "") =>
    get<PolicyForm>(
      `/eligibility/form?insurer=${encodeURIComponent(insurer)}&payer_id=${encodeURIComponent(payerId)}&plan_type=${encodeURIComponent(planType)}`,
    ),
  replays: () => get<{ count: number; results: Replay[] }>("/eligibility/replays"),
  runEligibility: (body: Record<string, unknown>) =>
    post<{ source: { kind: string }; benefits: ParsedBenefits; estimate?: Estimate }>("/eligibility/run", body),
  submitPackage: (id: string) => post<never>(`/preauth/${id}/submit`),
};
