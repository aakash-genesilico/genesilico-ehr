import * as React from "react";
import { cn } from "@/lib/utils";

export type ChipTone = "neutral" | "brand" | "ai" | "success" | "warning" | "danger";

const TONES: Record<ChipTone, string> = {
  neutral: "bg-[var(--ink-50)] text-[var(--ink-500)] border-[var(--ink-200)]",
  brand: "bg-[var(--teal-50)] text-[var(--teal-700)] border-[var(--teal-100)]",
  ai: "bg-[var(--ai-50)] text-[var(--ai-700)] border-[var(--ai-100)]",
  success: "bg-[var(--green-50)] text-[var(--green-700)] border-[var(--green-100)]",
  warning: "bg-[var(--amber-50)] text-[var(--amber-700)] border-[var(--amber-100)]",
  danger: "bg-[var(--red-50)] text-[var(--red-700)] border-[var(--red-100)]",
};

interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  readonly tone?: ChipTone;
  readonly icon?: React.ReactNode;
}

export function Chip({ tone = "neutral", icon, className, children, ...rest }: ChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium leading-5 whitespace-nowrap",
        TONES[tone],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </span>
  );
}

/* ---- Domain status → tone maps -------------------------------------- */

const STATUS_TONES: Record<string, ChipTone> = {
  /* connections */
  connected: "success",
  degraded: "warning",
  disconnected: "danger",
  "not-configured": "neutral",
  /* organisations */
  active: "success",
  onboarding: "warning",
  suspended: "danger",
  /* casebooks */
  draft: "neutral",
  ingesting: "ai",
  "gaps-pending": "warning",
  "ai-ready": "ai",
  "plan-drafted": "brand",
  "signed-off": "success",
  /* plans + packages */
  "in-review": "warning",
  "pre-auth-started": "brand",
  drafting: "neutral",
  "manager-review": "warning",
  submitted: "brand",
  "payer-review": "brand",
  approved: "success",
  denied: "danger",
  appealed: "warning",
  /* coverage decisions */
  covered: "success",
  partial: "warning",
  "not-covered": "danger",
  "prior-auth-required": "warning",
  pending: "neutral",
};

const STATUS_LABELS: Record<string, string> = {
  "not-configured": "Not configured",
  "gaps-pending": "Gaps pending",
  "ai-ready": "AI ready",
  "plan-drafted": "Plan drafted",
  "signed-off": "Signed off",
  "in-review": "In review",
  "pre-auth-started": "Pre-auth started",
  "manager-review": "Manager review",
  "payer-review": "Payer review",
  "not-covered": "Not covered",
  "prior-auth-required": "Separate auth needed",
};

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/-/g, " ");
}

export function StatusChip({ status, className }: { readonly status?: string | null; readonly className?: string }) {
  if (!status) return null;
  return (
    <Chip tone={STATUS_TONES[status] ?? "neutral"} className={className}>
      {STATUS_LABELS[status] ?? titleCase(status)}
    </Chip>
  );
}
