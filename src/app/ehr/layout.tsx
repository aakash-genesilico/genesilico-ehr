import type { ReactNode } from "react";
import { AppShell } from "@/components/ehr/AppShell";

export default function EhrLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
