"use client";

import * as React from "react";
import { Field, Select, TextInput } from "@/components/ui/Field";
import type { FormField, PolicyForm } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FormValues = Record<string, string | boolean>;

/** Field-level conditional visibility, as declared by the schema. */
function isVisible(field: FormField, values: FormValues): boolean {
  const cond = field.visible_when;
  if (!cond) return true;
  return Object.entries(cond).every(([k, want]) => {
    const have = values[k];
    if (Array.isArray(want)) return (want as unknown[]).includes(have);
    if (typeof want === "boolean") return Boolean(have) === want;
    return String(have ?? "") === String(want);
  });
}

export function initialValues(form: PolicyForm): FormValues {
  const out: FormValues = {};
  for (const s of form.sections) {
    for (const f of s.fields) {
      if (f.value !== undefined && f.value !== null) out[f.id] = f.value;
      else out[f.id] = f.type === "checkbox" ? false : "";
    }
  }
  return out;
}

export function DynamicForm({
  form,
  values,
  onChange,
  errors,
}: {
  readonly form: PolicyForm;
  readonly values: FormValues;
  readonly onChange: (next: FormValues) => void;
  readonly errors?: Record<string, string>;
}) {
  const set = (id: string, v: string | boolean) => onChange({ ...values, [id]: v });

  return (
    <div className="space-y-5">
      {form.sections.map((section) => {
        const visible = section.fields.filter((f) => isVisible(f, values));
        if (visible.length === 0) return null;
        return (
          <div key={section.id}>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-[var(--ink-400)]">
              {section.title}
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              {visible.map((f) => (
                <div key={f.id} className={cn(f.type === "checkbox" && "sm:col-span-2")}>
                  <FieldControl
                    field={f}
                    value={values[f.id]}
                    error={errors?.[f.id]}
                    onChange={(v) => set(f.id, v)}
                  />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FieldControl({
  field,
  value,
  error,
  onChange,
}: {
  readonly field: FormField;
  readonly value: string | boolean | undefined;
  readonly error?: string;
  readonly onChange: (v: string | boolean) => void;
}) {
  const id = `f-${field.id}`;

  if (field.type === "checkbox") {
    return (
      <label className="flex cursor-pointer items-start gap-2.5 rounded-[var(--radius-sm)] px-1 py-1.5">
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--ink-300)] accent-[var(--teal-600)]"
        />
        <span className="min-w-0">
          <span className="block text-[13px] font-medium text-[var(--ink-700)]">{field.label}</span>
          {field.help && <span className="mt-0.5 block text-[11px] leading-snug text-[var(--ink-400)]">{field.help}</span>}
        </span>
      </label>
    );
  }

  const control =
    field.type === "select" ? (
      <Select id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select…</option>
        {(field.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    ) : (
      <TextInput
        id={id}
        type={field.type === "date" ? "date" : field.type === "tel" ? "tel" : "text"}
        value={String(value ?? "")}
        placeholder={field.placeholder}
        maxLength={field.maxLength}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          field.sensitive && "font-mono text-[13px]",
          error && "border-[var(--red-600)] focus:ring-[var(--red-600)]",
        )}
      />
    );

  return (
    <Field label={field.label} required={field.required} htmlFor={id} hint={error ? undefined : field.help}>
      {control}
      {error && <p className="text-[11px] font-medium text-[var(--red-600)]">{error}</p>}
      {/* The X12 element each field maps to — makes the form auditable against
          the 270 it produces. */}
      {field.x12 && !error && (
        <p className="font-mono text-[10px] text-[var(--ink-300)]">{field.x12}</p>
      )}
    </Field>
  );
}
