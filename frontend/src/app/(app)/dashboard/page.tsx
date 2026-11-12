import type { Metadata } from "next";
import { Suspense } from "react";
import { Dashboard } from "./dashboard";

export const metadata: Metadata = { title: "Monitors" };

export default function DashboardPage() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}
