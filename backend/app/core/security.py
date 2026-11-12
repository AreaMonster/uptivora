"""Security primitives: password hashing, opaque tokens, constant-time comparison."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# RFC 9106 "second recommended option": Argon2id, t=3, m=64 MiB, p=4.
_hasher = PasswordHasher(
    time_cost=3, memory_cost=64 * 1024, parallelism=4, hash_len=32, salt_len=16
)

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 256  # bounds hashing cost for hostile input

# A dummy hash so that login with an unknown email costs the same as a wrong password
# (prevents user enumeration by timing).
_DUMMY_HASH = _hasher.hash("uptivora-timing-equaliser")


class PasswordPolicyError(ValueError):
    pass


def check_password_policy(password: str, *, email: str | None = None) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters")
    if not password.strip():
        raise PasswordPolicyError("Password must not be blank")
    if len(set(password)) < 4:
        raise PasswordPolicyError("Password is too repetitive")
    local_part = email.split("@", 1)[0].lower() if email else ""
    if len(local_part) >= 4 and local_part in password.lower():
        raise PasswordPolicyError("Password must not contain your email name")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> tuple[bool, bool]:
    """Return ``(valid, needs_rehash)``. Always does the full hashing work."""
    if len(password) > PASSWORD_MAX_LENGTH:
        password = password[:PASSWORD_MAX_LENGTH]
    if not password_hash:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass
        return False, False
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return True, _hasher.check_needs_rehash(password_hash)


def generate_token(nbytes: int = 32) -> str:
    """URL-safe random token (256 bits by default) for sessions, CSRF, email links."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> bytes:
    """Tokens are stored hashed so a database leak does not leak live sessions."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def constant_time_equals(a: str | bytes, b: str | bytes) -> bool:
    if isinstance(a, str):
        a = a.encode("utf-8")
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hmac.compare_digest(a, b)
