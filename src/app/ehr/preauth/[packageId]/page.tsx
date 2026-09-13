"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { PageShell } from "@/components/ehr/PageHeader";
import { Card } from "@/components/ui/Card";
import { ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

/**
 * A package is not a place — it belongs to a patient.
 *
 * Old links land here and are forwarded into that patient's workspace, so the
 * casebook and the authorisation stay one continuous piece of work.
 */
export default function PackageRedirect() {
  const { packageId } = useParams<{ packageId: string }>();
  const router = useRouter();
  const pkg = useApi(() => api.package(packageId), [packageId]);

  React.useEffect(() => {
    if (pkg.data?.casebookId) router.replace(`/ehr/casebooks/${pkg.data.casebookId}`);
  }, [pkg.data?.casebookId, router]);

  return (
    <PageShell>
      {pkg.error ? <Card><ErrorState error={pkg.error} onRetry={pkg.reload} /></Card> : <LoadingSkeleton count={3} />}
    </PageShell>
  );
}
