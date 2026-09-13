"use client";

import * as React from "react";
import Link from "next/link";
import { Building2, Hospital as HospitalIcon, MapPin, Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { api, type CancerCenter, type Hospital } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { EmptyState, LoadingSkeleton, ErrorState } from "@/components/ui/States";
import { formatDate } from "@/lib/utils";

const VENDOR_LABELS: Record<string, string> = {
  "ontada-ikm": "Ontada · iKnowMed",
  epic: "Epic",
  cerner: "Oracle Cerner",
  none: "No EHR connected",
};

export default function CancerCentersPage() {
  const [query, setQuery] = React.useState("");
  const [creating, setCreating] = React.useState(false);

  const centers = useApi(() => api.cancerCenters(), []);
  const sites = useApi(() => api.hospitals(), []);
  const cancerCenters = centers.data?.results ?? [];
  const hospitals = sites.data?.results ?? [];

  const results = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cancerCenters;
    return cancerCenters.filter((c) =>
      [c.name, c.city, c.state, c.organizationId].some((v) => (v ?? "").toLowerCase().includes(q)),
    );
  }, [cancerCenters, query]);

  return (
    <div className="space-y-4">
      <SearchBar value={query} onChange={setQuery} placeholder="Search cancer centers…">
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" />
          New cancer center
        </Button>
      </SearchBar>

      {centers.loading && <LoadingSkeleton count={3} />}
      {centers.error && <Card><ErrorState error={centers.error} onRetry={centers.reload} /></Card>}

      {!centers.loading && !centers.error && (results.length === 0 ? (
        <Card>
          <EmptyState
            title="No cancer centers found"
            icon={<Building2 className="h-5 w-5" strokeWidth={1.75} />}
          />
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
          {results.map((center: CancerCenter) => {
            const centerSites = hospitals.filter((h: Hospital) => h.cancerCenterId === center.id);
            return (
              <Card key={center.id} className="flex flex-col p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-[15px] font-bold tracking-tight text-[var(--ink-900)]">
                      {center.name}
                    </h3>
                    <p className="mt-1 flex items-center gap-1 text-xs text-[var(--ink-400)]">
                      <MapPin className="h-3.5 w-3.5 shrink-0" />
                      {center.city}, {center.state}
                    </p>
                  </div>
                  <StatusChip status={center.status} />
                </div>

                <p className="mt-3 break-all rounded-[var(--radius-sm)] bg-[var(--ink-50)] px-2.5 py-1.5 font-mono text-[11px] text-[var(--ink-600)]">
                  {center.organizationId}
                </p>

                <div className="mt-3 grid grid-cols-1 gap-2 border-y border-[var(--ink-50)] py-3">
                  <Metric icon={<HospitalIcon className="h-3.5 w-3.5" />} value={centerSites.length} label="Sites" />
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <Chip tone={center.ehrVendor === "none" ? "neutral" : "brand"}>{VENDOR_LABELS[center.ehrVendor]}</Chip>
                  <Chip tone="neutral">Created {formatDate(center.createdAt)}</Chip>
                </div>

                {centerSites.length > 0 && (
                  <ul className="mt-3 space-y-1">
                    {centerSites.map((site: Hospital) => (
                      <li key={site.id} className="flex items-center gap-2 text-[13px] text-[var(--ink-500)]">
                        <span className="h-1 w-1 shrink-0 rounded-full bg-[var(--ink-300)]" aria-hidden="true" />
                        <span className="min-w-0 truncate">{site.name}</span>
                      </li>
                    ))}
                  </ul>
                )}

                <div className="mt-4 flex items-center gap-2 pt-1">
                  <Link href="/ehr/admin/connections" className="flex-1">
                    <Button variant="secondary" size="sm" className="w-full">
                      Connections
                    </Button>
                  </Link>
                  <Link href="/ehr/admin/hospitals" className="flex-1">
                    <Button variant="secondary" size="sm" className="w-full">
                      Hospitals
                    </Button>
                  </Link>
                </div>
              </Card>
            );
          })}
        </div>
      ))}

      <NewCancerCenterModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => {
          centers.reload();
          sites.reload();
        }}
      />
    </div>
  );
}

function Metric({ icon, value, label }: { readonly icon: React.ReactNode; readonly value: React.ReactNode; readonly label: string }) {
  return (
    <div>
      <p className="flex items-center gap-1 text-[var(--ink-300)]">{icon}</p>
      <p className="mt-0.5 text-base font-bold tabular-nums text-[var(--ink-900)]">{value}</p>
      <p className="text-[11px] text-[var(--ink-400)]">{label}</p>
    </div>
  );
}

function NewCancerCenterModal({
  open,
  onClose,
  onCreated,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onCreated: () => void;
}) {
  const [form, setForm] = React.useState({ name: "", city: "", state: "", organization_id: "", ehr_vendor: "ontada-ikm" });
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await api.createCancerCenter(form);
      onCreated();
      onClose();
      setForm({ name: "", city: "", state: "", organization_id: "", ehr_vendor: "ontada-ikm" });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New cancer center"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} disabled={saving || form.name.trim().length < 2}>
            {saving ? "Creating…" : "Create center"}
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        {err && <p className="rounded-[var(--radius-sm)] bg-[var(--red-50)] px-3 py-2 text-[13px] text-[var(--red-700)]">{err}</p>}
        <Field label="Center name" required htmlFor="cc-name">
          <TextInput id="cc-name" placeholder="Texas Oncology — Austin" value={form.name} onChange={set("name")} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="City" required htmlFor="cc-city">
            <TextInput id="cc-city" placeholder="Austin" value={form.city} onChange={set("city")} />
          </Field>
          <Field label="State" required htmlFor="cc-state">
            <TextInput id="cc-state" placeholder="TX" maxLength={2} value={form.state} onChange={set("state")} />
          </Field>
        </div>

        <Field label="FHIR Organization identifier" htmlFor="cc-org">
          <TextInput id="cc-org" placeholder="Organization/txo-austin-001" className="font-mono text-[13px]" value={form.organization_id} onChange={set("organization_id")} />
        </Field>

        <Field label="EHR vendor" htmlFor="cc-vendor">
          <Select id="cc-vendor" value={form.ehr_vendor} onChange={set("ehr_vendor")}>
            <option value="ontada-ikm">Ontada · iKnowMed</option>
            <option value="epic">Epic</option>
            <option value="cerner">Oracle Cerner</option>
            <option value="none">No EHR connected</option>
          </Select>
        </Field>
      </form>
    </Modal>
  );
}
