"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, Bell, ChevronDown, Check } from "lucide-react";
import { NAV_ITEMS, activeNavHref } from "./nav";
import { ReconnectBanner } from "./ReconnectBanner";
import { api, type CancerCenter } from "@/lib/api";
import { cn, initialsOf } from "@/lib/utils";

const USER = { name: "Dana Whitmore", role: "Pre-Auth & Insurance Admin" };

export function AppShell({ children }: { readonly children: React.ReactNode }) {
  const pathname = usePathname() ?? "/ehr";
  const active = activeNavHref(pathname);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  // The drawer is a route-level overlay; leaving the route should close it.
  React.useEffect(() => setDrawerOpen(false), [pathname]);

  return (
    <div className="flex min-h-screen bg-[var(--canvas)]">
      <DesktopSidebar active={active} />
      <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} active={active} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setDrawerOpen(true)} />
        <ReconnectBanner />
        {/* pb-20 keeps the last row clear of the mobile bottom bar. */}
        <main className="min-w-0 flex-1 pb-20 md:pb-0">{children}</main>
      </div>

      <MobileBottomBar active={active} />
    </div>
  );
}

/* ---------------- Brand ---------------- */

function BrandMark({ withWordmark = true }: { readonly withWordmark?: boolean }) {
  return (
    <Link href="/ehr" className="flex items-center gap-2.5" aria-label="GeneSilico EHR home">
      <span className="ai-gradient-bg flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white">
        GS
      </span>
      {withWordmark && (
        <span className="min-w-0 truncate text-sm font-bold tracking-tight text-[var(--ink-900)]">
          GeneSilico <span className="gradient-text">EHR</span>
        </span>
      )}
    </Link>
  );
}

/* ---------------- Desktop sidebar ---------------- */

function DesktopSidebar({ active }: { readonly active: string }) {
  return (
    <aside
      className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-[var(--ink-100)] bg-white lg:flex"
      aria-label="Primary"
    >
      <div className="flex h-14 items-center border-b border-[var(--ink-100)] px-4">
        <BrandMark />
      </div>
      <CenterSwitcher />
      <nav className="thin-scrollbar flex-1 overflow-y-auto px-3 py-3">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <NavLink item={item} active={active === item.href} />
            </li>
          ))}
        </ul>
      </nav>
      <SidebarFooter />
    </aside>
  );
}

function NavLink({
  item,
  active,
  onClick,
}: {
  readonly item: (typeof NAV_ITEMS)[number];
  readonly active: boolean;
  readonly onClick?: () => void;
}) {
  const { Icon } = item;
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-2 transition-colors",
        active
          ? "bg-[var(--teal-50)] text-[var(--teal-700)]"
          : "text-[var(--ink-500)] hover:bg-[var(--ink-50)] hover:text-[var(--ink-900)]",
      )}
    >
      <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={active ? 2 : 1.75} />
      <span className={cn("min-w-0 truncate text-[13px]", active ? "font-bold" : "font-semibold")}>{item.label}</span>
    </Link>
  );
}

/** Tenant picker. Every screen below is scoped to the selected cancer center. */
function CenterSwitcher() {
  const [open, setOpen] = React.useState(false);
  const [centers, setCenters] = React.useState<CancerCenter[]>([]);
  const [selected, setSelected] = React.useState<string>("");
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    api
      .cancerCenters()
      .then((r) => {
        setCenters(r.results);
        setSelected((s) => s || r.results[0]?.id || "");
      })
      .catch(() => setCenters([]));
  }, []);

  const center = centers.find((c) => c.id === selected) ?? centers[0];

  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative border-b border-[var(--ink-100)] px-3 py-3">
      <button
        onClick={() => setOpen((p) => !p)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--ink-200)] bg-white px-2.5 py-2 text-left transition-colors hover:bg-[var(--ink-50)]"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-[10px] font-semibold uppercase tracking-wider text-[var(--ink-400)]">
            Cancer center
          </span>
          <span className="block truncate text-[13px] font-semibold text-[var(--ink-900)]">
            {center?.name ?? "No cancer center"}
          </span>
        </span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-[var(--ink-400)] transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute left-3 right-3 top-full z-40 mt-1 overflow-hidden rounded-[var(--radius-sm)] border border-[var(--ink-200)] bg-white py-1 shadow-[var(--shadow)]"
        >
          {centers.map((c) => (
            <li key={c.id}>
              <button
                role="option"
                aria-selected={c.id === selected}
                onClick={() => {
                  setSelected(c.id);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors hover:bg-[var(--ink-50)]"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-[var(--ink-900)]">{c.name}</span>
                  <span className="block text-[11px] text-[var(--ink-400)]">
                    {c.city}, {c.state}
                  </span>
                </span>
                {c.id === selected && <Check className="h-4 w-4 shrink-0 text-[var(--teal-600)]" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SidebarFooter() {
  return (
    <div className="border-t border-[var(--ink-100)] p-3">
      <div className="flex items-center gap-2.5 rounded-[var(--radius-sm)] px-1 py-1">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--ai-100)] text-[11px] font-bold text-[var(--ink-700)]">
          {initialsOf(USER.name)}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[13px] font-semibold text-[var(--ink-900)]">{USER.name}</span>
          <span className="block truncate text-[11px] text-[var(--ink-400)]">{USER.role}</span>
        </span>
      </div>
    </div>
  );
}

/* ---------------- Top bar ---------------- */

function TopBar({ onMenu }: { readonly onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-[var(--ink-100)] bg-white/92 px-3 backdrop-blur-md sm:px-4">
      <button
        onClick={onMenu}
        aria-label="Open navigation"
        className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] text-[var(--ink-500)] transition-colors hover:bg-[var(--ink-50)] lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="lg:hidden">
        <BrandMark withWordmark={false} />
      </div>

      <div className="min-w-0 flex-1" />

      <button
        aria-label="Notifications"
        className="relative flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] text-[var(--ink-500)] transition-colors hover:bg-[var(--ink-50)]"
      >
        <Bell className="h-[18px] w-[18px]" strokeWidth={1.75} />
        <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-[var(--red-600)]" />
      </button>

      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--ai-100)] text-[11px] font-bold text-[var(--ink-700)] lg:hidden">
        {initialsOf(USER.name)}
      </span>
    </header>
  );
}

/* ---------------- Mobile drawer ---------------- */

function MobileDrawer({
  open,
  onClose,
  active,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly active: string;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button className="absolute inset-0 bg-[var(--ink-900)]/40" onClick={onClose} aria-label="Close navigation" />
      <div className="absolute inset-y-0 left-0 flex w-[280px] max-w-[85vw] flex-col bg-white shadow-[var(--shadow-lg)]">
        <div className="flex h-14 items-center justify-between border-b border-[var(--ink-100)] px-4">
          <BrandMark />
          <button
            onClick={onClose}
            aria-label="Close navigation"
            className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] text-[var(--ink-500)] hover:bg-[var(--ink-50)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <CenterSwitcher />
        <nav className="thin-scrollbar flex-1 overflow-y-auto px-3 py-3">
          <ul className="space-y-0.5">
            {NAV_ITEMS.map((item) => (
              <li key={item.href}>
                <NavLink item={item} active={active === item.href} onClick={onClose} />
              </li>
            ))}
          </ul>
        </nav>
        <SidebarFooter />
      </div>
    </div>
  );
}

/* ---------------- Mobile bottom bar ---------------- */

function MobileBottomBar({ active }: { readonly active: string }) {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 flex h-16 items-stretch border-t border-[var(--ink-100)] bg-white/92 px-1 backdrop-blur-md md:hidden"
      aria-label="Sections"
    >
      {NAV_ITEMS.map((item) => {
        const isActive = active === item.href;
        const { Icon } = item;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-0.5 rounded-xl py-1 transition-colors",
              isActive ? "text-[var(--teal-600)]" : "text-[var(--ink-400)]",
            )}
          >
            <Icon className="h-5 w-5" strokeWidth={isActive ? 2 : 1.75} />
            <span className={cn("text-[10px] tracking-tight", isActive ? "font-bold" : "font-semibold")}>
              {item.short}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
