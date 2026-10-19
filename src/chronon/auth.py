"""RS256 provider-token verification: signature, time window, roles, projects.

Tokens are minted by a backend provider with the client's ``TokenGenerator``
(vendor/.../tokens.py:54-67). They carry ``user_id``, a ``qpu`` map of
per-backend grants (``from``, ``to``, ``access`` roles, ``project`` list) and
``expires``. They don't carry ``exp``, ``iat``, ``kid`` or ``jti``, so:

- ``expires`` and the window are checked here, by hand;
- with no ``kid``, every key registered for the backend is tried;
- with no ``jti``, a single token can't be revoked (see ADR-0012).
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key


class AuthError(Exception):
    """A token was rejected. ``status`` is 401 or 403; ``detail`` says why."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Principal:
    """Who is calling, and what their token grants on one backend."""

    user_id: str
    backend: str
    roles: frozenset[str]
    projects: tuple[str, ...]
    window_from: float
    window_to: float

    def require_role(self, role: str, action: str) -> None:
        """Raise 403 unless the token carries ``role``.

        Args:
            role: The role required, e.g. ``calibrator``.
            action: What the caller tried, for the error message.

        Raises:
            AuthError: If the role is missing.
        """
        if role not in self.roles:
            have = ", ".join(sorted(self.roles)) or "none"
            raise AuthError(
                403,
                f"{action} on backend {self.backend} requires the '{role}' "
                f"role; your token's roles: {have}. Ask the backend provider "
                f"for a token with '{role}'.",
            )


def load_keys(directory: str) -> dict[str, list[Any]]:
    """Load provider public keys, grouped by backend.

    Files are named ``<backend>.<key-name>.pem`` and hold one PEM public key,
    PKCS#1 (what ``iqcc-cloud provider`` prints) or SubjectPublicKeyInfo.

    Args:
        directory: Where the key files are mounted.

    Returns:
        A map from backend name to its loaded public keys.
    """
    keys: dict[str, list[Any]] = {}
    root = Path(directory)
    if not root.is_dir():
        return keys
    for path in sorted(root.glob("*.pem")):
        backend = path.name.split(".", 1)[0]
        keys.setdefault(backend, []).append(
            load_pem_public_key(path.read_bytes())
        )
    return keys


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _ago(seconds: float) -> str:
    seconds = int(abs(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m} min" if h else f"{m} min {s} s"


def _window_detail(backend: str, start: float, end: float, now: float) -> str:
    window = f"{_utc(start)} → {_utc(end)}"
    if now < start:
        when = f"it opens in {_ago(start - now)}"
    else:
        when = f"it closed {_ago(now - end)} ago"
    return (
        f"Your access window for backend {backend} is {window}; it is now "
        f"{_utc(now)}, so {when}. Ask the backend provider for a token "
        f"covering the current time."
    )


def verify(
    token: str,
    backend: str,
    keys: Mapping[str, list[Any]],
    now: float | None = None,
) -> Principal:
    """Verify a bearer token for one backend.

    Order: signature (any registered key for the backend), required claims,
    the backend grant, ``expires``, the ``from``/``to`` window.

    Args:
        token: The raw JWT.
        backend: The backend being called.
        keys: Public keys per backend, from ``load_keys``.
        now: Current time in Unix seconds; defaults to the clock.

    Returns:
        The verified principal.

    Raises:
        AuthError: 401 for a bad signature, malformed token or time window;
            403 if the token grants nothing on this backend.
    """
    now = time.time() if now is None else now
    candidates = keys.get(backend, [])
    if not candidates:
        raise AuthError(
            401, f"Backend {backend} has no provider keys registered."
        )
    claims: dict[str, Any] | None = None
    for key in candidates:
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                # The tokens use `expires`, not `exp`; checked below.
                options={"verify_exp": False, "verify_aud": False},
            )
            break
        except jwt.InvalidSignatureError:
            continue
        except jwt.DecodeError as e:
            raise AuthError(401, f"The bearer token is malformed: {e}.") from e
        except jwt.InvalidTokenError as e:
            # e.g. an unsigned (alg "none") or HS256 token: never a 500.
            raise AuthError(401, f"The bearer token was rejected: {e}.") from e
    if claims is None:
        raise AuthError(
            401,
            f"The token's signature doesn't match any of the "
            f"{len(candidates)} provider key(s) registered for backend "
            f"{backend}. Was it minted for another backend or provider?",
        )

    qpu = claims.get("qpu")
    user_id = claims.get("user_id")
    if not isinstance(qpu, dict) or not isinstance(user_id, str):
        raise AuthError(401, "The token lacks the 'user_id' or 'qpu' claim.")
    grants = cast(dict[str, Any], qpu)
    grant = grants.get(backend)
    if not isinstance(grant, dict):
        granted = ", ".join(sorted(grants)) or "none"
        raise AuthError(
            403,
            f"Your token grants no access to backend {backend}; it grants: "
            f"{granted}.",
        )
    g = cast(dict[str, Any], grant)
    try:
        start = float(g["from"])
        end = float(g["to"])
        expires = float(claims["expires"])
    except (KeyError, TypeError, ValueError) as e:
        raise AuthError(
            401, "The token's 'from', 'to' or 'expires' is missing or invalid."
        ) from e
    if now >= expires or not start <= now <= end:
        raise AuthError(
            401, _window_detail(backend, start, min(end, expires), now)
        )

    roles = cast(list[Any], g.get("access") or [])
    projects = cast(list[Any], g.get("project") or [])
    return Principal(
        user_id=user_id,
        backend=backend,
        roles=frozenset(str(r) for r in roles),
        projects=tuple(str(p) for p in projects),
        window_from=start,
        window_to=end,
    )


def bearer(authorization: str | None) -> str:
    """Extract the token from an ``Authorization`` header.

    Args:
        authorization: The header value, if any.

    Returns:
        The token.

    Raises:
        AuthError: 401 if the header is missing or not a bearer token.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError(
            401,
            "Missing 'Authorization: Bearer <token>' header. Pass api_token "
            "to the client.",
        )
    return authorization[7:].strip()
