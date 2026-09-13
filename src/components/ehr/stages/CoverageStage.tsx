"use client";

import * as React from "react";
import { CheckCircle2, Search, TriangleAlert, Users } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { KeyValue, SectionCard } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { Td, TableWrap, Th } from "@/components/ehr/Table";
import { api, type CasebookPackage, type CoverageDiscovery } from "@/lib/api";

/**
 * Which policies is this patient actually covered under?
 *
 * The chart usually records one. Insurance discovery routinely finds more,
 * including plans where the patient is a dependent on somebody else's policy.
 * Billing the wrong one first is a denial, and a missed primary is a write-off,
 * so this sits before the money stages rather than after them.
 */
export function CoverageStage({
  casebookId,
  pkg,
}: {
  readonly casebookId: string;
  readonly pkg: CasebookPackage | null;
}) {
  const [result, setResult] = React.useState<CoverageDiscovery | null>(null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await api.discoverCoverage(casebookId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const unknown = (result?.items ?? []).filter((i) => !i.on_file);

  return (
    <div className="space-y-4">
      <SectionCard
        title="Policies on file"
        description={pkg ? "From the pre-auth package" : "No package yet"}
      >
        {pkg ? (
          <dl>
            <KeyValue label="Payer">{pkg.payer || "Not set"}</KeyValue>
            <KeyValue label="Member ID" mono>{pkg.memberId || "Not set"}</KeyValue>
          </dl>
        ) : (
          <p className="text-sm text-[var(--ink-400)]">Nothing is being billed for this patient yet.</p>
        )}
      </SectionCard>

      <SectionCard
        title="Find other coverage"
        description="Searches the payer network on name, date of birth and state"
        icon={<Search className="h-4 w-4" strokeWidth={1.75} />}
        action={
          <Button size="sm" onClick={run} disabled={running}>
            {running ? "Searching…" : result ? "Search again" : "Run discovery"}
          </Button>
        }
      >
        {error && (
          <p className="rounded-[var(--radius-sm)] border border-[var(--red-100)] bg-[var(--red-50)] px-3 py-2.5 text-[13px] text-[var(--red-700)]">
            {error}
          </p>
        )}

        {!result && !error && (
          <p className="text-[13px] leading-relaxed text-[var(--ink-400)]">
            This is a live payer-network query. It bills a transaction, so it is not run automatically.
          </p>
        )}

        {result && !result.available && (
          <p className="text-[13px] text-[var(--ink-500)]">{result.reason}</p>
        )}

        {result?.available && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Chip tone={unknown.length > 0 ? "warning" : "success"}>
                {result.distinct_policies} distinct {result.distinct_policies === 1 ? "policy" : "policies"}
              </Chip>
              {unknown.length > 0 && (
                <Chip tone="warning" icon={<TriangleAlert className="h-3 w-3" />}>
                  {unknown.length} not on file
                </Chip>
              )}
            </div>

            {unknown.length > 0 && (
              <p className="rounded-[var(--radius-sm)] border border-[var(--amber-100)] bg-[var(--amber-50)] px-3 py-2.5 text-[13px] leading-relaxed text-[var(--amber-700)]">
                Coverage exists that this package is not billing. Confirm which plan is primary before
                submitting — the cost estimate is calculated against the policy on file only.
              </p>
            )}

            <TableWrap className="min-w-0">
              <thead>
                <tr>
                  <Th>Payer</Th>
                  <Th>Member ID</Th>
                  <Th>Subscriber</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((c) => (
                  <tr key={`${c.payer_id}-${c.member_id}`}>
                    <Td className="font-medium text-[var(--ink-900)]">
                      {c.payer_name}
                      <span className="ml-1.5 font-mono text-[11px] font-normal text-[var(--ink-400)]">
                        {c.payer_id}
                      </span>
                    </Td>
                    <Td className="font-mono text-[13px]">{c.member_id || "—"}</Td>
                    <Td className="text-[13px]">
                      {c.patient_is_dependent ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Users className="h-3.5 w-3.5 text-[var(--amber-600)]" />
                          <span>
                            {c.subscriber_name}
                            <span className="block text-[11px] text-[var(--ink-400)]">patient is a dependent</span>
                          </span>
                        </span>
                      ) : (
                        c.subscriber_name || "—"
                      )}
                    </Td>
                    <Td>
                      {c.on_file ? (
                        <Chip tone="success" icon={<CheckCircle2 className="h-3 w-3" />}>On file</Chip>
                      ) : (
                        <Chip tone="warning">Not on file</Chip>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>

            {(result.warnings ?? []).length > 0 && (
              <ul className="space-y-1 border-t border-[var(--ink-50)] pt-3">
                {result.warnings!.map((w, i) => (
                  <li key={i} className="text-[12px] leading-snug text-[var(--ink-400)]">{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
