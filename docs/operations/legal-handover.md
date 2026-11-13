# Legal and financial handover

The software side is ready; these items need a lawyer, a fiduciary/accountant or a contract
with a provider. This document is **not legal or tax advice** — it collects the facts those
professionals will ask for, and the questions to put to them.

## Facts about the processing (hosted service)

| Topic | Facts |
| --- | --- |
| Data subjects | Account holders; alert recipients they add; invited team members (self-hosted only) |
| Personal data | Email, optional name, time zone, password hash (Argon2id), sessions (IP address, browser, timestamps, 30 days max), alert recipients' emails, emails sent (subject, status), billing records, audit log of security-relevant actions (with IP) |
| Not personal data, but stored | Monitored URLs, check results, incidents and notes |
| Purposes | Providing monitoring and alerts; account security; billing; abuse prevention (rate limits) |
| Retention | Sessions: 30 days absolute; individual checks 3 days; failed checks and incident context 30 days; hourly summaries 400 days; incidents until the monitor or account is deleted; sent-email records 30 days; system logs 30 days; audit log 365 days (`UPTIVORA_AUDIT_RETENTION_DAYS`); backups 14–30 days; account data until deletion |
| Recipients / subprocessors | Hosting provider (server location: choose and name it); SMTP provider used for sending; payment provider once real billing starts. No analytics, no advertising, no AI services |
| Cookies | One session cookie after sign-in (strictly necessary). None before sign-in |
| Data subject rights | Settings → Your data (export as JSON); Settings → Delete account (immediate: account, monitors, history, recipients, sessions; payment and licence-order records are kept without the account link for accounting; audit entries keep the IP until their retention ends; backups age out); one-click unsubscribe for alert recipients |
| Security measures (TOMs) | See [../SECURITY.md](../SECURITY.md): TLS everywhere, Argon2id, CSRF/Origin checks, rate limits, SSRF protection, least-privilege containers, database on an internal network, nightly backups with weekly restore test |
| Transfers abroad | Only if the chosen hosting/SMTP/payment provider stores data outside Switzerland/EU |

Self-hosted: the customer runs everything; Uptivora receives no data at all (verified by
`test_no_phone_home.py`). Only the licence purchase (name, email, billing) is processed by
the hosted shop.

## Drafted documents

Drafts of all documents below are on the website (`/legal`, `/privacy`, `/terms`,
`/licence-agreement`, `/dpa`), written to match how the software actually behaves. Text:
`frontend/src/content/legal/pages.tsx`; operator details (name, address, providers):
`frontend/src/content/legal/operator.ts`. Until `LEGAL_STATUS.reviewed` is set to `true`, every
page shows a "draft" banner and "For review" notes with the open questions for the lawyer.
Sign-up and both checkouts link to them (hosted edition only).

To finish: fill in `operator.ts`, have the lawyer review the five pages and answer the review
notes, then set `reviewed: true` and update `version`.

### What each document covers

1. **Terms of service (hosted)** — plans and limits, monthly billing, upgrade/downgrade and
   cancellation rules as implemented (upgrades prorated immediately, downgrades and
   cancellations at period end, 7-day grace after a failed renewal), acceptable use (only
   monitor sites you are allowed to monitor), no guaranteed uptime of the service unless an
   SLA is offered, liability limits.
2. **Privacy policy** under the Swiss revDSG and, for EU customers, the GDPR — based on the
   table above.
3. **Data processing agreement** for business customers (they control their recipients'
   addresses) with the subprocessor list.
4. **Self-hosted licence agreement (EULA)** — perpetual, per installation, updates included,
   no support or hosting included, no redistribution; what happens to evaluation limits.
5. **Legal notice (Impressum)** with the operator's name and address.
6. **Refund / withdrawal policy** — questions: EU consumers' 14-day withdrawal right for
   digital services and downloadable licences; how a refund interacts with an already issued
   licence file (it cannot be revoked offline).

They are linked in the site footer and as a notice at sign-up and checkout; ask the lawyer
whether a checkbox is preferred instead of the notice.

## Questions for the fiduciary / accountant

- Swiss VAT: registration threshold, and whether to register voluntarily.
- Selling to EU consumers and businesses: VAT on electronically supplied services (OSS,
  reverse charge), invoices with the required details.
- Invoices: the app records payments and sends receipts; are the receipts sufficient as
  invoices, or is an accounting/invoicing system needed?

## Payment provider onboarding

Real payments stay disabled until a provider account exists. Prepare: company details,
website with terms/privacy/legal notice live, description of the product, refund policy.
Then implement the provider in `backend/app/billing/providers.py` (the interface and webhook
signature verification are in place), switch `UPTIVORA_BILLING_PROVIDER`, and run the billing
tests against the provider's test mode before enabling live keys.
