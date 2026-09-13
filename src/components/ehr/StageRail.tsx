"use client";

import * as React from "react";
import { Check, Lock, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export type StageState = "complete" | "active" | "blocked" | "pending";

export interface StageItem {
  key: string;
  label: string;
  state: StageState;
}

/**
 * Numbered progress rail shared by the casebook wizard and the pre-auth
 * package builder. Scrolls horizontally rather than wrapping into an
 * unreadable grid on a phone.
 */
export function StageRail({
  stages,
  activeKey,
  onSelect,
  className,
}: {
  readonly stages: readonly StageItem[];
  readonly activeKey: string;
  readonly onSelect?: (key: string) => void;
  readonly className?: string;
}) {
  return (
    <div className={cn("no-scrollbar -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0", className)}>
      <ol className="flex min-w-max items-stretch gap-1" role="tablist">
        {stages.map((stage, i) => {
          const isActive = stage.key === activeKey;
          const interactive = Boolean(onSelect) && stage.state !== "pending";
          const Tag = interactive ? "button" : "div";

          return (
            <li key={stage.key} className="flex items-stretch">
              <Tag
                {...(interactive
                  ? { onClick: () => onSelect?.(stage.key), role: "tab", "aria-selected": isActive, type: "button" as const }
                  : {})}
                className={cn(
                  "flex items-center gap-1.5 rounded-[var(--radius-sm)] border px-3 py-2 text-left transition-colors",
                  isActive
                    ? "border-[var(--teal-500)] bg-[var(--teal-50)]"
                    : "border-[var(--ink-100)] bg-white",
                  interactive && !isActive && "hover:border-[var(--ink-200)] hover:bg-[var(--ink-50)]",
                  !interactive && "cursor-default",
                )}
              >
                <StageBadge index={i + 1} state={stage.state} active={isActive} />
                <span
                  className={cn(
                    "whitespace-nowrap text-[13px]",
                    isActive ? "font-bold text-[var(--teal-700)]" : "font-semibold text-[var(--ink-700)]",
                  )}
                >
                  {stage.label}
                </span>
              </Tag>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StageBadge({ index, state, active }: { readonly index: number; readonly state: StageState; readonly active: boolean }) {
  const base = "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[10px] font-bold";

  if (state === "complete") {
    return (
      <span className={cn(base, "bg-[var(--green-600)] text-white")} aria-label="Complete">
        <Check className="h-3 w-3" strokeWidth={3} />
      </span>
    );
  }
  if (state === "blocked") {
    return (
      <span className={cn(base, "bg-[var(--red-600)] text-white")} aria-label="Blocked">
        <TriangleAlert className="h-[11px] w-[11px]" strokeWidth={2.5} />
      </span>
    );
  }
  if (state === "pending") {
    return (
      <span className={cn(base, "bg-[var(--ink-100)] text-[var(--ink-300)]")} aria-label="Not started">
        <Lock className="h-[10px] w-[10px]" strokeWidth={2.5} />
      </span>
    );
  }
  return (
    <span className={cn(base, active ? "bg-[var(--teal-600)] text-white" : "bg-[var(--ink-100)] text-[var(--ink-500)]")}>
      {index}
    </span>
  );
}
