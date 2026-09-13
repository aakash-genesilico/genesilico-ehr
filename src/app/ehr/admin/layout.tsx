import type { ReactNode } from "react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { SubTabs } from "@/components/ehr/SubTabs";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <PageShell>
      <PageHeader title="Admin Console" />
      <SubTabs
        tabs={[
          { href: "/ehr/admin", label: "Cancer centers" },
          { href: "/ehr/admin/hospitals", label: "Hospitals" },
          { href: "/ehr/admin/connections", label: "EHR connections" },
        ]}
      />
      {children}
    </PageShell>
  );
}
