# Licence Signing Key Operations (operator runbook)

The Ed25519 **private** signing key is the most sensitive secret of the business: anyone
holding it can create valid lifetime licences. It must never be on the web server.

## One-time key ceremony (before the first self-hosted release)

1. Use an offline machine (or at least a machine with no deployment credentials), with this
   repository checked out and the backend venv installed.
2. `cd tools/licensegen`
3. `python -m licensegen keygen --key-id k2026a --out-dir <encrypted USB or vault folder>`
   — choose a long passphrase; store it in a password manager.
4. Paste the printed line into `PRODUCTION_PUBLIC_KEYS` in `backend/app/licensing/keys.py`
   and commit it (public keys are not secret).
5. Make **two** offline backups of `k2026a.private.pem` (it is passphrase-encrypted PKCS#8).
   Losing it means you cannot issue new licences with that key id (old ones stay valid; you
   would rotate to a new key id).

## Issuing a licence for an order

```bash
python -m licensegen issue --key /vault/k2026a.private.pem --key-id k2026a \
  --edition professional --name "Example AG" --email it@example.ch \
  --order <order-id> --out Example_AG.uptivora-license
```

Then attach the file to the order in Admin → Licences. The server verifies it with the public
key before accepting it.

## Rotation

Add a new key id, publish a release containing both public keys, switch issuance to the new
key. Never delete an old public key unless it is compromised.

## Compromise

1. Generate a new key, ship a release that **removes** the compromised public key and adds
   the new one.
2. Re-issue licences for all legitimate customers (from `license_orders`) with the new key and
   email them. Because verification is offline, installations that do not upgrade keep
   accepting forged licences — this is the accepted trade-off of a no-phone-home design.

## Development key

`python -m licensegen keygen --dev` writes an unencrypted key to `backend/.dev-keys/`
(git-ignored). It is trusted only when `UPTIVORA_ENV` is `development` or `test`, and those
modes refuse to start with a non-local `UPTIVORA_PUBLIC_URL`.
