"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface SearchBarProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly placeholder?: string;
  readonly className?: string;
  /** Filters, sort controls or actions rendered to the right of the field. */
  readonly children?: React.ReactNode;
}

export function SearchBar({ value, onChange, placeholder = "Search…", className, children }: SearchBarProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="relative min-w-[12rem] flex-1">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--ink-400)]"
          aria-hidden="true"
        />
        <input
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-[var(--radius-sm)] border border-[var(--ink-200)] bg-white py-2.5 pl-9 pr-3 text-sm text-[var(--ink-900)] placeholder:text-[var(--ink-400)] transition-shadow focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[var(--teal-500)]"
        />
      </div>
      {children}
    </div>
  );
}

/** Segmented control above every list — grey track, white active pill. */
export function FilterPills<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  readonly options: ReadonlyArray<{ value: T; label: string; count?: number }>;
  readonly value: T;
  readonly onChange: (value: T) => void;
  readonly className?: string;
}) {
  return (
    <div
      className={cn("no-scrollbar flex gap-1 overflow-x-auto rounded-[var(--radius-sm)] bg-[var(--ink-50)] p-1", className)}
      role="tablist"
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              "flex-1 whitespace-nowrap rounded-[4px] px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-white text-[var(--teal-600)] shadow-[var(--shadow-sm)]"
                : "text-[var(--ink-500)] hover:text-[var(--ink-700)]",
            )}
          >
            {opt.label}
            {opt.count !== undefined && (
              <span className={cn("ml-1.5 tabular-nums", active ? "text-[var(--teal-500)]" : "text-[var(--ink-300)]")}>
                {opt.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
