import * as React from "react";
import { cn } from "@/lib/utils";

const CONTROL =
  "w-full rounded-[var(--radius-sm)] border border-[var(--ink-200)] bg-white px-3 py-2.5 text-sm text-[var(--ink-900)] placeholder:text-[var(--ink-300)] transition-shadow focus:border-transparent focus:outline-none focus:ring-2 focus:ring-[var(--teal-500)] disabled:bg-[var(--ink-50)] disabled:text-[var(--ink-400)]";

export function Field({
  label,
  hint,
  required,
  htmlFor,
  children,
  className,
}: {
  readonly label: string;
  readonly hint?: string;
  readonly required?: boolean;
  readonly htmlFor?: string;
  readonly children: React.ReactNode;
  readonly className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-xs font-semibold text-[var(--ink-600)]">
        {label}
        {required && <span className="ml-0.5 text-[var(--red-600)]">*</span>}
      </label>
      {children}
      {hint && <p className="text-[11px] leading-snug text-[var(--ink-400)]">{hint}</p>}
    </div>
  );
}

export const TextInput = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(CONTROL, className)} {...props} />,
);
TextInput.displayName = "TextInput";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => <select ref={ref} className={cn(CONTROL, "pr-8", className)} {...props} />,
);
Select.displayName = "Select";

export const TextArea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(CONTROL, "resize-y", className)} {...props} />,
);
TextArea.displayName = "TextArea";
