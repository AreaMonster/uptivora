import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/legal-page";
import { LegalNoticeText } from "@/content/legal/pages";

export const metadata: Metadata = { title: "Legal notice", description: "Who operates Uptivora and how to reach us." };

export default function Page() {
  return (
    <LegalPage title="Legal notice">
      <LegalNoticeText />
    </LegalPage>
  );
}
