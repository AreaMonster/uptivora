import type { Metadata } from "next";
import { PlansView } from "./view";

export const metadata: Metadata = { title: "Plans & pricing" };

export default function Page() {
  return <PlansView />;
}
