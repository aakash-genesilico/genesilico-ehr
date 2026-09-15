"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";

/* Ontada's grant can only be restored by a person signing in, so a dead
   connection has to be visible from wherever someone is working — not only on
   the Connect page they had no reason to open. The backend renews on a timer,
   which makes this rare; when it does appear it means retrying will not help.

   Deliberately silent about a merely-expired token: the keeper renews those
   without anyone noticing, and a banner that cried wolf every 30 minutes would
   be ignored by the time it mattered. */
export function ReconnectBanner() {
  const pathname = usePathname() ?? "";
  const [needed, setNeeded] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const s = await api.ontadaStatus();
        if (alive) setNeeded(Boolean(s.keeper?.reauth_required) || (s.configured && !s.connected));
      } catch {
        // A backend that cannot be reached is a different problem, and the page
        // it belongs to reports it. Saying "reconnect to Ontada" here would send
        // someone to sign in to fix something a sign-in cannot fix.
      }
    };
    void check();
    const t = setInterval(check, 60_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (!needed || pathname.startsWith("/ehr/connect")) return null;

  return (
    <div className="flex items-start gap-2.5 border-b border-[var(--amber-100)] bg-[var(--amber-50)] px-4 py-2.5 text-[13px] text-[var(--amber-700)] md:px-6">
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="min-w-0">
        Not connected to Ontada — live chart reads will fail until a practitioner signs in.
        Records already imported stay readable.{" "}
        <Link href="/ehr/connect" className="font-semibold underline underline-offset-2">
          Reconnect
        </Link>
      </span>
    </div>
  );
}
