"""Point the real iqcc-cloud-client at a chronon site, and only there.

Import this module before constructing ``IQCC_Cloud``. It does three things:

1. Replaces the ``IQCC_Cloud.state`` property. Upstream, it is a property
   whose ``state_service_url`` parameter defaults to the upstream state
   service (vendor/.../computers.py:747-761). A property cannot receive
   arguments, so that default is always used, and the constructor calls it
   three times (computers.py:108, 114, 137). We return a ``StateService``
   bound to ``CHRONON_STATE_URL`` instead.
2. Wraps ``IQCC_Cloud.__init__`` so that it requires an explicit token and a
   non-upstream ``url``. Without a token the client reads
   ``~/.config/iqcc_cloud/config.toml``, whose ``url`` key would override ours
   (computers.py:61-73).
3. Guards ``httpx.Client.send`` and ``httpx.AsyncClient.send``: any request to
   the upstream domain raises before it leaves the process. This is the
   backstop if a code path above is missed.

The upstream domain appears in this file only to block it.
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from iqcc_cloud_client.computers import IQCC_Cloud
from iqcc_cloud_client.state import StateService

FORBIDDEN_DOMAIN = "i-qcc.com"

CHRONON_URL = os.environ.get("CHRONON_URL", "https://api.chronon.test:8443")
CHRONON_STATE_URL = os.environ.get(
    "CHRONON_STATE_URL", "https://state.chronon.test:8443"
)


class ForbiddenHostError(RuntimeError):
    """Raised when something tries to contact the upstream service."""


def is_forbidden(host: str) -> bool:
    """Return True if ``host`` is the upstream domain or one of its subdomains.

    Args:
        host: A hostname, without scheme or port.

    Returns:
        Whether requests to this host must be refused.
    """
    host = host.lower().rstrip(".")
    return host == FORBIDDEN_DOMAIN or host.endswith("." + FORBIDDEN_DOMAIN)


def _check(url: str) -> None:
    host = httpx.URL(url).host
    if is_forbidden(host):
        raise ForbiddenHostError(
            f"Refusing request to {host}: chronon must never contact the "
            f"upstream service. Set CHRONON_URL / CHRONON_STATE_URL to a "
            f"chronon site."
        )


_original_send = httpx.Client.send
_original_async_send = httpx.AsyncClient.send


def _guarded_send(
    self: httpx.Client, request: httpx.Request, **kwargs: Any
) -> httpx.Response:
    _check(str(request.url))
    return _original_send(self, request, **kwargs)


async def _guarded_async_send(
    self: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
) -> httpx.Response:
    _check(str(request.url))
    return await _original_async_send(self, request, **kwargs)


def _state(self: IQCC_Cloud) -> StateService:
    return StateService(
        url=CHRONON_STATE_URL, backend=self.backend, headers=self.headers
    )


def _data(self: IQCC_Cloud) -> StateService:
    raise ForbiddenHostError(
        "The datastore is not part of chronon; .data is disabled."
    )


_original_init = IQCC_Cloud.__init__


def _init(
    self: IQCC_Cloud,
    quantum_computer_backend: str,
    api_token: str | None = None,
    url: str = CHRONON_URL,
    datastore: str | None = None,
) -> None:
    if api_token is None:
        raise ValueError(
            "Pass api_token explicitly; the config-file fallback can "
            "override the URL."
        )
    _check(url)
    if datastore is not None:
        raise ValueError("The datastore is not part of chronon.")
    # Upstream annotates url as AnyUrl but concatenates it as a str
    # (computers.py:44, 379), so a str is what it actually needs.
    _original_init(self, quantum_computer_backend, api_token, cast(Any, url))


httpx.Client.send = _guarded_send  # type: ignore[method-assign]
httpx.AsyncClient.send = _guarded_async_send  # type: ignore[method-assign]
IQCC_Cloud.state = property(_state)  # type: ignore[assignment]
IQCC_Cloud.data = property(_data)  # type: ignore[assignment]
IQCC_Cloud.__init__ = _init  # type: ignore[method-assign]
