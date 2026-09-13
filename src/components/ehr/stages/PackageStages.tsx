"use client";

import * as React from "react";
import { CircleDollarSign, Send, Tag } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { SectionCard } from "@/components/ui/Card";
import { Select } from "@/components/ui/Field";
import { ErrorState } from "@/components/ui/States";
import { Td, TableWrap, Th } from "@/components/ehr/Table";
import { api, ApiError, type DrugTier, type Estimate, type PreAuthLine } from "@/lib/api";
import { cn, formatUSD, pluralize } from "@/lib/utils";

/** Billable lines, with the drug-tier assignment that makes pricing possible. */
export function LinesStage({
  lines: initial,
  tiers,
  onSave,
}: {
  readonly lines: PreAuthLine[];
  readonly tiers: DrugTier[];
  readonly onSave: (lines: PreAuthLine[]) => Promise<void>;
}) {
  const [lines, setLines] = React.useState<PreAuthLine[]>(initial);
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => setLines(initial), [initial]);

  const dirty = JSON.stringify(lines) !== JSON.stringify(initial);
  const paTiers = tiers.filter((t) => t.kind === "provider_administered");

  const setTier = (id: string, tier: string) =>
    setLines((ls) =>
      ls.map((l) =>
        l.id === id
          ? { ...l, drug_tier: tier === "" ? null : Number(tier), tier_kind: "provider_administered" }
          : l,
      ),
    );

  return (
    <SectionCard
      title="Billable lines"
      description={pluralize(lines.length, "line")}
      icon={<Tag className="h-4 w-4" strokeWidth={1.75} />}
      action={
        dirty && (
          <Button
            size="sm"
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              await onSave(lines);
              setSaving(false);
            }}
          >
            {saving ? "Saving…" : "Save tiers"}
          </Button>
        )
      }
      flush
    >
      <div className="px-4 sm:px-0">
        <TableWrap>
          <thead>
            <tr>
              <Th className="sm:pl-5">Item</Th>
              <Th>Code</Th>
              <Th align="right">Billed</Th>
              <Th className="sm:pr-5">Drug tier</Th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.id}>
                <Td className="font-medium text-[var(--ink-900)] sm:pl-5">{l.description}</Td>
                <Td className="font-mono text-[13px]">{l.code || "—"}</Td>
                <Td align="right" className="tabular-nums">{formatUSD(l.billed_cents)}</Td>
                <Td className="sm:pr-5">
                  {l.category === "drug" || l.category === "supportive" ? (
                    paTiers.length > 0 ? (
                      <div className="w-36">
                        <Select
                          value={l.drug_tier == null ? "" : String(l.drug_tier)}
                          onChange={(e) => setTier(l.id, e.target.value)}
                        >
                          <option value="">Not set</option>
                          {paTiers.map((t) => (
                            <option key={t.tier} value={t.tier}>
                              Tier {t.tier} · ${t.in_network ?? "?"}
                            </option>
                          ))}
                        </Select>
                      </div>
                    ) : (
                      <span className="text-[12px] text-[var(--ink-400)]">Run coverage to load tiers</span>
                    )
                  ) : (
                    <span className="text-[12px] text-[var(--ink-300)]">n/a</span>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
      <p className="border-t border-[var(--ink-100)] px-4 py-3 text-[12px] leading-relaxed text-[var(--ink-400)] sm:px-5">
        The 271 prices provider-administered drugs by tier, but never says which tier a HCPCS code falls
        in — that is a formulary lookup. Until a tier is set, the line stays unpriced.
      </p>
    </SectionCard>
  );
}

export function EstimateStage({ estimate }: { readonly estimate: Estimate | null }) {
  if (!estimate) {
    return (
      <SectionCard title="Cost estimate">
        <p className="text-sm text-[var(--ink-500)]">Run a coverage check to produce an estimate.</p>
      </SectionCard>
    );
  }
  const t = estimate.totals;
  const planPays = Math.max(0, t.billed_cents - t.patient_estimate_cents);

  return (
    <div className="space-y-4">
      <SectionCard title="Cost estimate" icon={<CircleDollarSign className="h-4 w-4" strokeWidth={1.75} />}>
        <div className="grid gap-3 sm:grid-cols-3">
          <Money label="Total billed" value={t.billed_cents} tone="neutral" />
          <Money label="Plan pays (est.)" value={planPays} tone="success" />
          <Money label="Patient owes (est.)" value={t.patient_estimate_cents} tone="warning" />
        </div>
        {t.lines_unknown > 0 && (
          <p className="mt-3 text-[13px] text-[var(--ink-400)]">
            {pluralize(t.lines_unknown, "line")} unpriced — assign a drug tier on the Lines stage.
          </p>
        )}
      </SectionCard>

      <SectionCard title="By line" flush>
        <div className="px-4 sm:px-0">
          <TableWrap>
            <thead>
              <tr>
                <Th className="sm:pl-5">Line</Th>
                <Th align="right">Billed</Th>
                <Th align="right">Patient</Th>
                <Th className="sm:pr-5">Basis</Th>
              </tr>
            </thead>
            <tbody>
              {estimate.lines.map((l) => (
                <tr key={l.id}>
                  <Td className="sm:pl-5">
                    <span className="block font-medium text-[var(--ink-900)]">{l.description}</span>
                    <span className="mt-0.5 block font-mono text-[11px] text-[var(--ink-400)]">{l.code}</span>
                  </Td>
                  <Td align="right" className="tabular-nums">{formatUSD(l.billed_cents)}</Td>
                  <Td
                    align="right"
                    className={cn("font-semibold tabular-nums",
                      (l.patient_estimate_cents ?? 0) > 0 ? "text-[var(--amber-700)]" : "text-[var(--ink-400)]")}
                  >
                    {l.patient_estimate_cents == null ? "—" : formatUSD(l.patient_estimate_cents)}
                    {l.capped_by_oop && (
                      <span className="ml-1 text-[10px] font-normal text-[var(--green-700)]">capped</span>
                    )}
                  </Td>
                  <Td className="text-[12px] text-[var(--ink-400)] sm:pr-5">{l.estimate_basis}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
        <p className="border-t border-[var(--ink-100)] px-4 py-3 text-[12px] leading-relaxed text-[var(--ink-400)] sm:px-5">
          {estimate.disclaimer}
        </p>
      </SectionCard>
    </div>
  );
}

export function SubmissionStage({ packageId }: { readonly packageId: string | null }) {
  const [error, setError] = React.useState<ApiError | null>(null);

  return (
    <SectionCard title="Submission" icon={<Send className="h-4 w-4" strokeWidth={1.75} />}>
      <p className="text-sm leading-relaxed text-[var(--ink-500)]">
        Submitting a prior authorisation is an X12 278 transaction. No 278 channel exists in this
        integration, so this reports why rather than recording a submission.
      </p>
      <Button
        className="mt-3"
        variant="secondary"
        disabled={!packageId}
        onClick={() => packageId && api.submitPackage(packageId).catch((e) => setError(e))}
      >
        <Send className="h-4 w-4" />
        Attempt submission
      </Button>
      {error && <ErrorState error={error} />}
    </SectionCard>
  );
}

function Money({
  label,
  value,
  tone,
}: {
  readonly label: string;
  readonly value: number;
  readonly tone: "neutral" | "success" | "warning";
}) {
  const colours = {
    neutral: "border-[var(--ink-100)] bg-[var(--ink-50)] text-[var(--ink-900)]",
    success: "border-[var(--green-100)] bg-[var(--green-50)] text-[var(--green-700)]",
    warning: "border-[var(--amber-100)] bg-[var(--amber-50)] text-[var(--amber-700)]",
  }[tone];
  return (
    <div className={cn("rounded-[var(--radius-sm)] border px-4 py-3", colours)}>
      <p className="text-[11px] font-semibold opacity-80">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums">{formatUSD(value)}</p>
    </div>
  );
}
