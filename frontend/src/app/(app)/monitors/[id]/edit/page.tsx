import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { EditMonitor } from "./edit-monitor";

export const metadata: Metadata = { title: "Edit monitor" };

export default function EditMonitorPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <Suspense fallback={<Skeleton className="h-96" />}>
        <EditMonitor />
      </Suspense>
    </div>
  );
}
