"use client";

import Link from "next/link";
import { ArrowRight, PlugZap, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { formatDateTime } from "@/lib/utils";

export default function ConnectionsPage() {
  const caps = useApi(() => api.capabilities(), []);
  const ontada = useApi(() => api.ontadaStatus(), []);

  const reloadAll = () => {
    caps.reload();
    ontada.reload();
  };

  if (caps.loading) return <LoadingSkeleton count={2} />;
  if (caps.error) return <Card><ErrorState error={caps.error} onRetry={reloadAll} /></Card>;
  if (!caps.data) return null;

  const { stedi, ontada: ont } = caps.data;
  const ontadaStatus = !ont.configured
    ? "not-configured"
    : ontada.data?.connected
      ? "connected"
      : "disconnected";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <Button variant="secondary" size="sm" onClick={reloadAll}>
          <RefreshCw className="h-3.5 w-3.5" />
          Re-check all
        </Button>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        {/* Ontada */}
        <Card className="flex flex-col p-4">
          <Header
            title="Ontada · iKnowMed"
            subtitle="FHIR R4 gateway · SMART on FHIR"
            status={ontadaStatus}
            ok={ontadaStatus === "connected"}
          />
          <Endpoint value={ont.fhir_base ?? "Not configured"} />
          <dl className="mt-3 grid grid-cols-2 gap-3 border-y border-[var(--ink-50)] py-3 text-[13px]">
            <Cell label="Grant types" value={ont.grant_types.join(", ")} />
            <Cell label="Client auth" value={ont.client_auth ?? "—"} />
            <Cell label="Launch context" value={ontada.data?.launch_context ?? "—"} />
            <Cell
              label="Token"
              value={
                ontada.data?.connected
                  ? ontada.data.expired
                    ? "Expired"
                    : `Valid to ${formatDateTime(ontada.data.expires_at)}`
                  : "None"
              }
            />
          </dl>
          <p className="mt-3 text-[13px] leading-relaxed text-[var(--ink-400)]">
            {ont.service_to_service.reason}
          </p>
          <div className="mt-4 pt-1">
            <Link href="/ehr/connect">
              <Button variant="secondary" size="sm" className="w-full">
                Open Ontada Connect
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </Card>

        {/* Stedi */}
        <Card className="flex flex-col p-4">
          <Header
            title="Stedi Healthcare"
            subtitle="Payer network · X12 eligibility"
            status={stedi.mode === "unconfigured" ? "not-configured" : "connected"}
            ok={stedi.mode !== "unconfigured"}
          />
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <Chip tone={stedi.mode === "production" ? "danger" : "warning"}>
              {stedi.mode === "production" ? "Production — real payers, billable" : `Mode: ${stedi.mode}`}
            </Chip>
          </div>
          <ul className="mt-3 space-y-2 border-t border-[var(--ink-50)] pt-3">
            <Capability label="Payer directory" ok={stedi.payer_search.available} />
            <Capability label="Eligibility 270/271" ok={stedi.eligibility_270_271.available} note={stedi.eligibility_270_271.note} />
            <Capability label="Claim status 276/277" ok={stedi.claim_status_276_277.available} note={stedi.claim_status_276_277.reason} />
            <Capability label="Insurance discovery" ok={stedi.insurance_discovery.available} note={stedi.insurance_discovery.reason} />
            <Capability label="Prior auth 278" ok={stedi.prior_auth_278.available} note={stedi.prior_auth_278.reason} />
          </ul>
        </Card>
      </div>
    </div>
  );
}

function Header({ title, subtitle, status, ok }: { title: string; subtitle: string; status: string; ok: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] ${
            ok ? "bg-[var(--green-50)] text-[var(--green-600)]" : "bg-[var(--ink-50)] text-[var(--ink-400)]"
          }`}
        >
          <PlugZap className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <h3 className="truncate text-[15px] font-bold tracking-tight text-[var(--ink-900)]">{title}</h3>
          <p className="mt-0.5 text-xs text-[var(--ink-400)]">{subtitle}</p>
        </div>
      </div>
      <StatusChip status={status} />
    </div>
  );
}

function Endpoint({ value }: { value: string }) {
  return (
    <p className="mt-3 break-all rounded-[var(--radius-sm)] bg-[var(--ink-50)] px-2.5 py-2 font-mono text-[11px] leading-relaxed text-[var(--ink-600)]">
      {value}
    </p>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-[var(--ink-400)]">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-[var(--ink-700)]">{value}</dd>
    </div>
  );
}

function Capability({ label, ok, note }: { label: string; ok: boolean; note?: string | null }) {
  return (
    <li className="flex items-start gap-2">
      <ShieldCheck
        className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${ok ? "text-[var(--green-600)]" : "text-[var(--ink-300)]"}`}
      />
      <div className="min-w-0">
        <span className={`text-[13px] font-medium ${ok ? "text-[var(--ink-900)]" : "text-[var(--ink-400)]"}`}>
          {label}
        </span>
        {!ok && note && <p className="mt-0.5 text-[12px] leading-snug text-[var(--ink-400)]">{note}</p>}
      </div>
    </li>
  );
}
