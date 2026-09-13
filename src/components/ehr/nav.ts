import {
  Building2,
  ClipboardCheck,
  FolderOpen,
  LayoutDashboard,
  PlugZap,
  Send,
  type LucideIcon,
} from "lucide-react";

export interface EhrNavItem {
  href: string;
  label: string;
  /** Shorter form for the mobile bottom bar. */
  short: string;
  Icon: LucideIcon;
}

export const NAV_ITEMS: EhrNavItem[] = [
  { href: "/ehr", label: "Overview", short: "Home", Icon: LayoutDashboard },
  { href: "/ehr/admin", label: "Admin Console", short: "Admin", Icon: Building2 },
  { href: "/ehr/connect", label: "Ontada Connect", short: "Connect", Icon: PlugZap },
  { href: "/ehr/casebooks", label: "Casebooks", short: "Casebook", Icon: FolderOpen },
  { href: "/ehr/preauth", label: "Pre-Auth", short: "Pre-Auth", Icon: ClipboardCheck },
  { href: "/ehr/submissions", label: "Submissions", short: "Submit", Icon: Send },
];

/** Longest matching href wins, so /ehr doesn't light up on every child route. */
export function activeNavHref(pathname: string): string {
  const matches = NAV_ITEMS.filter((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
  return matches.sort((a, b) => b.href.length - a.href.length)[0]?.href ?? "/ehr";
}
