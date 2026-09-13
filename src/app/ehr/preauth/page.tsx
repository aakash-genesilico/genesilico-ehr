"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronRight, ClipboardCheck, Plus } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { SearchBar } from "@/components/ui/SearchBar";
import { NewPackageModal } from "@/components/ehr/NewPackageModal";
import { api, type PreAuthPackage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { formatUSD, pluralize } from "@/lib/utils";

export default function PreAuthConsolePage() {
  const [query, setQuery] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const packages = useApi(() => api.packages(), []);
  const casebooks = useApi(() => api.casebooks(), []);
  const rows = packages.data?.results ?? [];

  const results = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((p) =>
      [p.patientName, p.mrn, p.id, p.regimen, p.payer].some((v) => (v ?? "").toLowerCase().includes(q)),
    );
  }, [rows, query]);

  return (
    <PageShell>
      <PageHeader
        title="Pre-Auth"
        subtitle={packages.loading ? "Loading…" : pluralize(rows.length, "package")}
        actions={
          <Button onClick={() => setCreating(true)} disabled={(casebooks.data?.results.length ?? 0) === 0}>
            <Plus className="h-4 w-4" />
            New package
          </Button>
        }
      />

      <SearchBar value={query} onChange={setQuery} placeholder="Search by patient, payer or regimen…" />

      {packages.loading && <LoadingSkeleton count={3} />}
      {packages.error && <Card><ErrorState error={packages.error} onRetry={packages.reload} /></Card>}

      {!packages.loading && !packages.error && results.length === 0 && (
        <Card>
          <EmptyState
            title={rows.length === 0 ? "No packages yet" : "No packages match"}
            description={
              rows.length === 0
                ? "A package is built from a casebook, then priced against the payer's real benefit response."
                : undefined
            }
            icon={<ClipboardCheck className="h-5 w-5" strokeWidth={1.75} />}
          />
        </Card>
      )}

      {results.length > 0 && (
        <div className="space-y-2.5">
          {results.map((pkg) => (
            <PackageRow key={pkg.id} pkg={pkg} />
          ))}
        </div>
      )}

      <NewPackageModal
        open={creating}
        onClose={() => setCreating(false)}
        casebooks={casebooks.data?.results ?? []}
        onCreated={packages.reload}
      />
    </PageShell>
  );
}

function PackageRow({ pkg }: { readonly pkg: PreAuthPackage }) {
  const billed = pkg.lines.reduce((n, l) => n + (l.billed_cents ?? 0), 0);
  const known = pkg.lines.filter((l) => l.patient_estimate_cents != null);
  const patient = known.reduce((n, l) => n + (l.patient_estimate_cents ?? 0), 0);
  const unknown = pkg.lines.length - known.length;

  return (
    <Link
      href={`/ehr/casebooks/${pkg.casebookId}`}
      className="group block rounded-[var(--radius)] border border-[var(--ink-100)] bg-white p-4 transition-all hover:border-[var(--teal-500)] hover:shadow-[var(--shadow)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-[14rem] flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[15px] font-bold text-[var(--ink-900)]">{pkg.patientName}</span>
            {pkg.mrn && <span className="font-mono text-[11px] text-[var(--ink-300)]">{pkg.mrn}</span>}
            <span className="font-mono text-[11px] text-[var(--ink-300)]">{pkg.id}</span>
          </div>
          {pkg.regimen && <p className="mt-1 truncate text-sm font-medium text-[var(--ink-700)]">{pkg.regimen}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--ink-400)]">
            {pkg.payer && <span>{pkg.payer}</span>}
            {pkg.memberId && <span className="font-mono text-[12px]">{pkg.memberId}</span>}
            <span>{pluralize(pkg.lines.length, "line")}</span>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <StatusChip status={pkg.status} />
          {unknown > 0 && <Chip tone="neutral">{unknown} not priced</Chip>}
          <ChevronRight className="h-4 w-4 text-[var(--ink-300)] transition-colors group-hover:text-[var(--teal-600)]" />
        </div>
      </div>

      <dl className="mt-3 flex flex-wrap gap-6 border-t border-[var(--ink-50)] pt-3">
        <div>
          <dt className="text-[11px] text-[var(--ink-400)]">Billed</dt>
          <dd className="text-sm font-bold tabular-nums text-[var(--ink-900)]">{formatUSD(billed)}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-[var(--ink-400)]">Patient estimate</dt>
          <dd className="text-sm font-bold tabular-nums text-[var(--ink-700)]">
            {known.length === 0 ? "Not run" : formatUSD(patient)}
          </dd>
        </div>
      </dl>
    </Link>
  );
}
