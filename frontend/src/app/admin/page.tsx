import type { Metadata } from "next";
import { AdminOverviewView } from "./overview-view";

export const metadata: Metadata = { title: { absolute: "Overview · Admin · Uptivora" } };

export default function Page() {
  return <AdminOverviewView />;
}
