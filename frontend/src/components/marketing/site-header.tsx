"use client";

import Link from "next/link";
import { useState } from "react";
import { Logo } from "@/components/logo";
import { ButtonLink } from "@/components/ui";

const NAV = [
  { href: "/pricing", label: "Pricing" },
  { href: "/self-hosted", label: "Self-hosted" },
  { href: "/docs", label: "Docs" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className="container-page flex h-14 items-center gap-8">
        <Logo />
        <nav className="hidden items-center gap-6 md:flex" aria-label="Main">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="text-sm text-fg-muted hover:text-fg">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto hidden items-center gap-5 md:flex">
          <Link href="/login" className="text-sm text-fg-muted hover:text-fg">
            Sign in
          </Link>
          <ButtonLink href="/register" size="sm">
            Create account
          </ButtonLink>
        </div>
        <button
          type="button"
          className="ml-auto -mr-2 px-2 py-1 font-mono text-xs uppercase tracking-wide text-fg-muted hover:text-fg md:hidden"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Close" : "Menu"}
        </button>
      </div>
      {open && (
        <nav className="border-t border-line md:hidden" aria-label="Mobile">
          <div className="container-page flex flex-col py-2">
            {[...NAV, { href: "/login", label: "Sign in" }, { href: "/register", label: "Create account" }].map(
              (item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="border-b border-line py-3 text-[15px] last:border-0"
                >
                  {item.label}
                </Link>
              ),
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
