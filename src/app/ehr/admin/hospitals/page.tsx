"use client";

import * as React from "react";
import { Hospital as HospitalIcon, Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { FilterPills, SearchBar } from "@/components/ui/SearchBar";
import { Td, TableWrap, Th } from "@/components/ehr/Table";
import { api, type CancerCenter } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

const TYPE_LABELS: Record<string, string> = {
  hospital: "Hospital",
  "infusion-center": "Infusion center",
  clinic: "Clinic",
};

export default function HospitalsPage() {
  const [query, setQuery] = React.useState("");
  const [center, setCenter] = React.useState<string>("all");
  const [creating, setCreating] = React.useState(false);

  const hospitals = useApi(() => api.hospitals(), []);
  const centers = useApi(() => api.cancerCenters(), []);
  const rows = hospitals.data?.results ?? [];
  const centerList = centers.data?.results ?? [];
  const centerName = (id: string) => centerList.find((c) => c.id === id)?.name ?? "—";

  const results = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((h) => {
      if (center !== "all" && h.cancerCenterId !== center) return false;
      if (!q) return true;
      return [h.name, h.city, h.state, h.npi].some((v) => (v ?? "").toLowerCase().includes(q));
    });
  }, [rows, query, center]);

  return (
    <div className="space-y-4">
      <SearchBar value={query} onChange={setQuery} placeholder="Search hospitals, cities or NPIs…">
        <Button onClick={() => setCreating(true)} disabled={centerList.length === 0}>
          <Plus className="h-4 w-4" />
          New hospital
        </Button>
      </SearchBar>

      {centerList.length > 0 && (
        <FilterPills
          value={center}
          onChange={setCenter}
          options={[
            { value: "all", label: "All centers", count: rows.length },
            ...centerList.map((c) => ({
              value: c.id,
              label: c.name.replace("Texas Oncology — ", "TXO "),
              count: rows.filter((h) => h.cancerCenterId === c.id).length,
            })),
          ]}
        />
      )}

      <Card className="overflow-hidden">
        {hospitals.loading && <div className="p-4"><LoadingSkeleton count={3} /></div>}
        {hospitals.error && <ErrorState error={hospitals.error} onRetry={hospitals.reload} />}
        {!hospitals.loading && !hospitals.error && results.length === 0 && (
          <EmptyState
            title="No hospitals yet"
            description="Add the facilities that will appear as the place of service on a pre-auth package."
            icon={<HospitalIcon className="h-5 w-5" strokeWidth={1.75} />}
          />
        )}
        {!hospitals.loading && !hospitals.error && results.length > 0 && (
          <div className="px-4 sm:px-0">
            <TableWrap>
              <thead>
                <tr>
                  <Th className="sm:pl-5">Facility</Th>
                  <Th>Cancer center</Th>
                  <Th>Type</Th>
                  <Th>NPI</Th>
                  <Th align="right">Beds</Th>
                  <Th align="right" className="sm:pr-5">Status</Th>
                </tr>
              </thead>
              <tbody>
                {results.map((h) => (
                  <tr key={h.id} className="transition-colors hover:bg-[var(--ink-50)]">
                    <Td className="sm:pl-5">
                      <span className="block font-semibold text-[var(--ink-900)]">{h.name}</span>
                      <span className="block text-xs text-[var(--ink-400)]">
                        {[h.city, h.state].filter(Boolean).join(", ") || "—"}
                      </span>
                    </Td>
                    <Td className="text-[13px]">{centerName(h.cancerCenterId)}</Td>
                    <Td>
                      <Chip tone={h.type === "hospital" ? "brand" : "neutral"}>
                        {TYPE_LABELS[h.type] ?? h.type}
                      </Chip>
                    </Td>
                    <Td className="font-mono text-[13px]">{h.npi || "—"}</Td>
                    <Td align="right" className="tabular-nums">{h.beds || "—"}</Td>
                    <Td align="right" className="sm:pr-5"><StatusChip status={h.status} /></Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        )}
      </Card>

      <NewHospitalModal
        open={creating}
        onClose={() => setCreating(false)}
        centers={centerList}
        onCreated={hospitals.reload}
      />
    </div>
  );
}

function NewHospitalModal({
  open,
  onClose,
  centers,
  onCreated,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly centers: CancerCenter[];
  readonly onCreated: () => void;
}) {
  const blank = {
    name: "",
    cancer_center_id: centers[0]?.id ?? "",
    city: "",
    state: "",
    npi: "",
    beds: "",
    type: "hospital",
  };
  const [form, setForm] = React.useState(blank);
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open && !form.cancer_center_id && centers[0]) {
      setForm((f) => ({ ...f, cancer_center_id: centers[0].id }));
    }
  }, [open, centers, form.cancer_center_id]);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await api.createHospital({ ...form, beds: Number(form.beds) || 0 });
      onCreated();
      onClose();
      setForm(blank);
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
      title="New hospital"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving || form.name.trim().length < 2 || !form.cancer_center_id}>
            {saving ? "Creating…" : "Create hospital"}
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        {err && (
          <p className="rounded-[var(--radius-sm)] bg-[var(--red-50)] px-3 py-2 text-[13px] text-[var(--red-700)]">{err}</p>
        )}

        <Field label="Facility name" required htmlFor="h-name">
          <TextInput id="h-name" placeholder="St. David's Medical Center" value={form.name} onChange={set("name")} />
        </Field>

        <Field label="Cancer center" required htmlFor="h-center">
          <Select id="h-center" value={form.cancer_center_id} onChange={set("cancer_center_id")}>
            {centers.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="City" htmlFor="h-city">
            <TextInput id="h-city" placeholder="Austin" value={form.city} onChange={set("city")} />
          </Field>
          <Field label="State" htmlFor="h-state">
            <TextInput id="h-state" placeholder="TX" maxLength={2} value={form.state} onChange={set("state")} />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Facility type" htmlFor="h-type">
            <Select id="h-type" value={form.type} onChange={set("type")}>
              <option value="hospital">Hospital</option>
              <option value="infusion-center">Infusion center</option>
              <option value="clinic">Clinic</option>
            </Select>
          </Field>
          <Field label="Licensed beds" htmlFor="h-beds">
            <TextInput id="h-beds" type="number" inputMode="numeric" min={0} value={form.beds} onChange={set("beds")} />
          </Field>
        </div>

        <Field label="Facility NPI" htmlFor="h-npi" hint="Ten digits.">
          <TextInput
            id="h-npi"
            inputMode="numeric"
            maxLength={10}
            placeholder="1467892034"
            className="font-mono text-[13px]"
            value={form.npi}
            onChange={set("npi")}
          />
        </Field>
      </form>
    </Modal>
  );
}
