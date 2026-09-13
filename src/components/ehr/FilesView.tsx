"use client";

/**
 * The actual documents on a chart — pathology PDFs, scanned operation notes,
 * imaging — not just a count of them.
 *
 * Bytes are proxied through the backend rather than linked directly: the
 * browser holds no Ontada token, so a link to the FHIR server would 401.
 *
 * One honesty rule runs through this file. A listed attachment means the chart
 * REFERENCES a file, not that the file exists — Ontada's own data contains
 * dangling references, and the server answers HAPI-2001 "is not known" for
 * them. So nothing is labelled "available", the preview reports a missing file
 * as missing rather than broken, and the counts distinguish the two.
 */

import * as React from "react";
import {
  Download, ExternalLink, FileImage, FileText, FileWarning, Files as FilesIcon,
  TriangleAlert, X,
} from "lucide-react";
import { Card, SectionCard } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api, type OntadaFile } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

const isImage = (ct: string) => ct.startsWith("image/");
const isPdf = (ct: string) => ct.includes("pdf");
const canPreview = (ct: string) => isImage(ct) || isPdf(ct);

function iconFor(ct: string) {
  if (isImage(ct)) return <FileImage className="h-4 w-4" strokeWidth={1.75} />;
  if (isPdf(ct)) return <FileText className="h-4 w-4" strokeWidth={1.75} />;
  return <FileWarning className="h-4 w-4" strokeWidth={1.75} />;
}

/** Short label for a media type — "application/pdf" says less than "PDF". */
function typeLabel(ct: string) {
  if (!ct) return "unknown";
  const sub = ct.split(";")[0].split("/")[1] ?? ct;
  return sub.toUpperCase();
}

export function FilesView({ patientId }: { readonly patientId: string }) {
  const list = useApi(() => api.ontadaFiles(patientId), [patientId]);
  const [open, setOpen] = React.useState<OntadaFile | null>(null);
  // Binary ids the server has answered 404 for. Remembering them stops the UI
  // offering a preview that cannot work a second time.
  const [missing, setMissing] = React.useState<Set<string>>(new Set());

  if (list.loading) return <LoadingSkeleton count={4} />;
  if (list.error) return <Card><ErrorState error={list.error} onRetry={list.reload} /></Card>;
  if (!list.data) return null;

  const { files, errors, withheld_note: withheld } = list.data;
  const failedSources = Object.entries(errors ?? {});

  return (
    <div className="space-y-3">
      <SectionCard
        title="Files on the chart"
        icon={<FilesIcon className="h-4 w-4" strokeWidth={1.75} />}
        description={`${files.length} attachment${files.length === 1 ? "" : "s"} referenced by DocumentReference and DiagnosticReport`}
      >
        {withheld && (
          <p className="mb-3 flex items-start gap-1.5 rounded-[var(--radius-sm)] bg-[var(--amber-50)] px-2.5 py-2 text-xs text-[var(--amber-700)]">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            {withheld}
          </p>
        )}

        {failedSources.length > 0 && (
          <div className="mb-3 rounded-[var(--radius-sm)] bg-[var(--red-50)] px-2.5 py-2 text-xs text-[var(--red-700)]">
            {failedSources.map(([kind, msg]) => (
              <p key={kind}>
                <strong>{kind}</strong> could not be read, so its files are missing from
                this list: {msg}
              </p>
            ))}
          </div>
        )}

        {files.length === 0 ? (
          <EmptyState title="No attachments referenced" />
        ) : (
          <ul className="divide-y divide-[var(--ink-100)]">
            {files.map((f) => {
              const gone = missing.has(f.binary_id);
              const previewable = f.addressable && canPreview(f.content_type) && !gone;
              return (
                <li
                  key={`${f.source_id}-${f.binary_id || f.url}`}
                  className="flex flex-wrap items-center gap-2 py-2 first:pt-0"
                >
                  <span className="text-[var(--ink-400)]">{iconFor(f.content_type)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-[var(--ink-700)]">{f.label}</span>
                    <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-[var(--ink-400)]">
                      <span>{typeLabel(f.content_type)}</span>
                      {f.date && <span>{f.date}</span>}
                      <span className="font-mono">{f.source_type}</span>
                    </span>
                  </span>

                  {gone && <Chip tone="danger">not on server</Chip>}

                  {previewable && (
                    <button
                      type="button"
                      onClick={() => setOpen(open?.binary_id === f.binary_id ? null : f)}
                      className="rounded-[var(--radius-sm)] border border-[var(--ink-200)] px-2 py-1 text-xs text-[var(--ink-600)] hover:border-[var(--teal-500)] hover:text-[var(--teal-700)]"
                    >
                      {open?.binary_id === f.binary_id ? "Hide" : "View"}
                    </button>
                  )}

                  {f.addressable && !gone && (
                    <a
                      href={api.ontadaFileUrl(f.binary_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--ink-200)] px-2 py-1 text-xs text-[var(--ink-600)] hover:border-[var(--teal-500)] hover:text-[var(--teal-700)]"
                    >
                      <ExternalLink className="h-3 w-3" strokeWidth={2} />
                      Open
                    </a>
                  )}

                  {f.addressable && !gone && (
                    <a
                      href={api.ontadaFileUrl(f.binary_id, true)}
                      className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--ink-200)] px-2 py-1 text-xs text-[var(--ink-600)] hover:border-[var(--teal-500)] hover:text-[var(--teal-700)]"
                    >
                      <Download className="h-3 w-3" strokeWidth={2} />
                      Save
                    </a>
                  )}

                  {!f.addressable && (
                    <Chip tone="neutral" title={f.url}>external link only</Chip>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </SectionCard>

      {open && (
        <FileModal
          file={open}
          onClose={() => setOpen(null)}
          onMissing={() => setMissing((m) => new Set(m).add(open.binary_id))}
        />
      )}
    </div>
  );
}

/**
 * A centred overlay, not a panel appended below the list.
 *
 * The panel version looked broken: with 44 rows above it, clicking "View" on
 * the first file opened a preview several screens down, so nothing appeared to
 * happen. A modal is visible wherever the reader is in the list.
 */
function FileModal({
  file, onClose, onMissing,
}: {
  readonly file: OntadaFile;
  readonly onClose: () => void;
  readonly onMissing: () => void;
}) {
  // Escape closes, and the page behind must not scroll while it is open.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={file.label}
        // Clicks inside must not reach the backdrop's close handler.
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-[var(--radius)] bg-white shadow-xl"
      >
        <div className="flex items-center gap-3 border-b border-[var(--ink-100)] px-4 py-3">
          <span className="text-[var(--ink-400)]">{iconFor(file.content_type)}</span>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-[var(--ink-700)]">{file.label}</h3>
            <p className="truncate text-[11px] text-[var(--ink-400)]">
              {typeLabel(file.content_type)} · {file.source_type}/{file.source_id}
              {file.date && ` · ${file.date}`}
            </p>
          </div>
          <a
            href={api.ontadaFileUrl(file.binary_id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--ink-200)] px-2 py-1 text-xs text-[var(--ink-600)] hover:border-[var(--teal-500)]"
          >
            <ExternalLink className="h-3 w-3" strokeWidth={2} />
            New tab
          </a>
          <a
            href={api.ontadaFileUrl(file.binary_id, true)}
            className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--ink-200)] px-2 py-1 text-xs text-[var(--ink-600)] hover:border-[var(--teal-500)]"
          >
            <Download className="h-3 w-3" strokeWidth={2} />
            Save
          </a>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close preview"
            className="rounded p-1 text-[var(--ink-400)] hover:bg-[var(--ink-50)] hover:text-[var(--ink-700)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-auto bg-[var(--ink-50)] p-4">
          <FilePreview file={file} onMissing={onMissing} />
        </div>
      </div>
    </div>
  );
}

/** Renders the bytes. Images are fetched so a 404 can be reported as a missing
 *  file; a bare <img> would only ever show a broken-image glyph. */
function FilePreview({
  file, onMissing,
}: { readonly file: OntadaFile; readonly onMissing: () => void }) {
  const [src, setSrc] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let url: string | null = null;
    let live = true;
    setSrc(null);
    setError(null);

    fetch(api.ontadaFileUrl(file.binary_id))
      .then(async (r) => {
        if (!r.ok) {
          const body = (await r.json().catch(() => null)) as
            | { error?: { message?: string } }
            | null;
          throw new Error(body?.error?.message ?? `The server answered ${r.status}.`);
        }
        return r.blob();
      })
      .then((blob) => {
        if (!live) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      })
      .catch((e: unknown) => {
        if (!live) return;
        setError(e instanceof Error ? e.message : String(e));
        onMissing();
      });

    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
    // onMissing is a setState wrapper and stable enough for this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.binary_id]);

  if (error) {
    return (
      <p className="flex items-start gap-1.5 rounded-[var(--radius-sm)] bg-[var(--amber-50)] px-2.5 py-2 text-xs leading-relaxed text-[var(--amber-700)]">
        <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
        {error}
      </p>
    );
  }
  if (!src) return <LoadingSkeleton count={2} />;

  if (isImage(file.content_type)) {
    /* eslint-disable-next-line @next/next/no-img-element -- a blob: URL from a
       proxied fetch cannot go through next/image's optimiser. */
    return <img src={src} alt={file.label} className="mx-auto w-auto max-w-full rounded-[var(--radius-sm)] border border-[var(--ink-100)] bg-white" />;
  }
  // Safari will not render a PDF inside <object> from a blob: URL, and fails
  // silently — a blank box, no error. An <iframe> works more widely, and the
  // link below is the guaranteed path in every browser: it points at the proxy
  // endpoint directly, which serves the real content type with
  // `Content-Disposition: inline`, so the browser's own PDF viewer takes over.
  return (
    <div className="space-y-2">
      <p className="text-xs text-[var(--ink-500)]">
        Not rendering below?{" "}
        <a
          className="font-medium text-[var(--teal-700)] underline"
          href={api.ontadaFileUrl(file.binary_id)}
          target="_blank"
          rel="noreferrer"
        >
          Open it in a new tab
        </a>{" "}
        — some browsers refuse to display a PDF inside a page.
      </p>
      <iframe
        src={src}
        title={file.label}
        className="h-[70vh] min-h-[420px] w-full rounded-[var(--radius-sm)] border border-[var(--ink-100)] bg-white"
      />
    </div>
  );
}
