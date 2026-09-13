"use client";

/**
 * Drill-down for the resource-count chips on a casebook.
 *
 * The counts alone say a chart is there without letting anyone read it, which
 * is the state this screen was in: 275 resources pulled, none inspectable.
 *
 * Every row is summarised from the resource itself. Where a field is absent it
 * stays absent — no placeholder, no guess — because this view is used to judge
 * whether a chart is complete enough to build a pre-auth on, and an invented
 * value would defeat the purpose. Raw JSON stays one click away for anything
 * the summary does not cover.
 */

import * as React from "react";
import { AlertTriangle, ChevronDown, X } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { ApiError, api, type FhirResource } from "@/lib/api";

/* ---- summarising one resource ---------------------------------------- */

type Coding = { system?: string; code?: string; display?: string };
type CodeableConcept = { text?: string; coding?: Coding[] };

function conceptText(cc: unknown): string {
  const c = cc as CodeableConcept | undefined;
  if (!c) return "";
  if (c.text) return c.text;
  return c.coding?.find((x) => x.display)?.display ?? "";
}

/** Prefer ICD-10 — the code a pre-auth form actually needs — then anything. */
function conceptCode(cc: unknown): string {
  const c = cc as CodeableConcept | undefined;
  const coding = c?.coding ?? [];
  const icd = coding.find((x) => (x.system ?? "").includes("/sid/icd-10"));
  const pick = icd ?? coding.find((x) => x.code);
  return pick?.code ?? "";
}

function firstDate(r: FhirResource): string {
  for (const k of [
    "recordedDate", "onsetDateTime", "authoredOn", "effectiveDateTime",
    "issued", "date", "created", "occurrenceDateTime",
  ]) {
    const v = r[k];
    if (typeof v === "string" && v) return v.slice(0, 10);
  }
  const period = r.period as { start?: string } | undefined;
  if (period?.start) return period.start.slice(0, 10);
  return "";
}

function statusOf(r: FhirResource): string {
  const clinical = conceptText(r.clinicalStatus) || (r.clinicalStatus as CodeableConcept | undefined)?.coding?.[0]?.code;
  return (clinical as string) || (typeof r.status === "string" ? r.status : "");
}

/** A one-line human label for any resource type we might be handed. */
function titleOf(r: FhirResource): string {
  const type = r.resourceType ?? "";

  if (type === "Patient" || type === "Practitioner" || type === "RelatedPerson") {
    const n = (r.name as { given?: string[]; family?: string }[] | undefined)?.[0];
    const full = [n?.given?.join(" "), n?.family].filter(Boolean).join(" ").trim();
    return full || "(unnamed)";
  }
  if (type === "Observation") {
    const label = conceptText(r.code) || "(no code)";
    const q = r.valueQuantity as { value?: number; unit?: string } | undefined;
    if (q?.value !== undefined) return `${label} — ${q.value}${q.unit ? ` ${q.unit}` : ""}`;
    const v = conceptText(r.valueCodeableConcept);
    return v ? `${label} — ${v}` : label;
  }
  if (type.startsWith("Medication")) {
    return (
      conceptText(r.medicationCodeableConcept) ||
      ((r.medicationReference as { display?: string } | undefined)?.display ?? "") ||
      "(no medication)"
    );
  }
  if (type === "Coverage") {
    const payor = (r.contained as FhirResource[] | undefined)?.find(
      (x) => x.resourceType === "Organization",
    );
    return (payor?.name as string) || conceptText(r.type) || "(no payer named)";
  }
  if (type === "DocumentReference" || type === "DiagnosticReport") {
    return conceptText(r.type) || conceptText(r.code) || "(untitled)";
  }
  if (type === "Encounter") {
    return conceptText(r.class) || (r.class as Coding | undefined)?.code || conceptText(r.type) || "Encounter";
  }
  if (type === "Organization" || type === "Location") {
    return (r.name as string) || "(unnamed)";
  }
  return conceptText(r.code) || conceptText(r.type) || (r.id as string) || "(no label)";
}

/* ---- component -------------------------------------------------------- */

interface Props {
  readonly resourceType: string;
  readonly patientId: string;
  readonly expectedCount: number;
  readonly onClose: () => void;
}

export function ResourceViewer({ resourceType, patientId, expectedCount, onClose }: Props) {
  const [state, setState] = React.useState<{
    loading: boolean;
    error: ApiError | null;
    items: FhirResource[];
    withheld: string | null;
  }>({ loading: true, error: null, items: [], withheld: null });
  const [open, setOpen] = React.useState<number | null>(null);

  React.useEffect(() => {
    let live = true;
    setState({ loading: true, error: null, items: [], withheld: null });
    api
      .ontadaResource(resourceType, patientId)
      .then((r) => {
        if (live) {
          setState({ loading: false, error: null, items: r.items ?? [], withheld: r.withheld_note ?? null });
        }
      })
      .catch((e: unknown) => {
        // Keep the ApiError itself — ErrorState reads `code` to decide between
        // an explanatory panel and a red failure, and a flattened string loses
        // that distinction.
        if (live) {
          const err =
            e instanceof ApiError
              ? e
              : new ApiError(0, {
                  code: "unknown",
                  message: e instanceof Error ? e.message : String(e),
                });
          setState({ loading: false, error: err, items: [], withheld: null });
        }
      });
    return () => {
      live = false;
    };
  }, [resourceType, patientId]);

  const { loading, error, items, withheld } = state;

  return (
    <Card className="mt-3">
      <div className="flex items-center justify-between border-b border-[var(--ink-100)] px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{resourceType}</h3>
          {!loading && !error && (
            <Chip tone={items.length === expectedCount ? "brand" : "warning"}>
              {items.length} of {expectedCount}
            </Chip>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={`Close ${resourceType}`}
          className="rounded p-1 text-[var(--ink-400)] hover:bg-[var(--ink-50)] hover:text-[var(--ink-700)]"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-4">
        {loading && <LoadingSkeleton count={3} />}
        {error && <ErrorState error={error} />}

        {!loading && !error && items.length === 0 && (
          <EmptyState
            title={`No ${resourceType} on file`}
            description="The server answered, and answered with nothing. That is different from a read that failed."
          />
        )}

        {/* Ontada documents that it may withhold elements on some resource
            types. Surfacing it stops a short list reading as a complete one. */}
        {withheld && (
          <p className="mb-3 flex items-start gap-1.5 rounded-[var(--radius-sm)] bg-[var(--amber-50)] px-2.5 py-2 text-xs text-[var(--amber-700)]">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            {withheld}
          </p>
        )}

        {items.length > 0 && (
          <ul className="divide-y divide-[var(--ink-100)]">
            {items.map((r, i) => {
              const code = conceptCode(r.code);
              const date = firstDate(r);
              const status = statusOf(r);
              return (
                <li key={(r.id as string) ?? i} className="py-2">
                  <button
                    type="button"
                    onClick={() => setOpen(open === i ? null : i)}
                    className="flex w-full items-start gap-2 text-left"
                  >
                    <ChevronDown
                      className={`mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--ink-300)] transition-transform ${
                        open === i ? "rotate-180" : ""
                      }`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm text-[var(--ink-700)]">{titleOf(r)}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                        {code && (
                          <span className="font-mono text-[11px] text-[var(--ink-400)]">{code}</span>
                        )}
                        {date && <span className="text-[11px] text-[var(--ink-400)]">{date}</span>}
                        {status && <Chip tone="neutral">{status}</Chip>}
                      </span>
                    </span>
                  </button>

                  {open === i && (
                    <pre className="mt-2 max-h-80 overflow-auto rounded-[var(--radius-sm)] bg-[var(--ink-50)] p-3 text-[11px] leading-relaxed text-[var(--ink-600)]">
                      {JSON.stringify(r, null, 2)}
                    </pre>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}
