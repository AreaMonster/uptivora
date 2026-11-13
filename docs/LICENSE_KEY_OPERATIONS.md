# Licence Signing Key Operations (operator runbook)

A self-hosted licence is a file signed with an Ed25519 **private** key; installations check it
with the matching **public** key compiled into the release (`PRODUCTION_PUBLIC_KEYS` in
`backend/app/licensing/keys.py`). Anyone holding a private key can create valid lifetime
licences, so the keys are kept apart from everything else.

Two keys are used:

| Key | Lives | Used for |
| --- | --- | --- |
| **Shop key** (e.g. `shop1`) | Docker secret mounted **only** into the `signer` container of the hosted stack | Signing every paid order automatically, seconds after payment |
| **Master key** (e.g. `k2026a`) | Offline (encrypted USB / vault), passphrase in a password manager | Special cases: manual sales, replacement licences, emergencies |

Both public keys are in `PRODUCTION_PUBLIC_KEYS`, so installations accept licences from either.

## How automatic signing is protected

The `signer` service (`backend/app/signer/`) is reachable only from the API and worker over an
internal Docker network, needs a shared token, and is the only process that can read the shop
key. Even with full control of the web application an attacker cannot copy the key; they can
only request signatures, which the signer limits and records:

- at most `UPTIVORA_SIGNER_DAILY_LIMIT` (default 25) new licences per 24 hours;
- one licence per order id (retries return the same file);
- re-issues only for orders it signed before, with the same licensee and limits;
- every signature appended to a journal on its own volume (`signer_data`, file `signed.jsonl`).

When the signer is down or the limit is reached, orders stay `paid`, the customer sees
"preparing your licence", and the worker retries every 5 minutes. Admin → Billing & licences
still allows attaching a manually signed file.

## One-time setup (before the first self-hosted release)

**1. Shop key** — on the hosted server, in `deploy/hosted` (after `sh init.sh`):

```bash
docker run --rm --user "$(id -u)" -v "$PWD/secrets:/out" uptivora/api:<version> \
  python -m app.signer keygen --key-id shop1 --out /out/licence_signing_key
```

It prints a line `"shop1": "<public key>",`. The private key stays in
`secrets/licence_signing_key` (mode 600) and is never copied anywhere else.

**2. Master key** — on an offline machine with this repository and the backend venv:

```bash
cd tools/licensegen
python -m licensegen keygen --key-id k2026a --out-dir <encrypted USB or vault folder>
```

Choose a long passphrase and store it in a password manager. Make two offline copies of
`k2026a.private.pem`. Never put it in the project folder, OneDrive or any synced folder.

**3. Release with both public keys** — add both printed lines to `PRODUCTION_PUBLIC_KEYS`,
commit, build the release (`deploy/release/build.sh` refuses to build without production keys).

**4. Enable the signer** — `UPTIVORA_SIGNER_KEY_ID=shop1` in `deploy/hosted/.env`, then
`docker compose up -d`. `docker compose ps signer` should report healthy; with no key it reports
`no_key` and orders wait for manual fulfilment.

Back up `secrets/licence_signing_key` together with the other secrets (encrypted, off-site).
Losing it only means generating a new shop key (see rotation); sold licences stay valid.

## Issuing a licence manually (master key)

```bash
python -m licensegen issue --key /vault/k2026a.private.pem --key-id k2026a \
  --edition professional --name "Example AG" --email it@example.ch \
  --order <order-id> --out Example_AG.uptivora-license
```

Attach the file to the order in Admin → Billing & licences. The server verifies it with the
public keys before accepting it.

## Rotation

1. Generate a new shop key (`--key-id shop2`) as in setup step 1, into a new file.
2. Add its public key to `PRODUCTION_PUBLIC_KEYS` (keep `shop1`), release, deploy.
3. Point the signer at the new key (`secrets/licence_signing_key`,
   `UPTIVORA_SIGNER_KEY_ID=shop2`), `docker compose up -d signer`.

Old licences keep working because `shop1` stays trusted.

## Compromise

**Shop key** (the signer container or the host was breached):

1. Rotate as above, but the release **removes** `shop1` from `PRODUCTION_PUBLIC_KEYS`.
2. `docker compose run --rm api python -m app.cli reissue-licences --from-key-id shop1` —
   re-signs every licence the signer issued with `shop1` and emails customers the new file.
3. Licences that were signed manually with the master key are not affected.

**Master key**: generate a new master key, ship a release that removes the old public key,
and re-sign the affected manually issued licences offline (orders list in Admin → Billing &
licences). Installations that never upgrade keep accepting forged licences — the accepted
trade-off of offline verification without phoning home.

## Development key

`python -m licensegen keygen --dev` writes an unencrypted key to `backend/.dev-keys/`
(git-ignored). It is trusted only when `UPTIVORA_ENV` is `development` or `test`, and those
modes refuse to start with a non-local `UPTIVORA_PUBLIC_URL`.
