"use client";

import Link from "next/link";
import { ArrowRight, ClipboardCheck, FolderOpen, PlugZap, Users } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { StatTile } from "@/components/ehr/StatTile";
import { Card, SectionCard } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, formatUSD } from "@/lib/utils";

export default function OverviewPage() {
  const caps = useApi(() => api.capabilities(), []);
  const centers = useApi(() => api.cancerCenters(), []);
  const casebooks = useApi(() => api.casebooks(), []);
  const packages = useApi(() => api.packages(), []);
  const ontada = useApi(() => api.ontadaStatus(), []);

  // A dead backend is one fact, not five identical errors.
  const fatal = caps.error ?? centers.error ?? casebooks.error ?? packages.error;
  if (fatal?.code === "backend_unreachable") {
    return (
      <PageShell>
        <PageHeader title="Overview" />
        <Card><ErrorState error={fatal} onRetry={() => { caps.reload(); centers.reload(); casebooks.reload(); packages.reload(); }} /></Card>
      </PageShell>
    );
  }

  const cbs = casebooks.data?.results ?? [];
  const pkgs = packages.data?.results ?? [];
  const priced = pkgs.filter((p) => p.lines.some((l) => l.patient_estimate_cents != null));
  const exposure = pkgs.reduce(
    (n, p) => n + p.lines.reduce((m, l) => m + (l.patient_estimate_cents ?? 0), 0),
    0,
  );
  const loading = caps.loading || casebooks.loading || packages.loading;
  const connected = ontada.data?.connected && !ontada.data?.expired;

  const activity = pkgs
    .flatMap((p) => p.events.map((e) => ({ ...e, casebookId: p.casebookId, patientName: p.patientName })))
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, 6);

  return (
    <PageShell>
      <PageHeader
        title="Overview"
        subtitle={centers.data?.results[0]?.name ?? undefined}
      />

      {loading ? (
        <LoadingSkeleton count={3} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatTile
              label="Casebooks"
              value={cbs.length}
              icon={<FolderOpen className="h-[18px] w-[18px]" strokeWidth={1.75} />}
              tone="brand"
            />
            <StatTile
              label="Bound to Ontada"
              value={cbs.filter((c) => c.ontadaFhirId).length}
              icon={<Users className="h-[18px] w-[18px]" strokeWidth={1.75} />}
              tone="success"
            />
            <StatTile
              label="Pre-auth packages"
              value={pkgs.length}
              hint={priced.length > 0 ? `${priced.length} priced` : undefined}
              icon={<ClipboardCheck className="h-[18px] w-[18px]" strokeWidth={1.75} />}
              tone="warning"
            />
            <StatTile label="Patient exposure (est.)" value={formatUSD(exposure)} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <SectionCard title="Recent activity" className="xl:col-span-2" flush>
              {activity.length === 0 ? (
                <EmptyState
                  title="No activity yet"
                  description="Coverage checks and package events appear here."
                />
              ) : (
                <ul className="divide-y divide-[var(--ink-50)]">
                  {activity.map((e) => (
                    <li key={e.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-4 py-3 sm:px-5">
                      <span className="shrink-0 font-mono text-[11px] text-[var(--ink-300)]">
                        {formatDateTime(e.at)}
                      </span>
                      <Link
                        href={`/ehr/casebooks/${e.casebookId}`}
                        className="shrink-0 text-[13px] font-semibold text-[var(--teal-600)] hover:underline"
                      >
                        {e.patientName}
                      </Link>
                      <span className="min-w-0 text-[13px] text-[var(--ink-700)]">{e.action}</span>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>

            <SectionCard
              title="Integrations"
              icon={<PlugZap className="h-4 w-4" strokeWidth={1.75} />}
              action={
                <Link href="/ehr/admin/connections" className="text-xs font-semibold text-[var(--teal-600)] hover:underline">
                  Manage
                </Link>
              }
            >
              <div className="space-y-3">
                <Row label="Ontada iKnowMed" value={<StatusChip status={connected ? "connected" : "disconnected"} />} />
                <Row
                  label="Stedi"
                  value={
                    caps.data ? (
                      <Chip tone={caps.data.stedi.mode === "production" ? "danger" : "warning"}>
                        {caps.data.stedi.mode}
                      </Chip>
                    ) : null
                  }
                />
                <Row label="Prior auth 278" value={<Chip tone="neutral">Unavailable</Chip>} />
                <Row label="CancerAI / Digital Twin" value={<Chip tone="neutral">Not wired</Chip>} />
              </div>
              {!connected && (
                <Link href="/ehr/connect" className="mt-3 inline-flex items-center gap-1 text-[13px] font-semibold text-[var(--teal-600)] hover:underline">
                  Connect Ontada
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </SectionCard>
          </div>
        </>
      )}
    </PageShell>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[13px] text-[var(--ink-500)]">{label}</span>
      {value}
    </div>
  );
}
