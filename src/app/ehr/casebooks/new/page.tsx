"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Check, Link2 } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { Button } from "@/components/ui/Button";
import { SectionCard } from "@/components/ui/Card";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

export default function NewCasebookPage() {
  const router = useRouter();
  const centers = useApi(() => api.cancerCenters(), []);
  const hospitals = useApi(() => api.hospitals(), []);
  const ontada = useApi(() => api.ontadaStatus(), []);

  const [form, setForm] = React.useState({
    patient_name: "",
    mrn: "",
    birth_date: "",
    gender: "",
    primary_diagnosis: "",
    diagnosis_code: "",
    stage: "",
    cancer_center_id: "",
    hospital_id: "",
    oncologist: "",
  });
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [bindOntada, setBindOntada] = React.useState(false);

  const centerList = centers.data?.results ?? [];
  const siteList = (hospitals.data?.results ?? []).filter(
    (h) => !form.cancer_center_id || h.cancerCenterId === form.cancer_center_id,
  );

  React.useEffect(() => {
    if (!form.cancer_center_id && centerList[0]) {
      setForm((f) => ({ ...f, cancer_center_id: centerList[0].id }));
    }
  }, [centerList, form.cancer_center_id]);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const create = async () => {
    setSaving(true);
    setErr(null);
    try {
      let extra: Record<string, unknown> = {};
      if (bindOntada) {
        // Pull the authorised patient straight from iKnowMed and keep the bundle.
        const rec = (await api.ontadaRecord()) as {
          patient?: { id?: string };
          counts?: Record<string, number>;
        };
        extra = {
          ontada_fhir_id: rec.patient?.id ? `Patient/${rec.patient.id}` : null,
          fhir_snapshot: rec,
        };
      }
      const created = await api.createCasebook({ ...form, ...extra });
      router.push(`/ehr/casebooks/${created.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  const connected = ontada.data?.connected && !ontada.data?.expired;

  return (
    <PageShell>
      <PageHeader title="New Casebook" backHref="/ehr/casebooks" backLabel="Casebooks" />

      {err && (
        <p className="rounded-[var(--radius-sm)] border border-[var(--red-100)] bg-[var(--red-50)] px-3 py-2.5 text-[13px] text-[var(--red-700)]">
          {err}
        </p>
      )}

      <SectionCard title="Ontada record" icon={<Link2 className="h-4 w-4" strokeWidth={1.75} />}>
        {connected ? (
          <label className="flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox"
              checked={bindOntada}
              onChange={(e) => setBindOntada(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--ink-300)] accent-[var(--teal-600)]"
            />
            <span className="text-[13px] leading-relaxed text-[var(--ink-700)]">
              Bind this casebook to the authorised iKnowMed patient and pull their record now.
            </span>
          </label>
        ) : (
          <p className="text-[13px] leading-relaxed text-[var(--ink-400)]">
            Not connected to Ontada, so the casebook will hold only what you type here.{" "}
            <Link href="/ehr/connect" className="font-semibold text-[var(--teal-600)] hover:underline">
              Connect Ontada
            </Link>
            .
          </p>
        )}
      </SectionCard>

      <SectionCard title="Patient details">
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Patient name" required htmlFor="n-name">
              <TextInput id="n-name" value={form.patient_name} onChange={set("patient_name")} />
            </Field>
            <Field label="MRN" htmlFor="n-mrn">
              <TextInput id="n-mrn" value={form.mrn} onChange={set("mrn")} className="font-mono text-[13px]" />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Date of birth" htmlFor="n-dob">
              <TextInput id="n-dob" type="date" value={form.birth_date} onChange={set("birth_date")} />
            </Field>
            <Field label="Gender" htmlFor="n-sex">
              <Select id="n-sex" value={form.gender} onChange={set("gender")}>
                <option value="">Not recorded</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </Select>
            </Field>
            <Field label="Stage" htmlFor="n-stage">
              <TextInput id="n-stage" value={form.stage} onChange={set("stage")} />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
            <Field label="Primary diagnosis" htmlFor="n-dx">
              <TextInput id="n-dx" value={form.primary_diagnosis} onChange={set("primary_diagnosis")} />
            </Field>
            <Field label="ICD-10-CM" htmlFor="n-icd">
              <TextInput id="n-icd" value={form.diagnosis_code} onChange={set("diagnosis_code")} className="font-mono text-[13px]" />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Cancer center" htmlFor="n-cc">
              <Select id="n-cc" value={form.cancer_center_id} onChange={set("cancer_center_id")}>
                {centerList.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Select>
            </Field>
            <Field label="Treating facility" htmlFor="n-site">
              <Select id="n-site" value={form.hospital_id} onChange={set("hospital_id")}>
                <option value="">Not set</option>
                {siteList.map((h) => (
                  <option key={h.id} value={h.id}>{h.name}</option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Treating oncologist" htmlFor="n-onc">
            <TextInput id="n-onc" value={form.oncologist} onChange={set("oncologist")} />
          </Field>
        </div>
      </SectionCard>

      <div className="flex justify-end">
        <Button onClick={create} disabled={saving || form.patient_name.trim().length < 1}>
          <Check className="h-4 w-4" />
          {saving ? "Creating…" : "Create casebook"}
        </Button>
      </div>
    </PageShell>
  );
}
