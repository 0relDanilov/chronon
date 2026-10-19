import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from chronon import auth

NOW = 1_760_000_000.0


def _keypair() -> tuple[rsa.RSAPrivateKey, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.PKCS1
    )
    return key, public


def _token(
    key: rsa.RSAPrivateKey,
    start: float = NOW - 60,
    end: float = NOW + 3600,
    roles: list[str] | None = None,
    backend: str = "sim-qpu",
) -> str:
    # The payload shape of the client's TokenGenerator (tokens.py:54-65).
    payload: dict[str, Any] = {
        "user_id": "student-01",
        "qpu": {
            backend: {
                "from": start,
                "to": end,
                "access": roles or [],
                "project": ["workshop"],
            }
        },
        "expires": end,
    }
    return jwt.encode(payload, key, algorithm="RS256")


@pytest.fixture
def keys(tmp_path: Path) -> tuple[rsa.RSAPrivateKey, dict[str, list[Any]]]:
    other, other_pub = _keypair()
    key, pub = _keypair()
    # Two keys for the backend: verification must try both (no `kid`).
    (tmp_path / "sim-qpu.old.pem").write_bytes(other_pub)
    (tmp_path / "sim-qpu.workshop.pem").write_bytes(pub)
    assert pub.startswith(b"-----BEGIN RSA PUBLIC KEY-----")  # PKCS#1
    return key, auth.load_keys(str(tmp_path))


def test_valid_token(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    key, loaded = keys
    p = auth.verify(_token(key, roles=["calibrator"]), "sim-qpu", loaded, NOW)
    assert p.user_id == "student-01"
    assert p.roles == frozenset({"calibrator"})
    assert p.projects == ("workshop",)


def test_unknown_signer(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    stranger, _ = _keypair()
    with pytest.raises(auth.AuthError) as e:
        auth.verify(_token(stranger), "sim-qpu", keys[1], NOW)
    assert e.value.status == 401
    assert "2 provider key(s)" in e.value.detail


def test_window_closed(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    key, loaded = keys
    token = _token(key, start=NOW - 3 * 3600, end=NOW - 2 * 3600)
    with pytest.raises(auth.AuthError) as e:
        auth.verify(token, "sim-qpu", loaded, NOW)
    assert e.value.status == 401
    assert "it is now" in e.value.detail
    assert "closed 2 h 0 min ago" in e.value.detail
    assert "→" in e.value.detail  # the window itself is shown


def test_window_not_open(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    key, loaded = keys
    with pytest.raises(auth.AuthError) as e:
        auth.verify(_token(key, start=NOW + 600), "sim-qpu", loaded, NOW)
    assert "opens in 10 min 0 s" in e.value.detail


def test_no_grant_for_backend(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    key, loaded = keys
    loaded = {"arc": loaded["sim-qpu"], **loaded}
    with pytest.raises(auth.AuthError) as e:
        auth.verify(_token(key), "arc", loaded, NOW)
    assert e.value.status == 403
    assert "grants: sim-qpu" in e.value.detail


def test_alg_none_rejected(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    # Deliberately unsigned: the attack the verifier must refuse.
    unsigned = jwt.encode({"user_id": "x"}, key=None, algorithm="none")  # pyright: ignore[reportArgumentType]
    with pytest.raises(auth.AuthError) as e:
        auth.verify(unsigned, "sim-qpu", keys[1], NOW)
    assert e.value.status == 401


def test_malformed(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    with pytest.raises(auth.AuthError) as e:
        auth.verify("not-a-jwt", "sim-qpu", keys[1], NOW)
    assert e.value.status == 401


def test_require_role(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    key, loaded = keys
    p = auth.verify(_token(key), "sim-qpu", loaded, NOW)
    with pytest.raises(auth.AuthError) as e:
        p.require_role("calibrator", "Pushing datasets")
    assert e.value.status == 403
    assert "requires the 'calibrator' role" in e.value.detail


def test_bearer_header() -> None:
    assert auth.bearer("Bearer abc") == "abc"
    with pytest.raises(auth.AuthError):
        auth.bearer(None)
    with pytest.raises(auth.AuthError):
        auth.bearer("Basic abc")


def test_clock_default(
    keys: tuple[rsa.RSAPrivateKey, dict[str, list[Any]]],
) -> None:
    key, loaded = keys
    now = time.time()
    token = _token(key, start=now - 10, end=now + 10)
    assert auth.verify(token, "sim-qpu", loaded).user_id == "student-01"
