import type { Metadata } from "next";
import { AdminOverviewView } from "./overview-view";

export const metadata: Metadata = { title: "Overview" };

export default function Page() {
  return <AdminOverviewView />;
}
