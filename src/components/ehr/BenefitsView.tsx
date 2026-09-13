"use client";

import * as React from "react";
import { Pill, Shield, TriangleAlert } from "lucide-react";
import { KeyValue, SectionCard } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { Td, TableWrap, Th } from "@/components/ehr/Table";
import { ProgressBar } from "@/components/ui/Progress";
import type { Accumulator, ParsedBenefits } from "@/lib/api";
import { cn } from "@/lib/utils";

const usd = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

function pick(accs: Accumulator[], level: string, network: string, basis: string) {
  return accs.find((a) => a.kind === "out_of_pocket" && a.level === level && a.network === network && a.basis === basis)?.amount ?? null;
}

export function BenefitsView({ benefits, network = "in" }: { readonly benefits: ParsedBenefits; readonly network?: string }) {
  const accs = benefits.accumulators;
  const annual = pick(accs, "individual", network, "service year");
  const remaining = pick(accs, "individual", network, "remaining");
  const ytd = pick(accs, "individual", "na", "year to date");
  const spent = annual != null && remaining != null ? annual - remaining : ytd;

  return (
    <div className="space-y-4">
      <SectionCard title="Coverage" icon={<Shield className="h-4 w-4" strokeWidth={1.75} />}>
        {benefits.errors.length > 0 ? (
          <div className="rounded-[var(--radius-sm)] border border-[var(--amber-100)] bg-[var(--amber-50)] px-3 py-2.5">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-[var(--amber-700)]">
              <TriangleAlert className="h-4 w-4" /> The payer rejected this request
            </p>
            <ul className="mt-1 space-y-0.5">
              {benefits.errors.map((e, i) => (
                <li key={i} className="text-[13px] text-[var(--ink-600)]">
                  {e.description}
                  {e.resolution && <span className="text-[var(--ink-400)]"> — {e.resolution}</span>}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <dl className="grid gap-x-8 sm:grid-cols-2">
            <div>
              <KeyValue label="Status">
                {benefits.active === null ? "Not stated" : benefits.active ? "Active coverage" : "Inactive"}
              </KeyValue>
              <KeyValue label="Payer">{benefits.payer.name ?? "—"}</KeyValue>
              <KeyValue label="Plan">{benefits.plan.name ?? "Not stated"}</KeyValue>
            </div>
            <div>
              <KeyValue label="Plan year">
                {benefits.plan.period_start && benefits.plan.period_end
                  ? `${benefits.plan.period_start} → ${benefits.plan.period_end}`
                  : "Not stated"}
              </KeyValue>
              <KeyValue label="Group" mono>{benefits.member.group_number ?? "—"}</KeyValue>
              <KeyValue label="Member ID" mono>{benefits.member.member_id ?? "—"}</KeyValue>
            </div>
          </dl>
        )}
      </SectionCard>

      {/* Accumulators — the figure that actually caps what the patient can owe. */}
      {annual != null && (
        <SectionCard title="Out-of-pocket" description={`Individual · ${network === "in" ? "in" : "out of"} network`}>
          <div className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm text-[var(--ink-500)]">
                {usd(spent)} of {usd(annual)} used
              </span>
              <span className="text-lg font-bold tabular-nums text-[var(--ink-900)]">
                {usd(remaining)} <span className="text-[13px] font-medium text-[var(--ink-400)]">remaining</span>
              </span>
            </div>
            <ProgressBar value={annual ? ((spent ?? 0) / annual) * 100 : 0} />
            <div className="grid grid-cols-2 gap-3 border-t border-[var(--ink-50)] pt-3 text-[13px] sm:grid-cols-4">
              <Fig label="Individual max" value={usd(pick(accs, "individual", network, "service year"))} />
              <Fig label="Individual left" value={usd(pick(accs, "individual", network, "remaining"))} />
              <Fig label="Family max" value={usd(pick(accs, "family", network, "service year"))} />
              <Fig label="Family left" value={usd(pick(accs, "family", network, "remaining"))} />
            </div>
          </div>
        </SectionCard>
      )}

      {/* Drug tiers — what prices an oncology regimen. */}
      {benefits.drug_tiers.length > 0 && (
        <SectionCard
          title="Drug tiers"
          description={`${benefits.drug_tiers.length} tiers stated by the payer`}
          icon={<Pill className="h-4 w-4" strokeWidth={1.75} />}
          flush
        >
          <div className="px-4 sm:px-0">
            <TableWrap className="min-w-0">
              <thead>
                <tr>
                  <Th className="sm:pl-5">Tier</Th>
                  <Th>Kind</Th>
                  <Th align="right">In network</Th>
                  <Th align="right">Out of network</Th>
                  <Th className="sm:pr-5">Note</Th>
                </tr>
              </thead>
              <tbody>
                {benefits.drug_tiers.map((t) => (
                  <tr key={`${t.kind}-${t.tier}`}>
                    <Td className="font-semibold text-[var(--ink-900)] sm:pl-5">Tier {t.tier}</Td>
                    <Td>
                      <Chip tone={t.kind === "provider_administered" ? "brand" : "neutral"}>
                        {t.kind.replace(/_/g, " ")}
                      </Chip>
                    </Td>
                    <Td align="right" className="tabular-nums">{usd(t.in_network)}</Td>
                    <Td align="right" className="tabular-nums text-[var(--ink-400)]">{usd(t.out_of_network)}</Td>
                    <Td className="text-[12px] text-[var(--ink-400)] sm:pr-5">
                      {t.varies_by_location ? "Varies by site of care" : "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </SectionCard>
      )}

      {benefits.limitations.length > 0 && (
        <SectionCard title="Limitations">
          <ul className="space-y-1.5">
            {benefits.limitations.map((l, i) => (
              <li key={i} className="text-[13px] text-[var(--ink-600)]">
                <span className="font-semibold text-[var(--ink-900)]">
                  {l.quantity} {l.unit}
                </span>{" "}
                — {l.service_types.join(", ") || l.labels.join(", ")}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {benefits.referrals.length > 0 && (
        <SectionCard title="Refer to">
          <ul className="space-y-1.5">
            {benefits.referrals.map((r, i) => (
              <li key={i} className="text-[13px] text-[var(--ink-600)]">
                <span className="font-semibold text-[var(--ink-900)]">{r.name}</span>
                {r.role && <span className="text-[var(--ink-400)]"> · {r.role}</span>}
                {r.contacts.length > 0 && <span className="text-[var(--ink-400)]"> · {r.contacts.join(", ")}</span>}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <p className="text-[11px] text-[var(--ink-300)]">
        Parsed from {benefits.entry_count} benefit entries
        {benefits.trace_id && <> · trace <span className="font-mono">{benefits.trace_id}</span></>}
        {benefits.mode && <> · {benefits.mode}</>}
      </p>
    </div>
  );
}

function Fig({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className={cn("min-w-0")}>
      <p className="text-[11px] text-[var(--ink-400)]">{label}</p>
      <p className="mt-0.5 font-semibold tabular-nums text-[var(--ink-900)]">{value}</p>
    </div>
  );
}
