"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export interface SubTab {
  href: string;
  label: string;
  count?: number;
}

/** Underlined tab strip used to switch views inside a console section. */
export function SubTabs({ tabs }: { readonly tabs: readonly SubTab[] }) {
  const pathname = usePathname() ?? "";

  // Longest matching href wins, so a parent tab ("/ehr/admin") does not stay
  // lit while a sibling child route ("/ehr/admin/hospitals") is open.
  const activeHref = tabs
    .filter((t) => pathname === t.href || pathname.startsWith(`${t.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return (
    <div className="no-scrollbar -mx-4 overflow-x-auto border-b border-[var(--ink-100)] px-4 sm:mx-0 sm:px-0">
      <nav className="flex min-w-max items-center gap-1" aria-label="Section views">
        {tabs.map((tab) => {
          const active = tab.href === activeHref;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] transition-colors",
                active
                  ? "border-[var(--teal-600)] font-bold text-[var(--teal-700)]"
                  : "border-transparent font-semibold text-[var(--ink-400)] hover:text-[var(--ink-700)]",
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums",
                    active ? "bg-[var(--teal-50)] text-[var(--teal-700)]" : "bg-[var(--ink-50)] text-[var(--ink-400)]",
                  )}
                >
                  {tab.count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
