"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModalProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly title: string;
  readonly description?: string;
  readonly footer?: React.ReactNode;
  readonly children: React.ReactNode;
  readonly size?: "md" | "lg";
}

export function Modal({ open, onClose, title, description, footer, children, size = "md" }: ModalProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    // Stop the page behind from scrolling while the sheet is up.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <button className="absolute inset-0 bg-[var(--ink-900)]/45 backdrop-blur-[2px]" onClick={onClose} aria-label="Close dialog" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-[var(--radius-lg)] bg-white shadow-[var(--shadow-lg)] sm:rounded-[var(--radius-lg)]",
          size === "lg" ? "sm:max-w-3xl" : "sm:max-w-xl",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--ink-100)] px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-bold tracking-tight text-[var(--ink-900)]">{title}</h2>
            {description && <p className="mt-0.5 text-[13px] leading-snug text-[var(--ink-400)]">{description}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-[var(--ink-400)] transition-colors hover:bg-[var(--ink-50)] hover:text-[var(--ink-900)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>

        {footer && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--ink-100)] bg-[var(--ink-50)] px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
