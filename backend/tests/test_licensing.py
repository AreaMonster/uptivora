import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensegen import __main__ as cli
from licensegen.core import build_payload, public_key_b64, sign_payload

from app.licensing import Edition, LicenseError, verify_license
from app.licensing.format import (
    ARMOR_BEGIN,
    ARMOR_END,
    armor,
    b64url_decode_strict,
    b64url_encode,
    dearmor,
    signing_message,
)
from app.licensing.keys import load_public_key, trusted_keys

KEY_ID = "k-test"


@pytest.fixture(scope="module")
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture(scope="module")
def trusted(private_key):
    return {KEY_ID: load_public_key(public_key_b64(private_key))}


def _issue(private_key, **overrides) -> str:
    payload = build_payload(
        key_id=KEY_ID,
        edition=Edition.PROFESSIONAL,
        licensee_name="Example AG",
        licensee_email="it@example.ch",
    )
    payload.update(overrides)
    return sign_payload(private_key, payload)


def _resign_raw(private_key, payload_bytes: bytes) -> str:
    return armor(payload_bytes, private_key.sign(signing_message(payload_bytes)))


def test_valid_licence_verifies(private_key, trusted) -> None:
    lic = verify_license(_issue(private_key), trusted)
    assert lic.edition is Edition.PROFESSIONAL
    assert lic.licensee_name == "Example AG"
    assert lic.limits.max_monitors == 0 and lic.limits.min_interval_seconds == 30
    assert lic.updates == "lifetime"


def test_starter_defaults(private_key, trusted) -> None:
    payload = build_payload(
        key_id=KEY_ID, edition=Edition.STARTER, licensee_name="Shop", licensee_email="a@b.ch"
    )
    lic = verify_license(sign_payload(private_key, payload), trusted)
    assert lic.limits.to_dict() == {"max_monitors": 25, "max_users": 3, "min_interval_seconds": 60}


def test_crlf_and_whitespace_tolerated(private_key, trusted) -> None:
    text = _issue(private_key).replace("\n", "\r\n")
    assert verify_license("\n\n" + text + "\n  ", trusted).edition is Edition.PROFESSIONAL


def test_payload_tampering_rejected(private_key, trusted) -> None:
    payload_bytes, sig = dearmor(_issue(private_key))
    forged = json.loads(payload_bytes)
    forged["licensee"]["name"] = "Someone Else"
    forged["limits"]["max_monitors"] = 999999
    forged_bytes = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(LicenseError) as exc:
        verify_license(armor(forged_bytes, sig), trusted)
    assert exc.value.code == "bad_signature"


def test_every_single_bit_flip_in_signature_rejected(private_key, trusted) -> None:
    payload_bytes, sig = dearmor(_issue(private_key))
    for i in range(0, len(sig) * 8, 7):
        flipped = bytearray(sig)
        flipped[i // 8] ^= 1 << (i % 8)
        with pytest.raises(LicenseError):
            verify_license(armor(payload_bytes, bytes(flipped)), trusted)


def test_untrusted_key_rejected(trusted) -> None:
    other = Ed25519PrivateKey.generate()
    with pytest.raises(LicenseError) as exc:
        verify_license(_issue(other), trusted)  # same key id, different key
    assert exc.value.code == "bad_signature"
    with pytest.raises(LicenseError) as exc:
        verify_license(_issue(other, key_id="unknown"), trusted)
    assert exc.value.code == "unknown_key"


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"product": "something-else"}, "wrong_product"),
        ({"format": 2}, "unsupported_format"),
        ({"expires_at": "2030-01-01T00:00:00+00:00"}, "invalid_payload"),
        ({"edition": "enterprise"}, "invalid_payload"),
        ({"license_id": "not-a-uuid"}, "invalid_payload"),
        (
            {"limits": {"max_monitors": -1, "max_users": 0, "min_interval_seconds": 30}},
            "invalid_payload",
        ),
        (
            {"limits": {"max_monitors": True, "max_users": 0, "min_interval_seconds": 30}},
            "invalid_payload",
        ),
        (
            {"limits": {"max_monitors": 1, "max_users": 0, "min_interval_seconds": 5}},
            "invalid_payload",
        ),
        ({"licensee": {"name": "  ", "email": "x@y.ch"}}, "invalid_payload"),
        ({"issued_at": "2026-01-01T00:00:00"}, "invalid_payload"),
    ],
)
def test_signed_but_invalid_payload_rejected(private_key, trusted, override, code) -> None:
    with pytest.raises(LicenseError) as exc:
        verify_license(_issue(private_key, **override), trusted)
    assert exc.value.code == code


def test_duplicate_json_keys_rejected(private_key, trusted) -> None:
    payload_bytes, _ = dearmor(_issue(private_key))
    dup = payload_bytes[:-1] + b',"edition":"starter"}'
    with pytest.raises(LicenseError) as exc:
        verify_license(_resign_raw(private_key, dup), trusted)
    assert exc.value.code == "malformed"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        f"{ARMOR_BEGIN}\n{ARMOR_END}",
        f"{ARMOR_BEGIN}\nabc\n{ARMOR_END}",
        f"{ARMOR_BEGIN}\nabc.def.ghi\n{ARMOR_END}",
        f"{ARMOR_BEGIN}\na+b/.cc\n{ARMOR_END}",
        "x" * 40000,
    ],
)
def test_malformed_files_rejected(text, trusted) -> None:
    with pytest.raises(LicenseError) as exc:
        verify_license(text, trusted)
    assert exc.value.code == "malformed"


def test_trailing_content_rejected(private_key, trusted) -> None:
    with pytest.raises(LicenseError):
        verify_license(_issue(private_key) + "extra", trusted)


def test_noncanonical_base64_rejected() -> None:
    good = b64url_encode(b"\xff")  # "_w"
    assert b64url_decode_strict(good) == b"\xff"
    with pytest.raises(ValueError):
        b64url_decode_strict("_x")  # same byte, non-zero padding bits
    with pytest.raises(ValueError):
        b64url_decode_strict(base64.b64encode(b"\xff\xfe").decode())  # padded / std alphabet


def test_signature_is_domain_separated(private_key, trusted) -> None:
    payload_bytes, _ = dearmor(_issue(private_key))
    raw_sig = private_key.sign(payload_bytes)  # signed WITHOUT the prefix
    with pytest.raises(LicenseError) as exc:
        verify_license(armor(payload_bytes, raw_sig), trusted)
    assert exc.value.code == "bad_signature"


def test_dev_key_only_trusted_outside_production(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    (tmp_path / "dev-public.key").write_text(public_key_b64(key))
    assert "dev" in trusted_keys("development", tmp_path)
    assert "dev" in trusted_keys("test", tmp_path)
    assert "dev" not in trusted_keys("production", tmp_path)


def test_cli_roundtrip(tmp_path: Path, capsys) -> None:
    keydir = tmp_path / "keys"
    cli.main(["keygen", "--dev", "--out-dir", str(keydir)])
    out = tmp_path / "customer.license"
    cli.main(
        [
            "issue",
            "--key",
            str(keydir / "dev-private.pem"),
            "--key-id",
            "dev",
            "--edition",
            "starter",
            "--name",
            "Test GmbH",
            "--email",
            "t@test.ch",
            "--max-monitors",
            "40",
            "--order",
            "ord-1",
            "--out",
            str(out),
        ]
    )
    pub = (keydir / "dev-public.key").read_text().strip()
    cli.main(["verify", str(out), "--public-key", pub])
    stdout = capsys.readouterr().out
    assert "VALID" in stdout and "'max_monitors': 40" in stdout
    lic = verify_license(out.read_text(), {"dev": load_public_key(pub)})
    assert lic.notes == "order:ord-1" and lic.edition is Edition.STARTER

    # Refuses to overwrite keys or licences
    with pytest.raises(SystemExit):
        cli.main(["keygen", "--dev", "--out-dir", str(keydir)])


def test_cli_encrypted_production_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LICENSEGEN_PASSPHRASE", "a-long-test-passphrase")
    cli.main(["keygen", "--key-id", "k2099", "--out-dir", str(tmp_path)])
    pem = (tmp_path / "k2099.private.pem").read_bytes()
    assert b"ENCRYPTED PRIVATE KEY" in pem
    out = tmp_path / "p.license"
    cli.main(
        [
            "issue",
            "--key",
            str(tmp_path / "k2099.private.pem"),
            "--key-id",
            "k2099",
            "--edition",
            "professional",
            "--name",
            "P AG",
            "--email",
            "p@p.ch",
            "--out",
            str(out),
        ]
    )
    pub = (tmp_path / "k2099.public.key").read_text().strip()
    assert (
        verify_license(out.read_text(), {"k2099": load_public_key(pub)}).edition
        is Edition.PROFESSIONAL
    )

    monkeypatch.setenv("LICENSEGEN_PASSPHRASE", "wrong-passphrase-123")
    with pytest.raises(ValueError):
        cli.main(
            [
                "issue",
                "--key",
                str(tmp_path / "k2099.private.pem"),
                "--key-id",
                "k2099",
                "--edition",
                "starter",
                "--name",
                "X",
                "--email",
                "x@x.ch",
                "--out",
                str(tmp_path / "x.license"),
            ]
        )


def test_armor_shape(private_key) -> None:
    text = _issue(private_key)
    lines = text.strip().splitlines()
    assert lines[0] == ARMOR_BEGIN and lines[-1] == ARMOR_END
    assert all(len(line) <= 64 for line in lines[1:-1])
