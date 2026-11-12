import type { Metadata } from "next";
import { IncidentsPage } from "./incidents-view";

export const metadata: Metadata = { title: "Incidents" };

export default function Page() {
  return <IncidentsPage />;
}
