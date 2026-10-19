"""Contract tests: the real iqcc-cloud-client against a running chronon site.

client_patch is imported before anything touches the client: it rebinds the
state URL, requires explicit tokens, and blocks the upstream domain.
"""

import client_patch  # noqa: F401, I001 - must come first

import time
from collections.abc import Callable

import httpx
import pytest
from iqcc_cloud_client.computers import IQCC_Cloud
from mint_tokens import mint

BACKEND = "sim-qpu"
API = client_patch.CHRONON_URL
STATE = client_patch.CHRONON_STATE_URL


@pytest.fixture(scope="session")
def tokens() -> dict[str, str]:
    now = time.time()
    return {
        "student": mint("contract-student", now - 60, now + 3600),
        "calibrator": mint(
            "contract-calibrator", now - 60, now + 3600, ["calibrator"]
        ),
        "expired": mint("contract-expired", now - 3 * 3600, now - 2 * 3600),
    }


@pytest.fixture(scope="session")
def connect(tokens: dict[str, str]) -> Callable[[str], IQCC_Cloud]:
    def _connect(who: str) -> IQCC_Cloud:
        # The client annotates url as AnyUrl but uses it as a str.
        return IQCC_Cloud(BACKEND, api_token=tokens[who], url=API)  # pyright: ignore[reportArgumentType]

    return _connect


@pytest.fixture(scope="session")
def raw(tokens: dict[str, str]) -> Callable[[str], httpx.Client]:
    """An h2-only httpx client with a token, like the real client's."""

    def _raw(who: str) -> httpx.Client:
        return httpx.Client(
            http2=True,
            http1=False,
            headers={"Authorization": f"Bearer {tokens[who]}"},
            timeout=30,
        )

    return _raw
