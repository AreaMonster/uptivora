import Link from "next/link";
import { cn } from "@/lib/format";

/** The mark is a status light: the one thing Uptivora tells you. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={cn("h-3.5 w-3.5", className)}>
      <circle cx="8" cy="8" r="7" className="fill-up" />
      <circle cx="8" cy="8" r="2.6" className="fill-canvas" />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-[17px] font-semibold tracking-[-0.02em] text-fg">uptivora</span>
    </Link>
  );
}
