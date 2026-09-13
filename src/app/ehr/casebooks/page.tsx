"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, ChevronRight, FolderOpen, Plus } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { SearchBar } from "@/components/ui/SearchBar";
import { api, type Casebook } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { formatDate, pluralize } from "@/lib/utils";

export default function CasebooksPage() {
  const [query, setQuery] = React.useState("");
  const casebooks = useApi(() => api.casebooks(), []);
  const rows = casebooks.data?.results ?? [];

  const results = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((c) =>
      [c.patientName, c.mrn, c.id, c.primaryDiagnosis, c.oncologist].some((v) =>
        (v ?? "").toLowerCase().includes(q),
      ),
    );
  }, [rows, query]);

  return (
    <PageShell>
      <PageHeader
        title="Casebooks"
        subtitle={casebooks.loading ? "Loading…" : pluralize(rows.length, "casebook")}
        actions={
          <Link href="/ehr/casebooks/new">
            <Button>
              <Plus className="h-4 w-4" />
              New casebook
            </Button>
          </Link>
        }
      />

      <SearchBar value={query} onChange={setQuery} placeholder="Search by patient, MRN or diagnosis…" />

      {casebooks.loading && <LoadingSkeleton count={4} />}
      {casebooks.error && <Card><ErrorState error={casebooks.error} onRetry={casebooks.reload} /></Card>}

      {!casebooks.loading && !casebooks.error && results.length === 0 && (
        <Card>
          <EmptyState
            title={rows.length === 0 ? "No casebooks yet" : "No casebooks match"}
            description={
              rows.length === 0
                ? "Casebooks are created from a patient record. Connect Ontada first, or create one manually."
                : undefined
            }
            icon={<FolderOpen className="h-5 w-5" strokeWidth={1.75} />}
            action={
              rows.length === 0 ? (
                <Link href="/ehr/casebooks/new">
                  <Button size="sm">New casebook</Button>
                </Link>
              ) : undefined
            }
          />
        </Card>
      )}

      {results.length > 0 && (
        <div className="space-y-2.5">
          {results.map((cb) => (
            <CasebookRow key={cb.id} casebook={cb} />
          ))}
        </div>
      )}
    </PageShell>
  );
}

function CasebookRow({ casebook: cb }: { readonly casebook: Casebook }) {
  const resources = Object.values(cb.resourceCounts ?? {}).reduce((a, b) => a + b, 0);

  return (
    <Link
      href={`/ehr/casebooks/${cb.id}`}
      className="group block rounded-[var(--radius)] border border-[var(--ink-100)] bg-white p-4 transition-all hover:border-[var(--teal-500)] hover:shadow-[var(--shadow)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="truncate text-[15px] font-bold text-[var(--ink-900)]">{cb.patientName}</span>
            {cb.mrn && <span className="shrink-0 font-mono text-[11px] text-[var(--ink-300)]">{cb.mrn}</span>}
          </div>

          {cb.primaryDiagnosis && (
            <p className="mt-1.5 truncate text-sm font-medium text-[var(--ink-700)]">
              {cb.primaryDiagnosis}
              {cb.diagnosisCode && (
                <span className="ml-1.5 font-mono text-[12px] font-normal text-[var(--ink-400)]">
                  {cb.diagnosisCode}
                </span>
              )}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--ink-400)]">
            {cb.oncologist && <span className="truncate">{cb.oncologist}</span>}
            {cb.stage && <span>Stage {cb.stage}</span>}
            <span>Updated {formatDate(cb.updatedAt)}</span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {cb.ontadaFhirId ? (
              <Chip tone="brand" className="font-mono text-[10px]">{cb.ontadaFhirId}</Chip>
            ) : (
              <Chip tone="warning" icon={<AlertTriangle className="h-3 w-3" />}>No Ontada record</Chip>
            )}
            {resources > 0 && <Chip tone="neutral">{pluralize(resources, "FHIR resource")}</Chip>}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <StatusChip status={cb.status} />
          <ChevronRight className="h-4 w-4 text-[var(--ink-300)] transition-colors group-hover:text-[var(--teal-600)]" />
        </div>
      </div>
    </Link>
  );
}
