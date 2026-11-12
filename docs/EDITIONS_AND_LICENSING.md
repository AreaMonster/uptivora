# Editions and Licensing

## 1. The two editions

Both editions are built from the **same source tree and the same Docker images**. The
edition is selected at deploy time with `UPTIVORA_EDITION`.

| | Hosted Uptivora (`hosted`) | Self-hosted Uptivora (`selfhosted`) |
|---|---|---|
| Who runs it | Us, on our VPS | The customer, on their server |
| Who pays how | Monthly subscription (Starter / Pro / Business) | One-time lifetime licence (Starter / Professional) |
| Limits come from | The customer's **subscription plan** (`plans` table, editable in admin) | The installed **licence file** (signed `limits`) |
| Registration | Public sign-up | First-run setup creates the owner admin; further users invited by the admin (or open sign-up if the admin enables it) |
| Billing module | Enabled (TEST MODE until a real provider is configured) | Disabled entirely (no pricing pages, no payment tables used) |
| Licence storefront | Sells self-hosted licences; admin uploads the signed file for the customer to download | Not present |
| Admin dashboard | Our operators: customers, plans, subscriptions, system health | The customer's admin: users, monitors, system health, licence status |
| Network dependencies | SMTP | SMTP (customer's own). **Nothing else.** No calls to any Uptivora server, ever. |
| Telemetry | None | None |

The monitoring engine, notification system, incident logic and dashboards are identical.
Edition-specific behaviour sits behind two small interfaces:

* `LimitsProvider.for_user(user) -> Limits(max_monitors, min_interval_seconds, max_users, ...)`
  * hosted: from active subscription → plan
  * self-hosted: from the verified licence (or the unlicensed defaults)
* `FeatureFlags` — `billing`, `public_signup`, `licence_storefront`, `licence_install`.

Hosted and self-hosted deployments are isolated: separate servers, separate databases,
separate `SECRET_KEY`s. The self-hosted bundle contains only public keys.

## 2. What a lifetime licence includes (customer-facing wording)

**Included, forever, for a one-time payment:**

* A perpetual, non-expiring licence to install and run Uptivora Self-Hosted on servers you
  control, for the edition and limits printed in your licence file.
* The complete application: web dashboard, admin dashboard, API, monitoring workers,
  database migrations, Docker Compose files, configuration examples and documentation.
* All product updates (new versions) released for the self-hosted edition, for the lifetime
  of the product. Updates are downloaded by you; nothing updates itself.
* The software keeps working without an internet connection, without renewals and without
  contacting Uptivora. If Uptivora the company ceased to exist, your installation would keep
  running exactly as before.

**Not included (separate from the software licence):**

* **Hosting.** You provide the server, domain, TLS, backups and SMTP server. (Running costs are
  yours; the software itself never costs more.)
* **Support / SLA.** Self-service documentation is included. Priority support, installation
  service or an SLA can be sold separately as optional, time-limited services.
* **Hosted monitoring.** A self-hosted licence does not include an account on hosted Uptivora.

**Licence terms summary** (final wording requires legal review — see roadmap Phase 10):
non-exclusive, non-transferable without consent, perpetual; may be used by the licensee and
its employees; may not be resold or offered as a competing hosted service to third parties.

### Initial self-hosted products (prices editable in admin; TEST prices)

| Product | Price | Licence `limits` |
|---|---|---|
| Starter Self-Hosted | CHF 99 one-time | `max_monitors: 25`, `max_users: 3`, `min_interval_seconds: 60` |
| Professional Self-Hosted | CHF 199 one-time | `max_monitors: 0` (unlimited), `max_users: 0` (unlimited), `min_interval_seconds: 30` |
| *(no licence installed)* | free evaluation | `max_monitors: 3`, `max_users: 1`, `min_interval_seconds: 300`, banner "Unlicensed" |

## 3. Licence system design

### 3.1 Cryptography

* Algorithm: **Ed25519** (RFC 8032) via the `cryptography` library.
* The application ships a table of **trusted public keys** keyed by `key_id`
  (`backend/app/licensing/keys.py`). Rotation = add a new key id, keep the old one so
  existing licences remain valid forever.
* A **development key** (`key_id = "dev"`) is generated locally per developer machine and is
  trusted **only** when `UPTIVORA_ENV=development`. A dev-signed licence is rejected in
  production.
* The **private key never enters the repository, the Docker images, the database or the web
  UI.** It lives on an offline machine as an encrypted PKCS#8 PEM (passphrase-protected),
  used only by `tools/licensegen`.

### 3.2 File format

```
-----BEGIN UPTIVORA LICENSE-----
eyJ2IjoxLCJsaWNlbnNlX2lkIjoi...   (base64url payload, wrapped at 64 cols)
.
MEUCIQDf...                       (base64url Ed25519 signature)
-----END UPTIVORA LICENSE-----
```

Precisely: the armour body (whitespace removed) is `B64URL(payload_bytes) "." B64URL(signature)`
where `signature = Ed25519_sign(private_key, b"uptivora-license-v1\x00" + payload_bytes)`.

* The signature is over the **exact payload bytes**, so there is no JSON canonicalisation
  ambiguity. The verifier decodes the bytes, verifies, and only then parses JSON.
* The domain-separation prefix `uptivora-license-v1\0` means a signature over a licence can
  never be confused with any other signed object.
* Payload JSON (UTF-8):

```json
{
  "format": 1,
  "key_id": "k2026a",
  "license_id": "6f0c2d8e-0d41-4d55-9a0e-6b7f0b0c1a2b",
  "product": "uptivora-selfhosted",
  "edition": "professional",
  "licensee": { "name": "Example AG", "email": "it@example.ch" },
  "issued_at": "2026-11-12T10:00:00Z",
  "expires_at": null,
  "updates": "lifetime",
  "limits": { "max_monitors": 0, "max_users": 0, "min_interval_seconds": 30 },
  "notes": ""
}
```

### 3.3 Verification rules (all must pass, otherwise the licence is rejected)

1. Armour present, body decodes as strict base64url, sizes sane (payload ≤ 8 KiB, signature = 64 bytes).
2. Payload parses as a JSON object; `format == 1`; `product == "uptivora-selfhosted"`.
3. `key_id` is in the trusted key set for the current environment (`dev` only in development).
4. Ed25519 signature verifies against that key over `prefix + payload_bytes`.
5. `edition` ∈ {`starter`, `professional`}; limits are non-negative integers; `expires_at` is `null`
   (non-expiring by design — field exists only so a future time-boxed trial format is possible).
6. `license_id` is a valid UUID.

Any byte change (payload, signature, armour content) fails step 1, 2 or 4.

### 3.4 What the licence deliberately does **not** do

* No hardware fingerprinting, no MAC/CPU binding, no domain binding.
* No online activation, no revocation check, no "call home".
* No expiry, no grace periods, no kill switch. If the licence file is removed the software
  falls back to the unlicensed evaluation limits — **data is never deleted** and existing
  monitors over the limit are paused, not removed.

### 3.5 Fulfilment flow for a sold licence (hosted side)

1. Customer buys "Professional Self-Hosted" on hosted Uptivora → `license_orders` row
   (`status = paid`, TEST MODE until real billing).
2. Operator, on the offline machine: `python -m licensegen issue --edition professional --name "Example AG" --email it@example.ch --order <order-id>`
   → writes `Example_AG.uptivora-license`.
3. Operator uploads the file in **Admin → Licences → Order → Attach licence**. The server
   verifies it with the public key before accepting it (catches mistakes).
4. Customer downloads the licence file and the release bundle from their account page.
5. Customer installs: copies the file into the deployment (`./license/uptivora.license`) or
   uploads it in their own admin dashboard → verified locally.

Automating step 2 (an isolated signing service) is possible later but intentionally not done:
keeping the key off any internet-facing machine is worth a few minutes of manual work per sale.
