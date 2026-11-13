import Link from "next/link";
import { Logo } from "@/components/logo";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line">
        <div className="container-page flex h-14 items-center justify-between">
          <Logo />
          <Link href="/" className="text-sm text-fg-muted hover:text-fg">
            uptivora.com
          </Link>
        </div>
      </header>
      <main className="container-page flex-1 pb-20 pt-12 sm:pt-20">
        <div className="w-full max-w-[400px] sm:ml-[8%]">{children}</div>
      </main>
    </div>
  );
}
