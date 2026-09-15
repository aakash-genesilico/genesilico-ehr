"use client";

import * as React from "react";
import { Search, UserRound } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api, type OntadaPatient } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

/* Every Ontada read needs a patient_id, because the token is provider-scoped
   and carries no patient context. Before this, finding one meant reading raw
   FHIR — so two screens simply asked for "the" patient and got a 400 back.

   The panel is ~224 records of which only a dozen are charts; the backend hides
   the login accounts and says so in `filter_note`, which is printed rather than
   paraphrased so the count never drifts from what the filter actually did. */
export function PatientPicker({
  onSelect,
  selectedId,
}: {
  readonly onSelect: (p: OntadaPatient) => void;
  readonly selectedId?: string | null;
}) {
  const [q, setQ] = React.useState("");
  const panel = useApi(() => api.ontadaPatients(), []);

  const rows = React.useMemo(() => {
    const all = panel.data?.results ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(
      (r) => r.name.toLowerCase().includes(needle) || r.mrn.toLowerCase().includes(needle),
    );
  }, [panel.data, q]);

  if (panel.loading) return <LoadingSkeleton count={3} />;
  if (panel.error) return <Card><ErrorState error={panel.error} onRetry={panel.reload} /></Card>;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-[var(--radius)] border border-[var(--ink-100)] bg-white px-3 py-2">
        <Search className="h-4 w-4 shrink-0 text-[var(--ink-400)]" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search the panel by name or MRN"
          className="w-full text-sm text-[var(--ink-700)] outline-none"
        />
        <span className="shrink-0 text-[11px] tabular-nums text-[var(--ink-400)]">
          {rows.length}
        </span>
      </div>

      <ul className="divide-y divide-[var(--ink-50)] overflow-hidden rounded-[var(--radius)] border border-[var(--ink-100)] bg-white">
        {rows.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => onSelect(r)}
              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-[var(--ink-50)] ${
                selectedId === r.id ? "bg-[var(--teal-50)]" : ""
              }`}
            >
              <UserRound className="h-4 w-4 shrink-0 text-[var(--ink-400)]" strokeWidth={1.75} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-[var(--ink-800)]">{r.name}</span>
                <span className="block truncate text-[12px] text-[var(--ink-400)]">
                  MRN {r.mrn}
                  {r.birth_date ? ` · ${r.birth_date}` : ""}
                  {r.gender ? ` · ${r.gender}` : ""}
                </span>
              </span>
              <span className="shrink-0 font-mono text-[10px] text-[var(--ink-300)]">
                {r.id.length > 12 ? `${r.id.slice(0, 8)}…` : r.id}
              </span>
            </button>
          </li>
        ))}
        {rows.length === 0 && (
          <li className="px-3 py-6 text-center text-[13px] text-[var(--ink-400)]">
            No chart in this panel matches “{q}”.
          </li>
        )}
      </ul>

      {panel.data?.filter_note && (
        <p className="text-[11px] leading-relaxed text-[var(--ink-400)]">{panel.data.filter_note}</p>
      )}
    </div>
  );
}
