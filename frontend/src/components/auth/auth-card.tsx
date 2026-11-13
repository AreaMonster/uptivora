import type { ReactNode } from "react";

export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <>
      <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
      {subtitle && <p className="mt-2 text-[15px] text-fg-muted">{subtitle}</p>}
      <div className="mt-8">{children}</div>
      {footer && <div className="mt-8 border-t border-line pt-5 text-sm text-fg-muted">{footer}</div>}
    </>
  );
}

/** Only allow same-site relative redirects after login (prevents open redirects). */
export function safeNext(next: string | null | undefined, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}
