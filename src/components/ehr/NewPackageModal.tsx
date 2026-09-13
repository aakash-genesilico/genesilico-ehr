"use client";

import * as React from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { api, type Casebook, type Payer } from "@/lib/api";

interface LineDraft {
  id: string;
  description: string;
  code: string;
  category: string;
  billed: string;
}

const blankLine = (): LineDraft => ({
  id: Math.random().toString(36).slice(2, 8),
  description: "",
  code: "",
  category: "drug",
  billed: "",
});

export function NewPackageModal({
  open,
  onClose,
  casebooks,
  onCreated,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly casebooks: Casebook[];
  readonly onCreated: () => void;
}) {
  const [casebookId, setCasebookId] = React.useState("");
  const [regimen, setRegimen] = React.useState("");
  const [payerQuery, setPayerQuery] = React.useState("");
  const [payers, setPayers] = React.useState<Payer[]>([]);
  const [payerName, setPayerName] = React.useState("");
  const [memberId, setMemberId] = React.useState("");
  const [lines, setLines] = React.useState<LineDraft[]>([blankLine()]);
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open && !casebookId && casebooks[0]) setCasebookId(casebooks[0].id);
  }, [open, casebooks, casebookId]);

  // Real payer lookup against the Stedi directory, debounced.
  React.useEffect(() => {
    const q = payerQuery.trim();
    if (q.length < 3) {
      setPayers([]);
      return;
    }
    const t = setTimeout(() => {
      api.payers(q).then((r) => setPayers(r.results.slice(0, 6))).catch(() => setPayers([]));
    }, 300);
    return () => clearTimeout(t);
  }, [payerQuery]);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await api.createPackage({
        casebook_id: casebookId,
        regimen,
        payer_name: payerName || payerQuery,
        member_id: memberId,
        lines: lines
          .filter((l) => l.description.trim() && l.billed)
          .map((l) => ({
            id: l.id,
            description: l.description,
            code: l.code,
            category: l.category,
            billed_cents: Math.round(Number(l.billed) * 100),
          })),
      });
      onCreated();
      onClose();
      setRegimen("");
      setMemberId("");
      setPayerName("");
      setPayerQuery("");
      setLines([blankLine()]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const patch = (id: string, k: keyof LineDraft, v: string) =>
    setLines((ls) => ls.map((l) => (l.id === id ? { ...l, [k]: v } : l)));

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="New pre-auth package"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving || !casebookId}>
            {saving ? "Creating…" : "Create package"}
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        {err && (
          <p className="rounded-[var(--radius-sm)] bg-[var(--red-50)] px-3 py-2 text-[13px] text-[var(--red-700)]">{err}</p>
        )}

        <Field label="Casebook" required htmlFor="pk-cb">
          <Select id="pk-cb" value={casebookId} onChange={(e) => setCasebookId(e.target.value)}>
            {casebooks.map((c) => (
              <option key={c.id} value={c.id}>
                {c.patientName} — {c.mrn || c.id}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Regimen" htmlFor="pk-reg">
          <TextInput id="pk-reg" value={regimen} onChange={(e) => setRegimen(e.target.value)} />
        </Field>

        <Field label="Payer" htmlFor="pk-payer" hint="Searches the live Stedi payer directory.">
          <TextInput
            id="pk-payer"
            value={payerName || payerQuery}
            placeholder="Start typing an insurer name…"
            onChange={(e) => {
              setPayerQuery(e.target.value);
              setPayerName("");
            }}
          />
          {payers.length > 0 && !payerName && (
            <ul className="mt-1 overflow-hidden rounded-[var(--radius-sm)] border border-[var(--ink-200)]">
              {payers.map((p) => (
                <li key={p.payer_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setPayerName(p.name);
                      setPayers([]);
                    }}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[13px] transition-colors hover:bg-[var(--ink-50)]"
                  >
                    <span className="truncate text-[var(--ink-900)]">{p.name}</span>
                    <span className="shrink-0 font-mono text-[11px] text-[var(--ink-400)]">{p.payer_id}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Field>

        <Field label="Member ID" htmlFor="pk-mem" hint="Must be the member's real ID for a production eligibility check.">
          <TextInput id="pk-mem" value={memberId} onChange={(e) => setMemberId(e.target.value)} className="font-mono text-[13px]" />
        </Field>

        <div>
          <p className="mb-2 text-xs font-semibold text-[var(--ink-600)]">Billable lines</p>
          <div className="space-y-2">
            {lines.map((l) => (
              <div key={l.id} className="grid grid-cols-[1fr_5rem_7rem_6rem_auto] gap-2">
                <TextInput placeholder="Description" value={l.description} onChange={(e) => patch(l.id, "description", e.target.value)} />
                <TextInput placeholder="Code" value={l.code} onChange={(e) => patch(l.id, "code", e.target.value)} className="font-mono text-[13px]" />
                <Select value={l.category} onChange={(e) => patch(l.id, "category", e.target.value)}>
                  <option value="drug">Drug</option>
                  <option value="administration">Administration</option>
                  <option value="imaging">Imaging</option>
                  <option value="lab">Lab</option>
                  <option value="supportive">Supportive</option>
                </Select>
                <TextInput placeholder="USD" type="number" min={0} value={l.billed} onChange={(e) => patch(l.id, "billed", e.target.value)} />
                <button
                  type="button"
                  onClick={() => setLines((ls) => (ls.length > 1 ? ls.filter((x) => x.id !== l.id) : ls))}
                  aria-label="Remove line"
                  className="flex h-10 w-9 items-center justify-center rounded-[var(--radius-sm)] text-[var(--ink-400)] transition-colors hover:bg-[var(--ink-50)] hover:text-[var(--red-600)]"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
          <Button variant="ghost" size="sm" className="mt-2" onClick={() => setLines((ls) => [...ls, blankLine()])}>
            <Plus className="h-3.5 w-3.5" />
            Add line
          </Button>
        </div>
      </form>
    </Modal>
  );
}
