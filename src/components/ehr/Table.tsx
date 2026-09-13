import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Tables here always live inside their own horizontal scroller — a wide
 * coding or coverage table must never make the page itself scroll sideways
 * on a phone.
 */
export function TableWrap({ children, className }: { readonly children: React.ReactNode; readonly className?: string }) {
  return (
    <div className={cn("table-scroll thin-scrollbar -mx-4 px-4 sm:mx-0 sm:px-0", className)}>
      <table className="w-full min-w-[640px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Th({ className, align = "left", ...rest }: React.ThHTMLAttributes<HTMLTableCellElement> & { align?: "left" | "right" | "center" }) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b border-[var(--ink-100)] px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-400)]",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
        className,
      )}
      {...rest}
    />
  );
}

export function Td({ className, align = "left", ...rest }: React.TdHTMLAttributes<HTMLTableCellElement> & { align?: "left" | "right" | "center" }) {
  return (
    <td
      className={cn(
        "border-b border-[var(--ink-50)] px-3 py-3 align-top text-[var(--ink-700)]",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
      {...rest}
    />
  );
}
