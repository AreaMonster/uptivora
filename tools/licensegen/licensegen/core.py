"""Licence signing for the OFFLINE CLI. The implementation lives in the application
(``app.licensing.signing``) so the CLI, the signer service and verification never drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.licensing.format import EDITION_DEFAULT_LIMITS, Edition, LicenseLimits  # noqa: E402, F401
from app.licensing.signing import (  # noqa: E402, F401
    build_payload,
    generate_keypair,
    load_private_key,
    private_key_to_pem,
    public_key_b64,
    sign_payload,
)
