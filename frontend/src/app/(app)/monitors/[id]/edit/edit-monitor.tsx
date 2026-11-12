"use client";

import { useParams } from "next/navigation";
import { MonitorForm } from "@/components/app/monitor-form";
import { Alert, PageHeader, Skeleton } from "@/components/ui";
import type { Monitor } from "@/lib/api";
import { useApi } from "@/lib/use-api";

export function EditMonitor() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<{ monitor: Monitor }>(`/api/monitors/${id}`);
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!data) return <Skeleton className="h-96" />;
  return (
    <>
      <PageHeader title={`Edit ${data.monitor.name}`} />
      <MonitorForm monitor={data.monitor} />
    </>
  );
}
