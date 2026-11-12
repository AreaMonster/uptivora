import pytest
from argon2 import PasswordHasher

from app.core import security
from app.core.security import (
    PasswordPolicyError,
    check_password_policy,
    constant_time_equals,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_hash_and_verify() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert verify_password("correct horse battery", h) == (True, False)
    assert verify_password("wrong password!!", h) == (False, False)


def test_unknown_user_does_not_crash_and_fails() -> None:
    assert verify_password("anything at all", None) == (False, False)


def test_garbage_hash_rejected() -> None:
    assert verify_password("anything at all", "not-a-hash") == (False, False)


def test_weak_parameters_trigger_rehash() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1).hash("pw-1234567890")
    assert verify_password("pw-1234567890", weak) == (True, True)


@pytest.mark.parametrize(
    "password",
    ["short", "a" * 300, "          ", "aaaaaaaaaaaa", "alice-secret-pw"],
)
def test_password_policy_rejects(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        check_password_policy(password, email="alice@example.com")


def test_password_policy_accepts() -> None:
    check_password_policy("Tr0ub4dor&3-horse", email="alice@example.com")


def test_tokens_are_random_and_hashed() -> None:
    a, b = generate_token(), generate_token()
    assert a != b and len(a) >= 43
    assert len(hash_token(a)) == 32 and hash_token(a) == hash_token(a)
    assert constant_time_equals(a, a) and not constant_time_equals(a, b)


def test_max_length_bound() -> None:
    assert security.PASSWORD_MAX_LENGTH == 256
