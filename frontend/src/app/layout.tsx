import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Uptivora — Website uptime & SSL monitoring",
    template: "%s · Uptivora",
  },
  description:
    "Uptivora checks your websites around the clock, tracks response times and SSL certificates, and emails you the moment something goes down. Hosted or self-hosted.",
  applicationName: "Uptivora",
};

export const viewport: Viewport = {
  themeColor: "#060a12",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
