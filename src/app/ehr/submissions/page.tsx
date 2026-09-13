"use client";

import Link from "next/link";
import { ArrowRight, Send } from "lucide-react";
import { PageHeader, PageShell } from "@/components/ehr/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, SectionCard } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { pluralize } from "@/lib/utils";

export default function SubmissionsPage() {
  const caps = useApi(() => api.capabilities(), []);
  const packages = useApi(() => api.packages(), []);

  const submitted = (packages.data?.results ?? []).filter((p) => p.submittedAt);
  const pa278 = caps.data?.stedi.prior_auth_278;

  return (
    <PageShell>
      <PageHeader title="Submissions" subtitle={pluralize(submitted.length, "submission")} />

      {/* The reason nothing can be submitted is the most important fact on this
          screen, so it leads rather than hiding behind an empty list. */}
      {pa278 && !pa278.available && (
        <SectionCard title="Prior-authorisation submission is unavailable">
          <p className="text-[13px] leading-relaxed text-[var(--ink-500)]">{pa278.reason}</p>
          <p className="mt-2 text-[13px] leading-relaxed text-[var(--ink-400)]">
            Packages can still be built and priced against a real eligibility response. They simply
            cannot be transmitted to the payer from here.
          </p>
        </SectionCard>
      )}

      {packages.loading && <LoadingSkeleton count={2} />}
      {packages.error && <Card><ErrorState error={packages.error} onRetry={packages.reload} /></Card>}

      {!packages.loading && !packages.error && submitted.length === 0 && (
        <Card>
          <EmptyState
            title="Nothing submitted"
            description="No package has been transmitted to a payer."
            icon={<Send className="h-5 w-5" strokeWidth={1.75} />}
            action={
              <Link href="/ehr/preauth">
                <Button size="sm" variant="secondary">
                  Go to Pre-Auth
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            }
          />
        </Card>
      )}
    </PageShell>
  );
}
