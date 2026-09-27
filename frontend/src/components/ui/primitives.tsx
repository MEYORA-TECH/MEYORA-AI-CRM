import { Loader2 } from "@/components/icons";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn, initials } from "@/lib/format";

/* ---------- Button ---------- */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary: "bg-jade text-jade-ink shadow-[0_6px_16px_-6px_var(--jade)] hover:brightness-110",
  secondary: "glass-dense text-ink hover:bg-glass-2",
  ghost: "text-ink-2 hover:bg-glass-2 hover:text-ink",
  danger: "bg-danger text-white hover:brightness-110",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "focus-ring inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] font-semibold transition",
        "disabled:cursor-not-allowed disabled:opacity-55 active:scale-[0.98]",
        size === "md" ? "h-10 px-4 text-sm" : "h-8 px-3 text-[13px]",
        variants[variant],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { label: string }>(
  function IconButton({ label, className, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        aria-label={label}
        title={label}
        className={cn(
          "focus-ring inline-flex size-9 items-center justify-center rounded-full text-ink-2 transition hover:bg-glass-2 hover:text-ink",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);

/* ---------- Form controls ---------- */

const control =
  "focus-ring w-full rounded-[var(--radius-control)] glass-dense px-3 text-sm text-ink placeholder:text-ink-3 transition " +
  "hover:border-line-strong disabled:opacity-60 aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(control, "h-10", className)} {...props} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(control, "min-h-24 py-2.5 leading-relaxed", className)} {...props} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select ref={ref} className={cn(control, "h-10 appearance-none bg-no-repeat pr-9", className)} style={{
      backgroundImage:
        "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%237c8781' stroke-width='2' viewBox='0 0 24 24'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      backgroundPosition: "right 0.75rem center",
    }} {...props}>
      {children}
    </select>
  );
});

export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  error?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-[13px] font-semibold text-ink-2">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-xs font-medium text-danger">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-3">{hint}</p>
      ) : null}
    </div>
  );
}

/* ---------- Display ---------- */

export type Tint = "slate" | "sky" | "violet" | "amber" | "orange" | "emerald" | "rose" | "jade" | "danger";

const tints: Record<Tint, string> = {
  slate: "bg-tint-slate text-ink-2",
  sky: "bg-tint-sky text-[#1d4f8a] dark:text-[#9cc5f5]",
  violet: "bg-tint-violet text-[#5132a8] dark:text-[#c3b1f7]",
  amber: "bg-tint-amber text-[#8a5200] dark:text-[#f2c47e]",
  orange: "bg-tint-orange text-[#9a3f0c] dark:text-[#f5ae80]",
  emerald: "bg-tint-emerald text-[#17634a] dark:text-[#8fe0c0]",
  rose: "bg-tint-rose text-[#9b1f45] dark:text-[#f5a3ba]",
  jade: "bg-jade-soft text-jade",
  danger: "bg-danger-soft text-danger",
};

export function Badge({ tint = "slate", children, className }: { tint?: Tint; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-xs font-semibold whitespace-nowrap", tints[tint], className)}>
      {children}
    </span>
  );
}

export function tintBg(tint: string) {
  return tints[(tint in tints ? tint : "slate") as Tint];
}

export function Card({ children, className, as: As = "section" }: { children: ReactNode; className?: string; as?: "section" | "div" | "article" }) {
  return <As className={cn("glass rounded-[var(--radius-card)]", className)}>{children}</As>;
}

export function CardHeader({ title, action, subtitle }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-none items-start justify-between gap-3 px-5 pt-4 pb-3">
      <div className="min-w-0">
        <h2 className="font-display text-[15px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Avatar({ name, size = 32, className }: { name?: string | null; size?: number; className?: string }) {
  // A stable hue per person, kept inside the pastel family.
  const hue = [...(name ?? "")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 150);
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-full font-bold text-[#14181b]", className)}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: `linear-gradient(140deg, hsl(${hue} 70% 86%), hsl(${(hue + 40) % 360} 60% 78%))`,
      }}
    >
      {initials(name)}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-5 animate-spin text-ink-3", className)} aria-label="Loading" />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-[var(--line-strong)]", className)} />;
}

export function EmptyState({
  icon,
  title,
  body,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-12 text-center", className)}>
      {icon ? <div className="mb-1 rounded-2xl bg-jade-soft p-3 text-jade">{icon}</div> : null}
      <p className="text-[15px] font-bold text-ink">{title}</p>
      {body ? <p className="max-w-sm text-sm text-ink-3">{body}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <p className="text-sm font-semibold text-danger">{message}</p>
      {onRetry ? <Button size="sm" onClick={onRetry}>Try again</Button> : null}
    </div>
  );
}
