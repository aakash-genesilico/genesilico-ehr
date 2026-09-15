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
import { api, ApiError, type OntadaPatient } from "@/lib/api";
import { PatientPicker } from "@/components/ehr/PatientPicker";
import { useApi } from "@/hooks/useApi";
import { formatDateTime } from "@/lib/utils";

function ConnectPageBody() {
  const params = useSearchParams();
  const status = useApi(() => api.ontadaStatus(), []);
  const [launching, setLaunching] = React.useState(false);
  const [launchError, setLaunchError] = React.useState<string | null>(null);
  const [awaitingPaste, setAwaitingPaste] = React.useState(false);

  const connected = status.data?.connected && !status.data?.expired;
  const callbackError = params?.get("ontada_error");
  const reauthRequired = Boolean(status.data?.keeper?.reauth_required);

  const startLaunch = async () => {
    setLaunching(true);
    setLaunchError(null);
    try {
      const { url } = await api.ontadaAuthorize();
      // Open in a new tab rather than navigating away. The redirect lands on a
      // different app that cannot hand the code back, so this tab has to stay
      // alive to receive it — and the PKCE verifier only lives ten minutes.
      window.open(url, "_blank", "noopener,noreferrer");
      setAwaitingPaste(true);
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : String(e));
    } finally {
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

      {reauthRequired && !awaitingPaste && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--amber-100)] bg-[var(--amber-50)] px-4 py-3 text-sm text-[var(--amber-700)]">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Ontada rejected the stored grant{status.data?.keeper?.last_error ? ` — ${status.data.keeper.last_error}` : ""}.
            Retrying cannot fix it; sign in once more above. Records already imported stay readable.
          </span>
        </div>
      )}

      {awaitingPaste && (
        <FinishLogin
          onDone={() => {
            setAwaitingPaste(false);
            status.reload();
          }}
          onCancel={() => setAwaitingPaste(false)}
        />
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
              {/* Ontada rotates the refresh token on every renewal and publishes
                  no lifetime for it, so an idle grant simply dies. The backend
                  renews on a timer; showing it here is how anyone confirms the
                  connection is being held open rather than merely valid now. */}
              {status.data.keeper && (
                <KeyValue label="Auto-renewal">
                  {status.data.keeper.enabled
                    ? `On — every ${Math.round(status.data.keeper.every_seconds / 60)} min, renewing ${Math.round(
                        status.data.keeper.renews_at_t_minus_seconds / 60,
                      )} min before expiry` +
                      (status.data.keeper.last_refresh_at
                        ? ` · last ${formatDateTime(status.data.keeper.last_refresh_at)}`
                        : " · not yet needed") +
                      (status.data.keeper.refreshes ? ` · ${status.data.keeper.refreshes} so far` : "")
                    : "Off — the grant will die when the token expires"}
                </KeyValue>
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

/* The redirect URI registered with Ontada is a single-page app whose router
   drops the query string, so the browser cannot deliver `?code=` to us. Until
   that redirect points somewhere we own, finishing the login means handing the
   address back — which belongs here, in the app, rather than in a terminal. */
function FinishLogin({
  onDone,
  onCancel,
}: {
  readonly onDone: () => void;
  readonly onCancel: () => void;
}) {
  const [url, setUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.ontadaComplete(url.trim());
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard
      title="Finish connecting"
      description="Sign in on the Ontada tab, then bring the address back here"
      icon={<PlugZap className="h-4 w-4" strokeWidth={1.75} />}
    >
      <ol className="mb-3 space-y-1.5 text-[13px] leading-relaxed text-[var(--ink-500)]">
        <li>1. Sign in on the tab that just opened, and choose <strong>Until I revoke it</strong> when it asks how long to remember the decision.</li>
        <li>2. You will land on a page that looks unrelated and blanks its own address. If you missed it, open browser history — the entry keeps the full address.</li>
        <li>3. Paste that whole address below. It carries the one-time code, and it expires within a few minutes.</li>
      </ol>
      <input
        type="text"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && url.trim()) void submit(); }}
        placeholder="https://canceros.genesilico.ai/?code=…&state=…"
        className="w-full rounded-[var(--radius)] border border-[var(--ink-100)] bg-white px-3 py-2 font-mono text-[12px] text-[var(--ink-700)] outline-none focus:border-[var(--brand-400)]"
      />
      {error && (
        <p className="mt-2 flex items-start gap-2 text-[13px] text-[var(--red-700)]">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <Button onClick={submit} disabled={busy || !url.trim()}>
          {busy ? "Connecting…" : "Finish connecting"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </SectionCard>
  );
}

function PatientRecord() {
  // There is no "the" patient on a provider-scoped token: this connection sees
  // a whole panel, and every read has to name which chart it means. Asking
  // first is the fix for the 400 this panel used to show on arrival.
  const [picked, setPicked] = React.useState<OntadaPatient | null>(null);

  if (!picked) {
    return (
      <SectionCard
        title="Choose a patient"
        description="This connection reads a practitioner's whole panel, so a chart has to be named"
        icon={<Database className="h-4 w-4" strokeWidth={1.75} />}
      >
        <PatientPicker onSelect={setPicked} />
      </SectionCard>
    );
  }
  return <PatientRecordFor patient={picked} onChange={() => setPicked(null)} />;
}

function PatientRecordFor({
  patient: picked,
  onChange,
}: {
  readonly patient: OntadaPatient;
  readonly onChange: () => void;
}) {
  const record = useApi(() => api.ontadaRecord(picked.id), [picked.id]);
  const router = useRouter();
  const [importing, setImporting] = React.useState(false);
  const [importError, setImportError] = React.useState<string | null>(null);

  const runImport = async () => {
    setImporting(true);
    setImportError(null);
    try {
      const res = await api.ontadaImport(picked.id);
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
      <SectionCard
        title="Selected patient"
        icon={<Database className="h-4 w-4" strokeWidth={1.75} />}
        action={
          <Button size="sm" variant="secondary" onClick={onChange}>
            Choose another
          </Button>
        }
      >
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
