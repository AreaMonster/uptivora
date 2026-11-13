import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Uptivora — Website uptime & SSL monitoring",
    template: "%s · Uptivora",
  },
  description:
    "Uptivora checks your websites every few minutes or every 30 seconds, watches their SSL certificates and emails you when one stops answering. Hosted from CHF 5 a month, or self-hosted with a one-time licence.",
  applicationName: "Uptivora",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f2ed" },
    { media: "(prefers-color-scheme: dark)", color: "#141412" },
  ],
  colorScheme: "light dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
