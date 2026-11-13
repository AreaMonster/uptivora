"use client";

import Link from "next/link";
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  useEffect,
  useId,
  useRef,
} from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { MonitorStatus } from "@/lib/api";
import { cn } from "@/lib/format";

// --- Buttons ---------------------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary/85",
  secondary: "border border-line-strong bg-surface text-fg hover:border-fg-subtle hover:bg-hover",
  ghost: "text-fg-muted hover:bg-hover hover:text-fg",
  danger: "bg-down text-canvas hover:bg-down-ink",
};
const sizes = { sm: "h-8 px-3 text-[13px]", md: "h-9 px-3.5 text-sm", lg: "h-11 px-5 text-[15px]" };
const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[3px] font-medium transition-colors";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: keyof typeof sizes;
  loading?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cn(
        base,
        "disabled:cursor-not-allowed disabled:opacity-55",
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: keyof typeof sizes;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        base,
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {children}
    </Link>
  );
}

// --- Form fields -----------------------------------------------------------------------------

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="label">
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1.5 text-xs text-down-ink" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="hint">{hint}</p>
      ) : null}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: ReactNode;
  error?: string;
};

export function TextField({ label, hint, error, className, id, ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={inputId} className={className}>
      <input
        id={inputId}
        {...rest}
        aria-invalid={error ? true : undefined}
        className={cn("input", error && "input-error")}
      />
    </Field>
  );
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  hint?: ReactNode;
  error?: string;
};

export function SelectField({ label, hint, error, className, id, children, ...rest }: SelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={selectId} className={className}>
      <select
        id={selectId}
        {...rest}
        className={cn("input appearance-none bg-[length:16px] pr-9", error && "input-error")}
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238a8678' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 0.7rem center",
        }}
      >
        {children}
      </select>
    </Field>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
  ariaLabel,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  const id = useId();
  return (
    <div className={cn("flex items-start justify-between gap-4", label ? "py-2" : "py-0")}>
      {label && (
        <div>
          <label htmlFor={id} className="text-sm font-medium text-fg">
            {label}
          </label>
          {description && <p className="mt-0.5 text-xs text-fg-muted">{description}</p>}
        </div>
      )}
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-[3px] border transition-colors",
          checked ? "border-up bg-up" : "border-line-strong bg-sunken",
          disabled && "opacity-50",
        )}
      >
        <span
          className={cn(
            "inline-block h-3.5 w-3.5 rounded-[2px] transition-transform",
            checked ? "translate-x-[17px] bg-white" : "translate-x-[2px] bg-fg-subtle",
          )}
        />
      </button>
    </div>
  );
}

// --- Feedback --------------------------------------------------------------------------------

const alertStyles = {
  info: ["border-accent bg-accent-soft", Info, "text-accent"],
  success: ["border-up bg-up-soft", CheckCircle2, "text-up"],
  warning: ["border-warn bg-warn-soft", AlertTriangle, "text-warn"],
  error: ["border-down bg-down-soft", XCircle, "text-down"],
} as const;

export function Alert({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof alertStyles;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const [style, Icon, iconColor] = alertStyles[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex gap-3 border-l-[3px] px-4 py-3 text-sm text-fg", style, className)}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", iconColor)} aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-0.5", "text-fg-muted")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-fg-muted", className)} aria-label="Loading" />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-[3px] bg-muted", className)} />;
}

// --- Status ----------------------------------------------------------------------------------

const statusMeta: Record<MonitorStatus, { label: string; dot: string; text: string }> = {
  up: { label: "Up", dot: "bg-up", text: "text-up-ink" },
  down: { label: "Down", dot: "bg-down status-blink", text: "text-down-ink" },
  pending: { label: "Pending", dot: "border-[1.5px] border-accent", text: "text-accent-ink" },
  paused: { label: "Paused", dot: "border-[1.5px] border-paused", text: "text-fg-subtle" },
};

export function StatusDot({ status, className }: { status: MonitorStatus; className?: string }) {
  return (
    <span
      className={cn("inline-block h-2 w-2 shrink-0 rounded-full", statusMeta[status].dot, className)}
      aria-hidden
    />
  );
}

export function StatusPill({ status }: { status: MonitorStatus }) {
  const meta = statusMeta[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-xs font-medium uppercase tracking-wide",
        meta.text,
      )}
    >
      <StatusDot status={status} />
      {meta.label}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "warn" | "down" | "up";
}) {
  const tones = {
    neutral: "border-line-strong text-fg-muted",
    accent: "border-accent/50 text-accent-ink",
    warn: "border-warn/60 text-warn-ink",
    down: "border-down/60 text-down-ink",
    up: "border-up/50 text-up-ink",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[2px] border px-1.5 py-px font-mono text-[10.5px] font-medium uppercase leading-4 tracking-wide",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

// --- Layout helpers --------------------------------------------------------------------------

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.01em] text-fg">{title}</h1>
        {description && <div className="mt-1 text-sm text-fg-muted">{description}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-dashed border-line-strong px-6 py-12 sm:px-10">
      {icon && <div className="mb-3 text-fg-subtle [&_svg]:h-5 [&_svg]:w-5">{icon}</div>}
      <h2 className="text-lg font-semibold">{title}</h2>
      {children && <div className="mt-1.5 max-w-lg text-sm text-fg-muted">{children}</div>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

// --- Confirm dialog (native <dialog>) --------------------------------------------------------

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  tone = "danger",
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  tone?: "danger" | "primary";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="m-auto w-[min(440px,calc(100vw-32px))] rounded-[var(--radius-card)] border border-line-strong bg-surface p-0 text-fg shadow-[0_12px_40px_-12px_rgb(0_0_0/0.35)] backdrop:bg-black/40"
    >
      <div className="p-6">
        <h2 className="text-lg font-semibold">{title}</h2>
        {children && <div className="mt-2 text-sm text-fg-muted">{children}</div>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel} disabled={loading}>
            Cancel
          </Button>
          <Button variant={tone} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
