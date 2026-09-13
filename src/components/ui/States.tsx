"use client";

import * as React from "react";
import { FileQuestion, PlugZap, RefreshCw, TriangleAlert } from "lucide-react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function LoadingSkeleton({ count = 5, className }: { readonly count?: number; readonly className?: string }) {
  return (
    <div className={cn("space-y-3", className)} role="status" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className="animate-pulse rounded-[var(--radius)] border border-[var(--ink-100)] bg-white p-4"
        >
          <div className="mb-3 flex items-center justify-between">
            <div className="h-4 w-32 rounded bg-[var(--ink-100)]" />
            <div className="h-5 w-20 rounded-full bg-[var(--ink-100)]" />
          </div>
          <div className="mb-2 h-3 w-48 rounded bg-[var(--ink-50)]" />
          <div className="h-3 w-36 rounded bg-[var(--ink-50)]" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title = "Nothing here yet",
  description,
  icon,
  action,
}: {
  readonly title?: string;
  readonly description?: string;
  readonly icon?: React.ReactNode;
  readonly action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--ink-50)] text-[var(--ink-300)]">
        {icon ?? <FileQuestion className="h-5 w-5" strokeWidth={1.75} />}
      </div>
      <p className="text-base font-semibold text-[var(--ink-700)]">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-[var(--ink-400)]">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}


/**
 * Renders a backend failure using the backend's own words.
 *
 * `unconfigured`, `not_implemented` and `ontada_not_connected` are not faults —
 * they are the service correctly reporting that a capability is not wired. They
 * get an explanatory panel, not a red error.
 */
export function ErrorState({ error, onRetry }: { readonly error: ApiError; readonly onRetry?: () => void }) {
  const informational =
    error.code === "unconfigured" ||
    error.code === "not_implemented" ||
    error.code === "ontada_not_connected" ||
    error.code === "ontada_reauth_required";

  const resolution =
    typeof error.detail === "object" && error.detail !== null && "resolution" in error.detail
      ? String((error.detail as { resolution: unknown }).resolution)
      : null;

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        informational ? "text-[var(--ink-500)]" : "text-[var(--red-700)]",
      )}
    >
      <span
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-full",
          informational ? "bg-[var(--ink-50)] text-[var(--ink-300)]" : "bg-[var(--red-50)] text-[var(--red-600)]",
        )}
      >
        {informational ? <PlugZap className="h-5 w-5" strokeWidth={1.75} /> : <TriangleAlert className="h-5 w-5" strokeWidth={1.75} />}
      </span>
      <p className="max-w-xl text-sm font-medium leading-relaxed text-[var(--ink-700)]">{error.message}</p>
      {resolution && <p className="max-w-xl text-[13px] text-[var(--ink-400)]">{resolution}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--ink-200)] bg-white px-3 py-1.5 text-xs font-semibold text-[var(--ink-700)] transition-colors hover:bg-[var(--ink-50)]"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}
