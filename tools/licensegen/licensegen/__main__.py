"""Uptivora offline licence generator.

Usage (run on an offline/trusted machine, from tools/licensegen):

  python -m licensegen keygen --key-id k2026a --out-dir /secure/keys
  python -m licensegen keygen --dev                      # local development key, unencrypted
  python -m licensegen issue --key /secure/keys/k2026a.private.pem --key-id k2026a \
      --edition professional --name "Example AG" --email it@example.ch --out example.license
  python -m licensegen verify example.license [--public-key <b64>]
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from licensegen.core import (
    EDITION_DEFAULT_LIMITS,
    Edition,
    LicenseLimits,
    build_payload,
    generate_keypair,
    load_private_key,
    private_key_to_pem,
    public_key_b64,
    sign_payload,
)

DEV_KEY_DIR = Path(__file__).resolve().parents[3] / "backend" / ".dev-keys"
PASSPHRASE_ENV = "LICENSEGEN_PASSPHRASE"  # noqa: S105 - env var name


def _write_private(path: Path, data: bytes) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing key file {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _passphrase(confirm: bool) -> bytes:
    value = os.environ.get(PASSPHRASE_ENV)
    if value is None:
        value = getpass.getpass("Key passphrase: ")
        if confirm and getpass.getpass("Repeat passphrase: ") != value:
            raise SystemExit("Passphrases do not match")
    if confirm and len(value) < 12:
        raise SystemExit("Use a passphrase of at least 12 characters")
    return value.encode("utf-8")


def cmd_keygen(args: argparse.Namespace) -> None:
    key = generate_keypair()
    pub = public_key_b64(key)
    if args.dev:
        out = Path(args.out_dir) if args.out_dir else DEV_KEY_DIR
        _write_private(out / "dev-private.pem", private_key_to_pem(key, None))
        (out / "dev-public.key").write_text(pub + "\n", encoding="ascii")
        print(f"Development key written to {out}")
        print("It is trusted ONLY when UPTIVORA_ENV=development or test.")
        return
    if not args.key_id or args.key_id == "dev":
        raise SystemExit("--key-id is required (and 'dev' is reserved)")
    out = Path(args.out_dir)
    _write_private(out / f"{args.key_id}.private.pem", private_key_to_pem(key, _passphrase(True)))
    (out / f"{args.key_id}.public.key").write_text(pub + "\n", encoding="ascii")
    print(f"Private key: {out / (args.key_id + '.private.pem')}  (encrypted, keep OFFLINE)")
    print("Add this line to PRODUCTION_PUBLIC_KEYS in backend/app/licensing/keys.py:")
    print(f'    "{args.key_id}": "{pub}",')


def cmd_issue(args: argparse.Namespace) -> None:
    edition = Edition(args.edition)
    pem = Path(args.key).read_bytes()
    is_dev = args.key_id == "dev"
    private_key = load_private_key(pem, None if is_dev else _passphrase(False))
    defaults = EDITION_DEFAULT_LIMITS[edition]
    limits = LicenseLimits(
        max_monitors=defaults.max_monitors if args.max_monitors is None else args.max_monitors,
        max_users=defaults.max_users if args.max_users is None else args.max_users,
        min_interval_seconds=args.min_interval or defaults.min_interval_seconds,
    )
    notes = args.notes or (f"order:{args.order}" if args.order else "")
    payload = build_payload(
        key_id=args.key_id,
        edition=edition,
        licensee_name=args.name,
        licensee_email=args.email,
        limits=limits,
        notes=notes,
    )
    text = sign_payload(private_key, payload)

    # Self-check with the matching public key before handing the file out.
    from app.licensing.keys import load_public_key
    from app.licensing.verify import verify_license

    lic = verify_license(text, {args.key_id: load_public_key(public_key_b64(private_key))})
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"Refusing to overwrite {out}")
    out.write_text(text, encoding="ascii")
    print(f"Issued licence {lic.license_id} ({lic.edition}) for {lic.licensee_name} -> {out}")


def cmd_verify(args: argparse.Namespace) -> None:
    from app.licensing.keys import PRODUCTION_PUBLIC_KEYS, load_public_key
    from app.licensing.verify import LicenseError, verify_license

    text = Path(args.file).read_text(encoding="utf-8")
    if args.public_key:
        import json

        from app.licensing.format import dearmor

        key_id = json.loads(dearmor(text)[0])["key_id"]
        keys = {key_id: load_public_key(args.public_key)}
    else:
        keys = {k: load_public_key(v) for k, v in PRODUCTION_PUBLIC_KEYS.items()}
        dev_pub = DEV_KEY_DIR / "dev-public.key"
        if dev_pub.exists():
            keys["dev"] = load_public_key(dev_pub.read_text(encoding="ascii"))
    try:
        lic = verify_license(text, keys)
    except LicenseError as exc:
        print(f"INVALID ({exc.code}): {exc.message}")
        raise SystemExit(1) from exc
    print("VALID")
    print(f"  licence id : {lic.license_id}")
    print(f"  edition    : {lic.edition}")
    print(f"  licensee   : {lic.licensee_name} <{lic.licensee_email}>")
    print(f"  issued at  : {lic.issued_at.isoformat()}")
    print(f"  signing key: {lic.key_id}")
    print(f"  limits     : {lic.limits.to_dict()}  (0 = unlimited)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="licensegen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="generate an Ed25519 signing key pair")
    p.add_argument("--key-id")
    p.add_argument("--out-dir")
    p.add_argument("--dev", action="store_true", help="unencrypted local development key")
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("issue", help="sign a licence file")
    p.add_argument("--key", required=True, help="private key PEM")
    p.add_argument("--key-id", required=True)
    p.add_argument("--edition", required=True, choices=[e.value for e in Edition])
    p.add_argument("--name", required=True, help="licensee name")
    p.add_argument("--email", required=True)
    p.add_argument("--max-monitors", type=int)
    p.add_argument("--max-users", type=int)
    p.add_argument("--min-interval", type=int)
    p.add_argument("--order", help="order id, stored in notes")
    p.add_argument("--notes")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_issue)

    p = sub.add_parser("verify", help="verify a licence file")
    p.add_argument("file")
    p.add_argument("--public-key", help="base64url public key (default: embedded keys)")
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
