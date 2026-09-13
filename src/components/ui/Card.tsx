import * as React from "react";
import { cn } from "@/lib/utils";

/** The surface every panel in this module sits on. */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border border-[var(--ink-100)] bg-white shadow-[var(--shadow-sm)]",
        className,
      )}
      {...props}
    />
  );
}

interface SectionCardProps extends React.HTMLAttributes<HTMLDivElement> {
  readonly title: string;
  readonly description?: string;
  readonly icon?: React.ReactNode;
  readonly action?: React.ReactNode;
  /** Drop the default padding when the body is a full-bleed table or list. */
  readonly flush?: boolean;
}

export function SectionCard({
  title,
  description,
  icon,
  action,
  flush = false,
  className,
  children,
  ...rest
}: SectionCardProps) {
  return (
    <Card className={cn("overflow-hidden", className)} {...rest}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--ink-100)] px-4 py-3 sm:px-5">
        <div className="flex min-w-0 items-start gap-2.5">
          {icon && <span className="mt-0.5 shrink-0 text-[var(--teal-600)]">{icon}</span>}
          <div className="min-w-0">
            <h2 className="text-sm font-bold tracking-tight text-[var(--ink-900)]">{title}</h2>
            {description && <p className="mt-0.5 text-xs leading-relaxed text-[var(--ink-400)]">{description}</p>}
          </div>
        </div>
        {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
      </div>
      <div className={flush ? "" : "px-4 py-4 sm:px-5"}>{children}</div>
    </Card>
  );
}

/** Label/value row used across the detail panels. Stacks on narrow screens. */
export function KeyValue({
  label,
  children,
  mono = false,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
  readonly mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-[var(--ink-50)] py-2.5 last:border-0 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="shrink-0 text-xs font-medium text-[var(--ink-400)] sm:w-44">{label}</dt>
      <dd
        className={cn(
          "min-w-0 break-words text-sm text-[var(--ink-900)]",
          mono && "font-mono text-[13px] text-[var(--ink-700)]",
        )}
      >
        {children}
      </dd>
    </div>
  );
}
