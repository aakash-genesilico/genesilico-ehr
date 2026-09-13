"use client";

import * as React from "react";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, Database, Download, ExternalLink, PlugZap, RefreshCw, TriangleAlert } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, KeyValue, SectionCard } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { formatDateTime } from "@/lib/utils";

function ConnectPageBody() {
  const params = useSearchParams();
  const status = useApi(() => api.ontadaStatus(), []);
  const [launching, setLaunching] = React.useState(false);
  const [launchError, setLaunchError] = React.useState<string | null>(null);

  const connected = status.data?.connected && !status.data?.expired;
  const callbackError = params?.get("ontada_error");

  const startLaunch = async () => {
    setLaunching(true);
    setLaunchError(null);
    try {
      const { url } = await api.ontadaAuthorize();
      // The gateway sits behind a WAF that rejects non-browser clients, so the
      // redirect has to happen in a real tab.
      window.location.href = url;
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : String(e));
      setLaunching(false);
    }
  };

  return (
    <PageShell>
      <PageHeader
        title="Ontada Connect"
        subtitle={status.data?.fhir_base ?? undefined}
        meta={status.data ? <StatusChip status={connected ? "connected" : "disconnected"} /> : undefined}
        actions={
          <>
            <Button variant="secondary" onClick={status.reload}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
            <Button onClick={startLaunch} disabled={launching || !status.data?.configured}>
              <ExternalLink className="h-4 w-4" />
              {launching ? "Opening…" : connected ? "Re-authorize" : "Connect to Ontada"}
            </Button>
          </>
        }
      />

      {callbackError && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--red-100)] bg-[var(--red-50)] px-4 py-3 text-sm text-[var(--red-700)]">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{callbackError}</span>
        </div>
      )}
      {params?.get("ontada_connected") && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--green-100)] bg-[var(--green-50)] px-4 py-3 text-sm text-[var(--green-700)]">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Authorization complete. The record below is live from iKnowMed.</span>
        </div>
      )}
      {launchError && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--red-100)] bg-[var(--red-50)] px-4 py-3 text-sm text-[var(--red-700)]">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{launchError}</span>
        </div>
      )}

      {status.loading && <LoadingSkeleton count={2} />}
      {status.error && <Card><ErrorState error={status.error} onRetry={status.reload} /></Card>}

      {status.data && (
        <>
          <SectionCard title="Connection" icon={<PlugZap className="h-4 w-4" strokeWidth={1.75} />}>
            <dl>
              <KeyValue label="FHIR base" mono>{status.data.fhir_base ?? "Not configured"}</KeyValue>
              <KeyValue label="Grant types">{status.data.grant_types.join(", ")}</KeyValue>
              <KeyValue label="Launch context">{status.data.launch_context}</KeyValue>
              <KeyValue label="Connected">
                {status.data.connected
                  ? `Yes — token ${status.data.expired ? "expired" : `valid to ${formatDateTime(status.data.expires_at)}`}`
                  : (status.data.reason ?? "No")}
              </KeyValue>
              {status.data.patient_context && (
                <KeyValue label="Patient context" mono>{status.data.patient_context}</KeyValue>
              )}
            </dl>
          </SectionCard>

          {/* Rendered only when the backend says panel search is unavailable,
              and it prints the backend's own measured reason rather than a
              hardcoded one — the answer changed once already when the Ontada
              grant was widened, and a duplicated claim here would have gone
              stale silently. */}
          {!status.data.panel_search_supported && (
            <SectionCard title="Panel search">
              <p className="text-[13px] leading-relaxed text-[var(--ink-500)]">
                {status.data.panel_search_reason}
              </p>
            </SectionCard>
          )}

          {connected ? <PatientRecord /> : null}
        </>
      )}
    </PageShell>
  );
}

function PatientRecord() {
  const record = useApi(() => api.ontadaRecord(), []);
  const router = useRouter();
  const [importing, setImporting] = React.useState(false);
  const [importError, setImportError] = React.useState<string | null>(null);

  const runImport = async () => {
    setImporting(true);
    setImportError(null);
    try {
      const res = await api.ontadaImport();
      router.push(`/ehr/casebooks/${res.casebook_id}`);
    } catch (e) {
      setImportError(e instanceof Error ? e.message : String(e));
      setImporting(false);
    }
  };

  if (record.loading) return <LoadingSkeleton count={3} />;
  if (record.error) return <Card><ErrorState error={record.error as ApiError} onRetry={record.reload} /></Card>;
  if (!record.data) return null;

  const data = record.data as {
    patient?: Record<string, unknown>;
    counts?: Record<string, number>;
    errors?: Record<string, string>;
    withheld_note?: string;
  };
  const patient = (data.patient ?? {}) as {
    id?: string;
    birthDate?: string;
    gender?: string;
    name?: Array<{ given?: string[]; family?: string }>;
  };
  const name = patient.name?.[0];

  return (
    <>
      <SectionCard title="Authorized patient" icon={<Database className="h-4 w-4" strokeWidth={1.75} />}>
        <dl>
          <KeyValue label="Name">
            {[name?.given?.join(" "), name?.family].filter(Boolean).join(" ") || "Not present in the resource"}
          </KeyValue>
          <KeyValue label="FHIR id" mono>{patient.id ?? "—"}</KeyValue>
          <KeyValue label="Date of birth">{patient.birthDate ?? "Not present"}</KeyValue>
          <KeyValue label="Gender">{patient.gender ?? "Not present"}</KeyValue>
        </dl>
      </SectionCard>

      {importError && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--red-100)] bg-[var(--red-50)] px-4 py-3 text-sm text-[var(--red-700)]">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{importError}</span>
        </div>
      )}

      <SectionCard
        title="Resources pulled"
        description="Live counts from iKnowMed"
        action={
          <Button size="sm" onClick={runImport} disabled={importing}>
            <Download className="h-3.5 w-3.5" />
            {importing ? "Importing…" : "Create casebook from this record"}
          </Button>
        }
      >
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(data.counts ?? {}).map(([res, n]) => (
            <Chip key={res} tone={n > 0 ? "brand" : "neutral"}>
              {res}
              <span className="tabular-nums text-[var(--ink-300)]">{n}</span>
            </Chip>
          ))}
        </div>
        {Object.keys(data.errors ?? {}).length > 0 && (
          <div className="mt-4 border-t border-[var(--ink-50)] pt-3">
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-400)]">
              Could not be read
            </p>
            <ul className="space-y-1">
              {Object.entries(data.errors ?? {}).map(([res, msg]) => (
                <li key={res} className="text-[13px] text-[var(--amber-700)]">
                  <span className="font-mono text-[12px]">{res}</span> — {msg}
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.withheld_note && (
          <p className="mt-3 text-[12px] leading-relaxed text-[var(--ink-400)]">{data.withheld_note}</p>
        )}
      </SectionCard>
    </>
  );
}

export default function ConnectPage() {
  return (
    <Suspense fallback={<PageShell><LoadingSkeleton count={3} /></PageShell>}>
      <ConnectPageBody />
    </Suspense>
  );
}
