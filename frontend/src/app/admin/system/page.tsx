import type { Metadata } from "next";
import { SystemView } from "./view";

export const metadata: Metadata = { title: "System" };

export default function Page() {
  return <SystemView />;
}
