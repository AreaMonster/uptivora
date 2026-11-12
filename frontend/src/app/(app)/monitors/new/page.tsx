import type { Metadata } from "next";
import { MonitorForm } from "@/components/app/monitor-form";
import { PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Add monitor" };

export default function NewMonitorPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Add monitor" description="Uptivora starts checking within seconds of saving." />
      <MonitorForm />
    </div>
  );
}
