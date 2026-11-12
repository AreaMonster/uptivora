import Link from "next/link";
import { cn } from "@/lib/format";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("h-7 w-7", className)}>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="#0F1726" stroke="#2F3D57" />
      <path
        d="M5 17h5.2l2.3-6 4.2 12 3-8.5 1.8 2.5H27"
        fill="none"
        stroke="#2DD4BF"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-[0.18em] text-fg">UPTIVORA</span>
    </Link>
  );
}
