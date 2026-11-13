/*
 * Legal texts for the hosted service and the self-hosted licence.
 *
 * DRAFTS written to match how the software actually works (retention periods, cookies,
 * billing rules, licence behaviour). They are not legal advice: have them reviewed before
 * relying on them, then set LEGAL_STATUS.reviewed in ./operator.ts.
 */
import Link from "next/link";
import { Op, ReviewNote } from "@/components/legal/legal-page";
import { OPERATOR } from "@/content/legal/operator";

function Address() {
  return (
    <p>
      <Op v="name" />
      {OPERATOR.legalForm && <>, <Op v="legalForm" /></>}
      <br />
      <Op v="street" />
      <br />
      <Op v="city" />, <Op v="country" />
      <br />
      Email: <Op v="email" />
    </p>
  );
}

/* --- Legal notice (Impressum) ------------------------------------------------------------- */

export function LegalNoticeText() {
  return (
    <>
      <h2>Operator of uptivora.com</h2>
      <Address />
      <p>
        Responsible for the content: <Op v="responsiblePerson" />
        {OPERATOR.uid && <><br />Company identification number (UID): <Op v="uid" /></>}
        {OPERATOR.vatNumber && <><br />VAT number: <Op v="vatNumber" /></>}
      </p>
      <h2>Liability for content and links</h2>
      <p>
        We take care that the information on this website is correct and up to date, but cannot
        guarantee it. Links to other websites are provided for convenience; we have no control
        over their content and accept no responsibility for it.
      </p>
      <h2>Copyright</h2>
      <p>
        Texts, design and software of Uptivora are protected by copyright. Uptivora uses open-source
        components under their respective licences.
      </p>
      <ReviewNote>
        Swiss law (UWG Art. 3 para. 1 lit. s) requires clear identity and contact details for
        businesses that sell online. Check whether a commercial register entry exists and must be
        mentioned, and whether a postal address other than a home address is preferred.
      </ReviewNote>
    </>
  );
}

/* --- Privacy policy ---------------------------------------------------------------------- */

export function PrivacyText() {
  return (
    <>
      <p>
        This policy explains which personal data Uptivora processes when you visit uptivora.com
        and when you use the hosted service, why, and what your rights are. It is written for the
        Swiss Federal Act on Data Protection (FADP/revDSG) and, where it applies, the EU General
        Data Protection Regulation (GDPR).
      </p>

      <h2>1. Who is responsible</h2>
      <Address />
      <p>
        Data protection requests: <Op v="privacyEmail" />
      </p>

      <h2>2. Visiting the website</h2>
      <p>
        Pages are delivered without analytics, advertising, tracking pixels, external fonts or
        third-party scripts. The web server keeps no access logs with visitors’ IP addresses. To
        protect sign-in and sign-up forms against abuse, we keep short-lived counters per IP
        address for at most 24 hours.
      </p>
      <p>
        <strong>Cookies:</strong> no cookie is set until you sign in. Signing in sets one
        strictly necessary session cookie, which keeps you signed in and is deleted when you sign
        out or the session expires (after 7 days of inactivity, at the latest after 30 days).
      </p>

      <h2>3. Your account</h2>
      <ul>
        <li><strong>Account data:</strong> email address, optional name, time zone, a hashed password (Argon2id; we never see or store the password itself).</li>
        <li><strong>Sessions:</strong> IP address, browser type and times of use of each signed-in session, shown to you under Settings → Security, deleted 7 days after the session ends.</li>
        <li><strong>Security log:</strong> security-relevant actions (sign-ins, password changes, plan changes) with IP address, kept 365 days.</li>
        <li><strong>Emails we send:</strong> account emails (confirmations, password resets, receipts) and the alerts you configure. We keep the recipient, subject and delivery status for 30 days. We send no newsletters or advertising.</li>
      </ul>
      <p>
        Purpose and legal basis: providing the service you signed up for (contract, GDPR Art. 6
        para. 1 lit. b) and keeping it secure (legitimate interest, Art. 6 para. 1 lit. f).
      </p>

      <h2>4. Monitoring data and alert recipients</h2>
      <p>
        We store the website addresses you monitor and the results of the checks: every check for
        3 days, failed checks and the checks around each outage for 30 days, hourly summaries for
        400 days, and incidents with your notes until you delete the monitor or your account.
        This information is about websites rather than people.
      </p>
      <p>
        If you add extra alert recipients, we email each address once to ask for confirmation
        and only send alerts after it has confirmed. Every alert contains a link to unsubscribe
        with one click. For business customers we process these addresses on their behalf under
        the <Link href="/dpa">data processing agreement</Link>.
      </p>

      <h2>5. Payments</h2>
      {OPERATOR.paymentProvider ? (
        <p>
          Payments are processed by <Op v="paymentProvider" />, which receives your payment details
          directly; we only receive the result and the amount. We keep payment records as long
          as accounting law requires (in Switzerland 10 years), even after an account is deleted,
          without the link to the account.
        </p>
      ) : (
        <p>
          Online payment is not active yet. Where checkout is shown in test mode, no payment
          details are requested or stored. Records of orders and payments are kept as long as
          accounting law requires (in Switzerland 10 years), without the link to a deleted account.
        </p>
      )}

      <h2>6. Who receives data</h2>
      <p>
        We do not sell or rent personal data and do not use it for advertising. Service providers
        process data for us under contract:
      </p>
      <ul>
        <li>Hosting: <Op v="hostingProvider" /></li>
        <li>Email delivery: <Op v="emailProvider" /></li>
        {OPERATOR.paymentProvider && <li>Payments: <Op v="paymentProvider" /></li>}
      </ul>
      <p>
        If one of them processes data outside Switzerland or the EU/EEA, we do so only with
        adequate safeguards such as the EU Standard Contractual Clauses.
      </p>
      <ReviewNote>
        Confirm the countries of all providers once chosen; if any is outside CH/EU/EEA, name the
        safeguard. Add the payment provider before real payments start.
      </ReviewNote>

      <h2>7. How long we keep data</h2>
      <p>
        As listed above. When you delete your account (Settings → Delete account), the account,
        monitors, history, recipients and sessions are deleted immediately. Backups
        are overwritten within 30 days. Payment records are kept as required by law, as above.
      </p>

      <h2>8. Security</h2>
      <p>
        Encrypted connections (TLS) for all traffic, hashed passwords and tokens, protection
        against cross-site request forgery and automated sign-in attempts, isolated services with
        minimal privileges, and daily backups that are test-restored every week.
      </p>

      <h2>9. Your rights</h2>
      <p>
        You can request access to your data, correction, deletion, restriction, and a copy in a
        portable format; and object to processing based on legitimate interests. Much of this you
        can do yourself: <strong>Settings → Your data</strong> downloads everything we store about
        you, and <strong>Settings → Delete account</strong> deletes it. For anything else write to{" "}
        <Op v="privacyEmail" />.
      </p>
      <p>
        You can complain to the Swiss Federal Data Protection and Information Commissioner
        (FDPIC, edoeb.admin.ch) or, in the EU, to the data protection authority of your country.
      </p>

      <h2>10. No automated decisions</h2>
      <p>
        We make no decisions about you based solely on automated processing and do not use
        artificial intelligence on your data.
      </p>

      <h2>11. Changes</h2>
      <p>
        We may update this policy when the service or the law changes. The version date is at the
        top; significant changes are announced by email to account holders.
      </p>
      <ReviewNote>
        Check whether an EU representative (GDPR Art. 27) is needed if EU customers are targeted,
        and whether a record of processing activities is required.
      </ReviewNote>
    </>
  );
}

/* --- Terms of service (hosted) ----------------------------------------------------------- */

export function TermsText() {
  return (
    <>
      <h2>1. Scope</h2>
      <p>
        These terms apply to the hosted website-monitoring service “Uptivora” offered by{" "}
        <Op v="name" /> (“we”) at uptivora.com. By creating an account you accept them. The
        self-hosted edition is governed by the{" "}
        <Link href="/licence-agreement">self-hosted licence agreement</Link>. How we handle
        personal data is described in the <Link href="/privacy">privacy policy</Link>.
      </p>

      <h2>2. The service</h2>
      <p>
        Uptivora requests the web addresses you enter at the interval you choose, records the
        results, and emails you about outages, recoveries and expiring certificates. Checks run
        from one location; a failure is confirmed by a second check before an alert is sent.
        Monitoring can only observe what is reachable from our servers and cannot guarantee that
        every outage is detected or that every email arrives in time.
      </p>

      <h2>3. Your account</h2>
      <p>
        You must give a valid email address and keep your password confidential. You are
        responsible for activity in your account. Accounts are personal; for teams, each person
        uses their own account.
      </p>

      <h2>4. Acceptable use</h2>
      <ul>
        <li>Only monitor websites you operate or are authorised to monitor.</li>
        <li>Do not use the service to attack, overload or probe systems, or to send unsolicited email.</li>
        <li>Do not try to circumvent limits, security measures or access other customers’ data.</li>
      </ul>
      <p>
        For security, the service refuses private, internal and reserved network addresses. We may
        suspend monitors or accounts that endanger the service or third parties, and will tell you
        why unless the law prevents it.
      </p>

      <h2>5. Plans, prices and payment</h2>
      <ul>
        <li>Plans and prices are shown on the <Link href="/pricing">pricing page</Link> and at checkout. Prices are in Swiss francs{OPERATOR.vatNumber ? ", including VAT" : ""}.</li>
        <li>Plans are paid monthly in advance and renew automatically each month until cancelled.</li>
        <li>An upgrade takes effect immediately; the price difference for the rest of the current month is charged at once.</li>
        <li>A downgrade or cancellation takes effect at the end of the paid month; there is no refund for the remaining days.</li>
        <li>If a renewal payment fails, we retry daily for 7 days, during which the plan stays active. Afterwards the plan ends.</li>
        <li>When a plan ends or its limit is lower than your usage, monitors above the limit are paused, never deleted.</li>
        <li>We may change prices with at least 30 days’ notice by email; the new price applies from the next renewal and you may cancel before.</li>
      </ul>
      <ReviewNote>
        Consumers in the EU have a 14-day right of withdrawal for digital services. Decide whether
        to grant it (refund on request within 14 days) or to obtain the customer’s express consent
        to immediate performance at checkout, and adapt this section and the checkout text.
      </ReviewNote>

      <h2>6. Availability and changes</h2>
      <p>
        We work to keep the service available and maintained but do not promise uninterrupted
        operation. Maintenance is done with as little interruption as possible. We may develop
        the service further; we will not remove core functions of a paid plan during a paid
        month.
      </p>

      <h2>7. Your data</h2>
      <p>
        Data you enter remains yours. You can export it (Settings → Your data) and delete your
        account at any time; deletion is immediate. For business customers who add other
        people’s email addresses as alert recipients, the{" "}
        <Link href="/dpa">data processing agreement</Link> forms part of these terms.
      </p>

      <h2>8. Liability</h2>
      <p>
        We are liable without limitation for damage caused intentionally or through gross
        negligence. Otherwise our liability is excluded to the extent permitted by law,
        in particular for indirect damage, lost profit and damage caused by outages of monitored
        websites, missed or delayed alerts, or events outside our control.
      </p>
      <ReviewNote>
        Swiss law does not allow excluding liability for intent and gross negligence (OR Art. 100);
        consumer protection rules in the customer’s country may limit exclusions further. Consider
        a liability cap for business customers (e.g. the fees paid in the last 12 months).
      </ReviewNote>

      <h2>9. Termination</h2>
      <p>
        You can cancel your plan in the billing settings and delete your account at any time.
        We may terminate an account with 30 days’ notice, or immediately for serious breaches of
        these terms. Fees for the current month are not refunded on termination for breach.
      </p>

      <h2>10. Changes to these terms</h2>
      <p>
        We may change these terms with at least 30 days’ notice by email. If you do not agree,
        you may cancel before the change takes effect; otherwise the new terms apply.
      </p>

      <h2>11. Applicable law and jurisdiction</h2>
      <p>
        Swiss law applies, excluding the UN Convention on Contracts for the International Sale
        of Goods. Courts at <Op v="jurisdiction" /> have jurisdiction for business customers.
        Consumers may also sue and be sued at their place of residence where the law provides so.
      </p>
    </>
  );
}

/* --- Self-hosted licence agreement (EULA) ------------------------------------------------- */

export function LicenceAgreementText() {
  return (
    <>
      <p>
        This agreement is between <Op v="name" /> (“we”) and the licensee named in the licence
        file (“you”). It applies when you buy a self-hosted licence or install Uptivora
        self-hosted, and together with the terms shown at purchase.
      </p>

      <h2>1. Licence</h2>
      <p>
        We grant you a perpetual, non-exclusive right to install and use the Uptivora
        self-hosted software for your own monitoring, in <strong>one production installation</strong>{" "}
        per licence, within the limits of the edition stated in your licence file (number of
        monitored websites, user accounts and shortest check interval). Additional
        installations for testing, staging or recovery from a backup are allowed if they are not
        used for production monitoring at the same time.
      </p>

      <h2>2. Evaluation</h2>
      <p>
        Without a licence the software runs in evaluation mode with reduced limits. You may use it
        so for as long as you like.
      </p>

      <h2>3. Updates</h2>
      <p>
        The licence includes all future versions of the self-hosted edition published by us for
        as long as we offer the product. Installing updates is your decision and responsibility.
        Every version accepts your licence file; a new file is only issued if we must replace a
        signing key, at no cost to you.
      </p>

      <h2>4. What you may not do</h2>
      <ul>
        <li>Give, sell, rent or publish the software or your licence file to others, except together with a transfer under section 6.</li>
        <li>Operate the software as a monitoring service for third parties in competition with the hosted Uptivora service.</li>
        <li>Remove or circumvent the licence check, or change licence files.</li>
      </ul>
      <p>
        You may adapt the configuration and deploy the software on any infrastructure you
        control. Open-source components included in the software remain under their own licences,
        which take precedence for those components.
      </p>

      <h2>5. Privacy and your data</h2>
      <p>
        The software runs entirely on your infrastructure and never sends data to us — no licence
        activation, no update checks, no telemetry. You are responsible for the personal data you
        process with it, including the email addresses of users and alert recipients.
      </p>

      <h2>6. Transfer</h2>
      <p>
        You may transfer the licence once to another company or person (for example when selling
        a business) if you stop using it and tell us the new licensee; we then issue a licence
        file in the new name.
      </p>

      <h2>7. Support</h2>
      <p>
        The licence includes the documentation. Installation help or support beyond that can be
        agreed separately. Hosting, servers, domains and email delivery are not part of the
        licence.
      </p>

      <h2>8. Warranty and liability</h2>
      <p>
        We warrant that the software essentially works as described in the documentation at the
        time of delivery. If it does not, we will correct the defect or, if we cannot within a
        reasonable time, refund the licence fee. Further warranty is excluded to the extent
        permitted by law. Our liability is governed by section 8 of the{" "}
        <Link href="/terms">terms of service</Link>, which applies accordingly.
      </p>
      <ReviewNote>
        Define the refund policy for licences (e.g. 14 days, no questions asked). Note that a licence
        file cannot be revoked once delivered (verification is offline), so a refund relies on the
        customer stopping use.
      </ReviewNote>

      <h2>9. Termination</h2>
      <p>
        If you seriously breach this agreement and do not remedy the breach within 30 days of
        notice, we may terminate the licence; you must then stop using the software.
      </p>

      <h2>10. Applicable law</h2>
      <p>
        Swiss law applies, excluding the UN Convention on Contracts for the International Sale of
        Goods. Courts at <Op v="jurisdiction" /> have jurisdiction for business customers;
        consumers may also sue and be sued at their place of residence where the law provides so.
      </p>
    </>
  );
}

/* --- Data processing agreement ----------------------------------------------------------- */

export function DpaText() {
  return (
    <>
      <p>
        This agreement applies when a business customer (“controller”) uses the hosted Uptivora
        service and thereby has <Op v="name" /> (“processor”) process personal data on its behalf.
        It forms part of the <Link href="/terms">terms of service</Link> and fulfils FADP Art. 9
        and GDPR Art. 28.
      </p>

      <h2>1. Subject, duration and nature of the processing</h2>
      <ul>
        <li><strong>Purpose:</strong> monitoring the controller’s websites and sending alerts.</li>
        <li><strong>Data subjects:</strong> people the controller adds as alert recipients; people named in incident notes or monitor names.</li>
        <li><strong>Personal data:</strong> email addresses, confirmation and unsubscribe status, delivery status of emails; any personal data the controller enters in free-text fields.</li>
        <li><strong>Duration:</strong> as long as the controller’s account exists; deletion as in section 7.</li>
      </ul>

      <h2>2. Instructions</h2>
      <p>
        The processor processes the data only on documented instructions of the controller, which
        are given by these terms and by the controller’s settings in the service, unless the law
        requires otherwise; in that case the processor informs the controller unless the law
        forbids it.
      </p>

      <h2>3. Confidentiality</h2>
      <p>
        Everyone with access to the data is bound to confidentiality.
      </p>

      <h2>4. Security measures</h2>
      <p>
        The processor takes appropriate technical and organisational measures, in particular:
        TLS encryption of all connections; hashed passwords and tokens; access to production
        systems only for authorised administrators with key-based authentication; isolated
        services with minimal privileges and a database without direct internet access;
        protection against cross-site requests and automated attacks; daily backups,
        test-restored weekly, stored separately; logging of security-relevant events. The
        measures are reviewed regularly and may be improved without notice.
      </p>

      <h2>5. Sub-processors</h2>
      <p>The controller authorises the following sub-processors:</p>
      <ul>
        <li>Hosting: <Op v="hostingProvider" /></li>
        <li>Email delivery: <Op v="emailProvider" /></li>
      </ul>
      <p>
        The processor informs the controller by email at least 30 days before adding or replacing
        a sub-processor; the controller may object for important reasons and, if no solution is
        found, terminate the service. Sub-processors are bound by obligations equivalent to this
        agreement.
      </p>

      <h2>6. Support for the controller</h2>
      <p>
        The processor helps the controller to answer requests from data subjects (export,
        correction and deletion are available in the service), and to meet its obligations on
        security, breach notification and data protection impact assessments, as far as
        reasonable. The processor notifies the controller without undue delay, at the latest
        within 48 hours, after becoming aware of a breach of the security of the controller’s
        personal data.
      </p>

      <h2>7. Deletion</h2>
      <p>
        When the account is deleted, the data is deleted immediately from the live system and
        disappears from backups within 30 days, unless the law requires storage. The controller
        can export its data beforehand.
      </p>

      <h2>8. Audits</h2>
      <p>
        On request the processor provides the information necessary to demonstrate compliance
        with this agreement, in particular a description of the security measures. On-site audits
        are possible with reasonable notice, at the controller’s expense, and without access to
        other customers’ data.
      </p>

      <h2>9. Transfers abroad</h2>
      <p>
        Data is processed in the countries of the sub-processors listed above. Transfers to
        countries without adequate data protection take place only with appropriate safeguards
        (such as the EU Standard Contractual Clauses).
      </p>
      <ReviewNote>
        Fill in the provider countries; if all processing stays in Switzerland/EU, say so
        explicitly. Some customers will ask for a countersigned copy — decide whether to offer one.
      </ReviewNote>
    </>
  );
}
