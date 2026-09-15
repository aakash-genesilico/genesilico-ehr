"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Database, Link2, RefreshCw, Sparkles, TriangleAlert, User } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { StageRail, type StageItem, type StageState } from "@/components/ehr/StageRail";
import { BenefitsView } from "@/components/ehr/BenefitsView";
import { ClinicalSummaryView } from "@/components/ehr/ClinicalSummary";
import { FilesView } from "@/components/ehr/FilesView";
import { ResourceViewer } from "@/components/ehr/ResourceViewer";
import { CoverageStage } from "@/components/ehr/stages/CoverageStage";
import { EstimateStage, LinesStage, SubmissionStage } from "@/components/ehr/stages/PackageStages";
import { Button } from "@/components/ui/Button";
import { Card, KeyValue, SectionCard } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { Select } from "@/components/ui/Field";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api, type PreAuthLine } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { formatDate, formatDateTime, formatUSD } from "@/lib/utils";

/* One patient, start to finish. The clinical record and the authorisation are
   the same piece of work, so they are the same screen rather than two. */
const STAGES = [
  { key: "patient", label: "Patient" },
  { key: "ehr", label: "EHR record" },
  { key: "coverage", label: "Coverage" },
  { key: "lines", label: "Lines" },
  { key: "benefits", label: "Benefits" },
  { key: "estimate", label: "Estimate" },
  { key: "submission", label: "Submission" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

export default function PatientWorkspacePage() {
  const params = useParams<{ casebookId: string }>();
  const id = params.casebookId;

  const cb = useApi(() => api.casebook(id), [id]);
  const pkgs = useApi(() => api.casebookPackages(id), [id]);
  const pkg = pkgs.data?.results[0] ?? null;

  const [network, setNetwork] = React.useState("in");
  const ben = useApi(
    () => (pkg ? api.packageBenefits(pkg.id, network) : Promise.resolve(null)),
    [pkg?.id, network],
  );
  const full = useApi(() => (pkg ? api.package(pkg.id) : Promise.resolve(null)), [pkg?.id]);

  const [stage, setStage] = React.useState<StageKey>("patient");
  // Which resource-count chip is expanded. Null means none.
  const [openResource, setOpenResource] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);
  const [runError, setRunError] = React.useState<string | null>(null);

  const benefits = ben.data?.benefits ?? null;
  const estimate = ben.data?.estimate ?? null;

  const runCoverage = async () => {
    if (!pkg) return;
    setRunning(true);
    setRunError(null);
    try {
      await api.runCoverage(pkg.id);
      ben.reload();
      full.reload();
      setStage("benefits");
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const saveLines = async (lines: PreAuthLine[]) => {
    if (!pkg) return;
    await api.updatePackageLines(pkg.id, lines);
    ben.reload();
    full.reload();
  };

  if (cb.loading) return <PageShell><LoadingSkeleton count={4} /></PageShell>;
  if (cb.error) return <PageShell><Card><ErrorState error={cb.error} onRetry={cb.reload} /></Card></PageShell>;
  if (!cb.data) return null;

  const c = cb.data;
  const resourceCount = Object.values(c.resourceCounts ?? {}).reduce((a, b) => a + b, 0);
  // ontadaFhirId is stored as "Patient/<id>"; every read wants the bare id.
  const fhirPatientId = c.ontadaFhirId?.split("/").pop() ?? "";

  // Stage state is derived from what the patient's record actually contains,
  // so the rail reads as progress rather than decoration.
  const state = (k: StageKey): StageState => {
    if (k === stage) return "active";
    switch (k) {
      case "patient": return "complete";
      case "ehr": return c.ontadaFhirId ? "complete" : "blocked";
      case "coverage": return pkg?.memberId ? "complete" : "pending";
      case "lines": return (full.data?.lines.length ?? 0) > 0 ? "complete" : "pending";
      case "benefits":
      case "estimate": return benefits ? "complete" : "pending";
      case "submission": return "pending";
    }
  };
  const stages: StageItem[] = STAGES.map((s) => ({ key: s.key, label: s.label, state: state(s.key) }));

  return (
    <PageShell>
      <PageHeader
        title={c.patientName}
        backHref="/ehr/casebooks"
        backLabel="Casebooks"
        subtitle={[c.primaryDiagnosis, c.stage && `Stage ${c.stage}`, pkg?.regimen].filter(Boolean).join(" · ") || undefined}
        meta={
          <>
            {/* The status alone says something is missing but not what, and the
                answer is one short list — so it rides along as a tooltip. */}
            <span title={c.gapFields?.length ? `Still missing: ${c.gapFields.join(", ")}` : undefined}>
              <StatusChip status={c.status} />
            </span>
            {c.gapFields && c.gapFields.length > 0 && (
              <Chip tone="warning">missing: {c.gapFields.join(", ")}</Chip>
            )}
            {c.mrn && <Chip tone="neutral" className="font-mono text-[10px]">{c.mrn}</Chip>}
            {pkg && <Chip tone="brand">{pkg.payer}</Chip>}
            {!c.ontadaFhirId && <Chip tone="warning">No Ontada record</Chip>}
          </>
        }
        actions={
          pkg && (
            <Button onClick={runCoverage} disabled={running}>
              <RefreshCw className={running ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              {running ? "Checking…" : "Run coverage check"}
            </Button>
          )
        }
      />

      {runError && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--red-100)] bg-[var(--red-50)] px-4 py-3 text-sm text-[var(--red-700)]">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{runError}</span>
        </div>
      )}

      <StageRail stages={stages} activeKey={stage} onSelect={(k) => setStage(k as StageKey)} />

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          {stage === "patient" && (
            <SectionCard title="Patient" icon={<User className="h-4 w-4" strokeWidth={1.75} />}>
              <dl className="grid gap-x-8 sm:grid-cols-2">
                <div>
                  <KeyValue label="Name">{c.patientName}</KeyValue>
                  <KeyValue label="Date of birth">{c.birthDate || "Not recorded"}</KeyValue>
                  <KeyValue label="Gender">{c.gender || "Not recorded"}</KeyValue>
                  <KeyValue label="MRN" mono>{c.mrn || "—"}</KeyValue>
                </div>
                <div>
                  <KeyValue label="Primary diagnosis">{c.primaryDiagnosis || "Not recorded"}</KeyValue>
                  <KeyValue label="ICD-10-CM" mono>{c.diagnosisCode || "—"}</KeyValue>
                  <KeyValue label="Stage">
                    <StageField casebookId={c.id} value={c.stage} onSaved={cb.reload} />
                  </KeyValue>
                  <KeyValue label="Oncologist">{c.oncologist || "Not recorded"}</KeyValue>
                </div>
              </dl>
            </SectionCard>
          )}

          {/* The summary leads; the resource inventory follows it. A reviewer
              needs the clinical picture first and the raw counts only when
              something in it needs checking. */}
          {stage === "ehr" && fhirPatientId && (
            <>
              <ClinicalSummaryView patientId={fhirPatientId} casebookId={c.id} />
              <FilesView patientId={fhirPatientId} />
            </>
          )}

          {stage === "ehr" && (
            <SectionCard title="EHR record" icon={<Database className="h-4 w-4" strokeWidth={1.75} />}>
              {c.ontadaFhirId ? (
                <>
                  <dl>
                    <KeyValue label="FHIR Patient id" mono>{c.ontadaFhirId}</KeyValue>
                    <KeyValue label="Resources pulled">{resourceCount}</KeyValue>
                  </dl>
                  <p className="mt-3 text-xs text-[var(--ink-400)]">
                    Raw resources — select one to read what was pulled.
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {Object.entries(c.resourceCounts ?? {}).map(([r, n]) => {
                      const selected = openResource === r;
                      return (
                        <button
                          key={r}
                          type="button"
                          disabled={n === 0}
                          aria-pressed={selected}
                          onClick={() => setOpenResource(selected ? null : r)}
                          className="rounded-full disabled:cursor-default enabled:cursor-pointer enabled:hover:opacity-80"
                        >
                          <Chip
                            tone={selected ? "ai" : n > 0 ? "brand" : "neutral"}
                            className={selected ? "ring-1 ring-[var(--ai-700)]" : undefined}
                          >
                            {r}<span className="tabular-nums text-[var(--ink-300)]">{n}</span>
                          </Chip>
                        </button>
                      );
                    })}
                  </div>
                  {openResource && fhirPatientId && (
                    <ResourceViewer
                      resourceType={openResource}
                      patientId={fhirPatientId}
                      expectedCount={c.resourceCounts?.[openResource] ?? 0}
                      onClose={() => setOpenResource(null)}
                    />
                  )}
                </>
              ) : (
                <EmptyState
                  title="Not bound to an Ontada record"
                  description="Diagnosis, stage, labs and prior therapy have to be entered by hand until the EHR is connected."
                  icon={<Link2 className="h-5 w-5" strokeWidth={1.75} />}
                  action={
                    <Link href="/ehr/connect">
                      <Button size="sm" variant="secondary">Go to Ontada Connect</Button>
                    </Link>
                  }
                />
              )}
            </SectionCard>
          )}

          {stage === "coverage" && <CoverageStage casebookId={id} pkg={pkg} />}

          {stage === "lines" && (
            pkg ? (
              <LinesStage
                lines={full.data?.lines ?? []}
                tiers={benefits?.drug_tiers ?? []}
                onSave={saveLines}
              />
            ) : <NoPackage />
          )}

          {stage === "benefits" && (
            pkg ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-[13px] text-[var(--ink-500)]">Network</span>
                  <div className="w-40">
                    <Select value={network} onChange={(e) => setNetwork(e.target.value)}>
                      <option value="in">In network</option>
                      <option value="out">Out of network</option>
                    </Select>
                  </div>
                </div>
                {ben.loading && <LoadingSkeleton count={3} />}
                {ben.error && <Card><ErrorState error={ben.error} onRetry={ben.reload} /></Card>}
                {benefits && <BenefitsView benefits={benefits} network={network} />}
              </>
            ) : <NoPackage />
          )}

          {stage === "estimate" && (pkg ? <EstimateStage estimate={estimate} /> : <NoPackage />)}
          {stage === "submission" && <SubmissionStage packageId={pkg?.id ?? null} />}
        </div>

        <div className="space-y-4">
          <SectionCard title="This patient">
            <dl>
              <KeyValue label="Casebook" mono>{c.id}</KeyValue>
              <KeyValue label="Created">{formatDate(c.createdAt)}</KeyValue>
              <KeyValue label="Updated">{formatDateTime(c.updatedAt)}</KeyValue>
              {pkg && <KeyValue label="Package" mono>{pkg.id}</KeyValue>}
              {pkg && <KeyValue label="Member ID" mono>{pkg.memberId || "—"}</KeyValue>}
            </dl>
            {estimate && (
              <div className="mt-4 space-y-2 border-t border-[var(--ink-50)] pt-4">
                <Row label="Billed" value={formatUSD(estimate.totals.billed_cents)} />
                <Row label="Patient (est.)" value={formatUSD(estimate.totals.patient_estimate_cents)} warn />
                {estimate.oop_remaining != null && (
                  <Row label="OOP remaining" value={`$${estimate.oop_remaining.toLocaleString()}`} />
                )}
              </div>
            )}
          </SectionCard>

          <SectionCard title="CancerAI & Digital Twin" icon={<Sparkles className="h-4 w-4" strokeWidth={1.75} />}>
            <p className="text-[13px] leading-relaxed text-[var(--ink-400)]">
              Scores come from gSage. No endpoint is connected to this module, so no confidence or
              efficacy value is shown.
            </p>
          </SectionCard>
        </div>
      </div>
    </PageShell>
  );
}

function NoPackage() {
  return (
    <Card>
      <EmptyState
        title="No pre-auth package for this patient"
        description="A package holds the billable lines and the payer response."
        action={
          <Link href="/ehr/preauth">
            <Button size="sm">Create one</Button>
          </Link>
        }
      />
    </Card>
  );
}

function Row({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[13px] text-[var(--ink-500)]">{label}</span>
      <span className={`text-sm font-bold tabular-nums ${warn ? "text-[var(--amber-700)]" : "text-[var(--ink-900)]"}`}>
        {value}
      </span>
    </div>
  );
}


/* Ontada carries no stage on any Condition — not in `Condition.stage`, not in a
   staging extension, and not as a TNM observation; it lives in the pathology
   PDF. A payer's medical-necessity criteria are stage-specific, so the summary
   reports its absence as a gap. This is the only way that gap can be closed,
   and what is typed here is labelled `entered by hand` wherever it appears. */
function StageField({
  casebookId,
  value,
  onSaved,
}: {
  readonly casebookId: string;
  readonly value: string;
  readonly onSaved: () => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(value);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => setDraft(value), [value]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateCasebook(casebookId, { stage: draft.trim() });
      setEditing(false);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <span>{value || "Not recorded"}</span>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-[12px] font-semibold text-[var(--teal-600)] hover:underline"
        >
          {value ? "Edit" : "Enter stage"}
        </button>
      </span>
    );
  }

  return (
    <span className="flex flex-wrap items-center gap-2">
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void save();
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
        placeholder="e.g. IIIB"
        className="w-28 rounded-[var(--radius-sm)] border border-[var(--ink-200)] bg-white px-2 py-1 text-[13px] outline-none focus:border-[var(--teal-600)]"
      />
      <Button size="sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
      <button
        type="button"
        onClick={() => { setDraft(value); setEditing(false); }}
        className="text-[12px] text-[var(--ink-400)] hover:underline"
      >
        Cancel
      </button>
      {error && <span className="text-[12px] text-[var(--red-700)]">{error}</span>}
    </span>
  );
}
