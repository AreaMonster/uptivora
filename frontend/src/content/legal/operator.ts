/**
 * Everything the legal pages need to know about the operator of the hosted service.
 *
 * Fill in every value in [brackets]. Then have the texts in ./pages.tsx reviewed by a lawyer
 * and set `reviewed: true`: until then every legal page shows a "draft" banner and the
 * review notes for the lawyer.
 */
export const OPERATOR = {
  /** Business name exactly as registered, or your full name for a sole proprietorship. */
  name: "[Business name or your full name]",
  /** e.g. "Einzelunternehmen" / "GmbH" — leave empty if not applicable. */
  legalForm: "[Legal form]",
  street: "[Street and number]",
  city: "[Postcode and city]",
  country: "Switzerland",
  /** General contact address shown on every page. */
  email: "[contact@your-domain.ch]",
  /** Address for data protection requests (can be the same). */
  privacyEmail: "[privacy@your-domain.ch]",
  /** Person responsible for the content (legal notice). */
  responsiblePerson: "[Your full name]",
  /** Swiss company identification number (UID), e.g. CHE-123.456.789 — empty if none. */
  uid: "[CHE-xxx.xxx.xxx or leave empty]",
  /** VAT number once registered for VAT — empty until then. */
  vatNumber: "",
  /** Where the hosted service runs, e.g. "Infomaniak Network SA, Geneva, Switzerland". */
  hostingProvider: "[Hosting provider, city, country]",
  /** Who delivers the emails, e.g. "Infomaniak Network SA, Switzerland". */
  emailProvider: "[Email (SMTP) provider, country]",
  /** Payment provider once real payments are enabled — empty while billing is off/test. */
  paymentProvider: "",
  /** Courts for disputes with business customers, usually the operator's seat. */
  jurisdiction: "[City of your registered seat]",
} as const;

export const LEGAL_STATUS = {
  /** Set to true only after a lawyer has reviewed the texts in pages.tsx. */
  reviewed: false,
  /** Shown as "Version of …" on every page; update whenever a text changes. */
  version: "13 November 2026",
};
