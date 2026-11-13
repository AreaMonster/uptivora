"""``python -m app.signer serve`` — run the signing service (port 8100).
``python -m app.signer keygen --key-id shop1 --out /out/licence_signing_key`` — create the
shop key once; prints the public-key line for ``PRODUCTION_PUBLIC_KEYS``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from app.licensing.keys import DEV_KEY_ID
from app.licensing.signing import generate_keypair, private_key_to_pem, public_key_b64


def keygen(key_id: str, out: Path) -> None:
    if not key_id or key_id == DEV_KEY_ID:
        raise SystemExit("--key-id is required ('dev' is reserved)")
    if out.exists() and out.stat().st_size > 0:
        raise SystemExit(f"Refusing to overwrite existing key {out}")
    key = generate_keypair()
    # Unencrypted: the signer starts unattended. The file is protected by being a Docker
    # secret readable only inside the signer container (and by the host's file permissions).
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(private_key_to_pem(key, None))
    print(f"Shop signing key written to {out}")
    print("Add this line to PRODUCTION_PUBLIC_KEYS in backend/app/licensing/keys.py:")
    print(f'    "{key_id}": "{public_key_b64(key)}",')
    print(f"and set UPTIVORA_SIGNER_KEY_ID={key_id} in the hosted .env")


def serve() -> None:
    import uvicorn

    from app.core.config import get_settings
    from app.signer.service import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    path = settings.signer_key_path
    if not path.is_file() or path.stat().st_size == 0:
        # Not set up yet: stay up (no restart loop) and report it on /health.
        logging.getLogger("uptivora.signer").warning(
            "No signing key at %s: automatic licence fulfilment is off. "
            "See docs/LICENSE_KEY_OPERATIONS.md",
            path,
        )
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @app.get("/health")
        def health() -> JSONResponse:
            return JSONResponse({"status": "no_key"}, status_code=503)
    else:
        app = create_app(settings)
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 — container port, reachable only on the internal network
        port=8100,
        proxy_headers=False,
        server_header=False,
        access_log=False,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.signer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    k = sub.add_parser("keygen")
    k.add_argument("--key-id", required=True)
    k.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "keygen":
        keygen(args.key_id, args.out)
    else:
        serve()


if __name__ == "__main__":
    sys.exit(main())
