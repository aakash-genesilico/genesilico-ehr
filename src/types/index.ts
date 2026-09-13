/* ================================================================
   Domain types for the GeneSilico EHR module.

   Shapes are drawn from the workflow these screens serve — Ontada
   (iKnowMed) → iCaseBook → CancerAI/DT → Pre-Auth → EHR submission —
   and, where the data comes off the wire as FHIR R4, they mirror the
   resource fields the connector will actually read. The backend pass
   These mirror the API responses in src/lib/api.ts.
   ================================================================ */

/* ---------------- Admin console ---------------- */

export interface CancerCenter {
  id: string;
  name: string;
  city: string;
  state: string;
  /** FHIR Organization.identifier — the tenant key on the EHR side. */
  organizationId: string;
  ehrVendor: EhrVendor;
  hospitalIds: string[];
  practitionerCount: number;
  patientCount: number;
  status: "active" | "onboarding" | "suspended";
  createdAt: string;
}

export interface Hospital {
  id: string;
  name: string;
  /** Owning cancer center. */
  cancerCenterId: string;
  city: string;
  state: string;
  /** CMS Certification Number / facility NPI, as the payer expects it. */
  npi: string;
  beds: number;
  type: "hospital" | "infusion-center" | "clinic";
  status: "active" | "onboarding" | "suspended";
}

export type EhrVendor = "ontada-ikm" | "epic" | "cerner" | "none";

export type ConnectionStatus = "connected" | "degraded" | "disconnected" | "not-configured";

export interface EhrConnection {
  id: string;
  label: string;
  vendor: EhrVendor;
  environment: "non-prod" | "production";
  /** FHIR R4 service base URL. */
  fhirBaseUrl: string;
  clientId: string;
  /** SMART scopes granted to the app registration. */
  scopes: string[];
  status: ConnectionStatus;
  lastHandshakeAt: string | null;
  tokenExpiresAt: string | null;
  cancerCenterId: string | null;
  /** Per-resource read support, as reported by the CapabilityStatement. */
  resources: FhirResourceSupport[];
}

export interface FhirResourceSupport {
  resource: string;
  supported: boolean;
  /** Records pulled during the last sync. */
  lastCount: number | null;
  note?: string;
}

/* ---------------- Ontada patient sync ---------------- */

export interface OntadaPatient {
  /** FHIR Patient.id on the Ontada gateway. */
  fhirId: string;
  mrn: string;
  firstName: string;
  lastName: string;
  birthDate: string;
  gender: "male" | "female" | "other" | "unknown";
  primaryDiagnosis: string;
  /** ICD-10-CM code for the primary diagnosis. */
  diagnosisCode: string;
  stage: string;
  attendingPractitioner: string;
  cancerCenterId: string;
  hospitalId: string;
  lastEncounter: string;
  payer: string;
  /** Whether this patient already has an iCaseBook entry. */
  linkedCasebookId: string | null;
  resourceCounts: Record<string, number>;
}

/* ---------------- Casebook ---------------- */

export type CasebookStatus =
  | "draft"
  | "ingesting"
  | "gaps-pending"
  | "ai-ready"
  | "plan-drafted"
  | "signed-off";

export interface Casebook {
  id: string;
  patientName: string;
  mrn: string;
  age: number;
  gender: string;
  primaryDiagnosis: string;
  diagnosisCode: string;
  stage: string;
  cancerCenterId: string;
  hospitalId: string;
  oncologist: string;
  status: CasebookStatus;
  /** Ontada FHIR Patient.id this casebook is bound to, if any. */
  ontadaFhirId: string | null;
  completeness: number;
  openGaps: number;
  ngsReports: number;
  updatedAt: string;
  createdAt: string;
}

export interface CompletenessGap {
  id: string;
  field: string;
  section: string;
  severity: "blocking" | "recommended";
  /** Where the value would come from once resolved. */
  source: "ontada-fhir" | "ngs-upload" | "manual" | "transcription";
  detail: string;
  resolved: boolean;
}

/* ---------------- Treatment plan & AI ---------------- */

export type PlanStatus = "in-review" | "signed-off" | "pre-auth-started" | "submitted" | "approved" | "denied";

export interface TreatmentPlan {
  id: string;
  casebookId: string;
  patientName: string;
  mrn: string;
  regimen: string;
  intent: "curative" | "adjuvant" | "neoadjuvant" | "palliative";
  cycles: number;
  lineOfTherapy: string;
  /** CancerAI artifact + Digital Twin efficacy score. */
  cancerAiConfidence: number;
  dtEfficacyScore: number;
  guideline: string;
  oncologist: string;
  signedOffAt: string | null;
  status: PlanStatus;
  cancerCenterId: string;
  lineItems: PlanLineItem[];
}

export interface PlanLineItem {
  id: string;
  description: string;
  /** HCPCS J-code, CPT, or NDC depending on the item. */
  code: string;
  codeSystem: "HCPCS" | "CPT" | "ICD-10-CM" | "NDC";
  units: number;
  unitCostCents: number;
  category: "drug" | "administration" | "imaging" | "lab" | "supportive";
}

/* ---------------- Pre-auth ---------------- */

export type PreAuthStage =
  | "plan"
  | "evidence"
  | "ehr"
  | "coding"
  | "coverage"
  | "financials"
  | "review"
  | "submission";

export type PreAuthStageState = "complete" | "active" | "blocked" | "pending";

export type CoverageDecision = "covered" | "partial" | "not-covered" | "prior-auth-required" | "pending";

export interface PreAuthPackage {
  id: string;
  planId: string;
  casebookId: string;
  patientName: string;
  mrn: string;
  regimen: string;
  payer: string;
  memberId: string;
  groupNumber: string;
  cancerCenterId: string;
  hospitalId: string;
  status: "drafting" | "manager-review" | "submitted" | "payer-review" | "approved" | "denied" | "appealed";
  createdAt: string;
  updatedAt: string;
  submittedAt: string | null;
  stages: Record<PreAuthStage, PreAuthStageState>;
  lines: PreAuthLine[];
  evidence: EvidenceItem[];
  events: PreAuthEvent[];
}

export interface PreAuthLine {
  id: string;
  description: string;
  code: string;
  codeSystem: "HCPCS" | "CPT" | "ICD-10-CM" | "NDC";
  units: number;
  billedCents: number;
  allowedCents: number;
  patientResponsibilityCents: number;
  decision: CoverageDecision;
  /** Payer's stated reason, verbatim, when the line is not fully covered. */
  payerNote?: string;
}

export interface EvidenceItem {
  id: string;
  title: string;
  kind: "treatment-plan" | "ngs-report" | "pathology" | "imaging" | "guideline" | "clinical-note" | "prior-therapy";
  source: "casebook" | "ontada-fhir" | "upload" | "cancerai";
  pages: number;
  attached: boolean;
  addedAt: string;
}

export interface PreAuthEvent {
  id: string;
  at: string;
  actor: string;
  action: string;
  detail?: string;
  kind: "info" | "success" | "warning" | "error";
}

/* ---------------- Shared UI ---------------- */

export interface NavItem {
  href: string;
  label: string;
  shortLabel: string;
  description: string;
}
