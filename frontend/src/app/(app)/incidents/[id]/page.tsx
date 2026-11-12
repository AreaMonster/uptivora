import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { IncidentDetailView } from "./incident-detail";

export const metadata: Metadata = { title: "Incident" };

export default function IncidentPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[480px]" />}>
      <IncidentDetailView />
    </Suspense>
  );
}
