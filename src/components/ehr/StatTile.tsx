import * as React from "react";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/Card";

export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  readonly label: string;
  readonly value: React.ReactNode;
  readonly hint?: string;
  readonly icon?: React.ReactNode;
  readonly tone?: "neutral" | "brand" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    neutral: "text-[var(--ink-400)] bg-[var(--ink-50)]",
    brand: "text-[var(--teal-600)] bg-[var(--teal-50)]",
    success: "text-[var(--green-600)] bg-[var(--green-50)]",
    warning: "text-[var(--amber-600)] bg-[var(--amber-50)]",
    danger: "text-[var(--red-600)] bg-[var(--red-50)]",
  }[tone];

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-[var(--ink-400)]">{label}</p>
          <p className="mt-1.5 text-2xl font-bold tabular-nums tracking-tight text-[var(--ink-900)]">{value}</p>
          {hint && <p className="mt-1 text-[11px] leading-snug text-[var(--ink-400)]">{hint}</p>}
        </div>
        {icon && (
          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)]", toneClass)}>
            {icon}
          </span>
        )}
      </div>
    </Card>
  );
}
