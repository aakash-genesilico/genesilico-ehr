"use client";

/**
 * The chart read as a clinical picture rather than a resource inventory.
 *
 * Counting resources tells a reviewer a chart exists. It does not tell them
 * what the patient has, what they are on, or whether the package can be
 * submitted — so this renders the three answers directly, and says plainly
 * where the chart is silent.
 *
 * Nothing here is generated or predicted. Every line comes from
 * services/clinical_summary.py, which assembles only from fields that are
 * present, so anything shown can be traced back to a resource.
 */

import * as React from "react";
import { Activity, FlaskConical, Paperclip, Pill, Stethoscope, TriangleAlert } from "lucide-react";
import { Card, SectionCard } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api, type ClinicalSummary as Summary } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

/** `active` on a problem means something different from `draft` on an order, so
 *  the tone map stays local rather than borrowing the domain status chips. */
function toneFor(status: string) {
  if (["active", "recurrence", "relapse", "final", "completed"].includes(status)) return "success";
  if (["draft", "on-hold", "unknown"].includes(status)) return "warning";
  if (["resolved", "cancelled", "stopped", "entered-in-error"].includes(status)) return "neutral";
  return "neutral";
}

export function ClinicalSummaryView({ patientId }: { readonly patientId: string }) {
  const s = useApi(() => api.ontadaSummary(patientId), [patientId]);

  if (s.loading) return <LoadingSkeleton count={4} />;
  if (s.error) return <Card><ErrorState error={s.error} onRetry={s.reload} /></Card>;
  if (!s.data) return null;

  const d: Summary = s.data;
  const docs = d.evidence.documents;
  const reports = d.evidence.reports;

  return (
    <div className="space-y-3">
      {/* The narrative first: one paragraph that answers "who is this and what
          are we authorising" without the reader assembling it themselves. */}
      <SectionCard title="Clinical picture" icon={<Stethoscope className="h-4 w-4" strokeWidth={1.75} />}>
        <p className="text-sm leading-relaxed text-[var(--ink-700)]">{d.narrative}</p>
      </SectionCard>

      {/* Gaps sit high, not buried at the bottom, because they decide whether
          the package is submittable at all. */}
      {d.gaps.length > 0 && (
        <Card className="border-[var(--amber-100)] bg-[var(--amber-50)]">
          <div className="p-4">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-[var(--amber-700)]">
              <TriangleAlert className="h-4 w-4" strokeWidth={1.75} />
              {d.gaps.length} gap{d.gaps.length > 1 ? "s" : ""} before this can be submitted
            </h3>
            <ul className="mt-2 space-y-1.5">
              {d.gaps.map((g) => (
                <li key={g} className="text-xs leading-relaxed text-[var(--amber-700)]">• {g}</li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {d.problems.length > 0 && (
        <SectionCard title="Problems" icon={<Activity className="h-4 w-4" strokeWidth={1.75} />}>
          <ul className="divide-y divide-[var(--ink-100)]">
            {d.problems.map((p) => (
              <li key={`${p.display}-${p.onset}`} className="flex flex-wrap items-center gap-2 py-2 first:pt-0">
                <span className="flex-1 text-sm text-[var(--ink-700)]">{p.display}</span>
                {p.icd10 && (
                  <span className="font-mono text-[11px] text-[var(--ink-500)]">{p.icd10}</span>
                )}
                {p.stage && <Chip tone="brand">Stage {p.stage}</Chip>}
                {p.status && <Chip tone={toneFor(p.status)}>{p.status}</Chip>}
                {p.onset && <span className="text-[11px] text-[var(--ink-400)]">{p.onset}</span>}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {d.regimen.length > 0 && (
        <SectionCard
          title="Medications"
          icon={<Pill className="h-4 w-4" strokeWidth={1.75} />}
          /* Grouped by drug: six Cetuximab orders are one line of therapy, not
             six drugs, and "prior lines" is the medical-necessity question. */
          description="Grouped by drug — repeat orders are one line of therapy, not many drugs"
        >
          <ul className="divide-y divide-[var(--ink-100)]">
            {d.regimen.map((m) => (
              <li key={m.rxnorm || m.drug} className="py-2.5 first:pt-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-[var(--ink-700)]">{m.drug}</span>
                  <Chip tone="brand">
                    {m.orders} order{m.orders > 1 ? "s" : ""}
                  </Chip>
                  {m.administered > 0 && <Chip tone="neutral">{m.administered} given</Chip>}
                  {m.statuses.map((st) => (
                    <Chip key={st} tone={toneFor(st)}>{st}</Chip>
                  ))}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-[var(--ink-400)]">
                  {m.rxnorm && <span className="font-mono">RxNorm {m.rxnorm}</span>}
                  {m.first && (
                    <span>{m.first === m.last ? m.first : `${m.first} → ${m.last}`}</span>
                  )}
                </div>
                {m.notes.map((n) => (
                  <p key={n} className="mt-1 text-xs italic text-[var(--ink-500)]">{n}</p>
                ))}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {d.dosing_basis.length > 0 && (
        <SectionCard
          title="Dosing basis"
          icon={<Activity className="h-4 w-4" strokeWidth={1.75} />}
          description="What a cytotoxic dose is calculated from"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {d.dosing_basis.map((m) => (
              <div key={m.label} className="rounded-[var(--radius-sm)] bg-[var(--ink-50)] p-2.5">
                <div className="text-[11px] text-[var(--ink-400)]">{m.label}</div>
                <div className="text-sm font-medium tabular-nums text-[var(--ink-700)]">
                  {m.value}
                  {m.unit && <span className="ml-1 text-[11px] font-normal text-[var(--ink-400)]">{m.unit}</span>}
                </div>
                {m.as_of && <div className="text-[10px] text-[var(--ink-300)]">{m.as_of}</div>}
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {d.labs.length > 0 && (
        <SectionCard
          title="Latest labs"
          icon={<FlaskConical className="h-4 w-4" strokeWidth={1.75} />}
          description="Most recent value per test"
        >
          <ul className="divide-y divide-[var(--ink-100)]">
            {d.labs.map((l) => (
              <li key={l.test} className="flex flex-wrap items-center gap-2 py-2 first:pt-0">
                <span className="flex-1 text-sm text-[var(--ink-700)]">{l.test}</span>
                <span className="text-sm tabular-nums text-[var(--ink-700)]">
                  {l.value !== null ? l.value : l.text}
                  {l.unit && <span className="ml-1 text-[11px] text-[var(--ink-400)]">{l.unit}</span>}
                </span>
                {l.interpretation && <Chip tone="warning">{l.interpretation}</Chip>}
                <span className="w-[72px] text-right text-[11px] text-[var(--ink-400)]">{l.as_of}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {(docs.length > 0 || reports.length > 0) && (
        <SectionCard
          title="Evidence on file"
          icon={<Paperclip className="h-4 w-4" strokeWidth={1.75} />}
          description="Available to attach to the package"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { heading: "Documents", rows: docs },
              { heading: "Diagnostic reports", rows: reports },
            ].map(({ heading, rows }) =>
              rows.length === 0 ? null : (
                <div key={heading}>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--ink-400)]">
                    {heading}
                  </h4>
                  <ul className="mt-1.5 space-y-1">
                    {rows.slice(0, 8).map((r) => (
                      <li key={r.kind} className="flex items-center gap-2 text-xs">
                        <span className="flex-1 truncate text-[var(--ink-600)]">{r.kind}</span>
                        <span className="tabular-nums text-[var(--ink-400)]">{r.count}</span>
                        <span className="w-[72px] text-right text-[10px] text-[var(--ink-300)]">
                          {r.latest}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ),
            )}
          </div>
        </SectionCard>
      )}
    </div>
  );
}
