"""Isolated licence signing service (hosted edition only).

Runs in its own container, reachable only from the API and worker over an internal Docker
network, and is the only process that can read the shop signing key. Even an attacker with full
control of the web application cannot copy the key; they can at most request signatures,
which the service limits and records:

* every request needs the shared token (``UPTIVORA_SIGNER_TOKEN``);
* at most ``signer_daily_limit`` new licences per 24 hours (default 25);
* the same order id always returns the same licence (safe retries, no duplicates);
* a re-issue (key rotation) is only possible for orders it signed before, with the same
  licensee and limits — it cannot create new entitlements;
* every signature is appended to a journal on the signer's own volume.

Commands: ``python -m app.signer serve`` and ``python -m app.signer keygen``.
"""
