import * as React from "react";
import { cn } from "@/lib/utils";

/** Thin completion bar. Colour follows the value, not the caller. */
export function ProgressBar({
  value,
  className,
  showLabel = false,
}: {
  readonly value: number;
  readonly className?: string;
  readonly showLabel?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const fill =
    clamped >= 90 ? "var(--green-600)" : clamped >= 60 ? "var(--teal-600)" : clamped >= 35 ? "var(--amber-600)" : "var(--red-600)";

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--ink-100)]"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full transition-all" style={{ width: `${clamped}%`, background: fill }} />
      </div>
      {showLabel && (
        <span className="shrink-0 text-xs font-semibold tabular-nums text-[var(--ink-500)]">{clamped}%</span>
      )}
    </div>
  );
}

/** Small circular score dial used for the CancerAI / Digital Twin numbers. */
export function ScoreDial({
  value,
  label,
  size = 64,
}: {
  readonly value: number;
  readonly label: string;
  readonly size?: number;
}) {
  const pct = Math.max(0, Math.min(1, value));
  const stroke = 5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const tone = pct >= 0.85 ? "var(--green-600)" : pct >= 0.7 ? "var(--teal-600)" : "var(--amber-600)";

  return (
    <div className="flex items-center gap-3">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${Math.round(pct * 100)}%`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--ink-100)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          fontSize={size * 0.26}
          fontWeight="700"
          fill="var(--ink-900)"
        >
          {Math.round(pct * 100)}
        </text>
      </svg>
      <span className="whitespace-pre-line text-xs font-medium leading-snug text-[var(--ink-500)]">{label}</span>
    </div>
  );
}
