import type { Metadata } from "next";
import { MonitorsView } from "./view";

export const metadata: Metadata = { title: "Monitors" };

export default function Page() {
  return <MonitorsView />;
}
