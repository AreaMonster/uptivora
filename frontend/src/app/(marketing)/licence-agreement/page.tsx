import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/legal-page";
import { LicenceAgreementText } from "@/content/legal/pages";

export const metadata: Metadata = { title: "Self-hosted licence agreement", description: "What a self-hosted Uptivora licence allows." };

export default function Page() {
  return (
    <LegalPage title="Self-hosted licence agreement">
      <LicenceAgreementText />
    </LegalPage>
  );
}
