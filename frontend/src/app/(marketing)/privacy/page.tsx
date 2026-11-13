import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/legal-page";
import { PrivacyText } from "@/content/legal/pages";

export const metadata: Metadata = { title: "Privacy policy", description: "Which personal data Uptivora processes, why, and your rights." };

export default function Page() {
  return (
    <LegalPage title="Privacy policy">
      <PrivacyText />
    </LegalPage>
  );
}
