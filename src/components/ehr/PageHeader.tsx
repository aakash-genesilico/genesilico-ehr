import * as React from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  readonly title: string;
  readonly subtitle?: string;
  readonly backHref?: string;
  readonly backLabel?: string;
  readonly actions?: React.ReactNode;
  readonly meta?: React.ReactNode;
}

export function PageHeader({ title, subtitle, backHref, backLabel, actions, meta }: PageHeaderProps) {
  return (
    <div className="space-y-3">
      {backHref && (
        <Link
          href={backHref}
          className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink-400)] transition-colors hover:text-[var(--teal-600)]"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          {backLabel ?? "Back"}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight text-[var(--ink-900)] sm:text-2xl">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-[var(--ink-500)]">{subtitle}</p>}
          {meta && <div className="mt-2 flex flex-wrap items-center gap-1.5">{meta}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

/** Standard page frame: canvas background, gutters, max width. */
export function PageShell({ children, className }: { readonly children: React.ReactNode; readonly className?: string }) {
  return (
    <div className={cn("mx-auto max-w-screen-2xl space-y-5 px-4 py-5 sm:px-6 sm:py-6 lg:px-8", className)}>
      {children}
    </div>
  );
}
