"""The client patch must keep the real client away from the upstream service.

Every request here goes through httpx.MockTransport, so even a broken guard
cannot reach the network.
"""

import client_patch
import httpx
import pytest
from iqcc_cloud_client.computers import IQCC_Cloud

UPSTREAM = f"https://state.{client_patch.FORBIDDEN_DOMAIN}/x/state/"


def _mock_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    )


@pytest.mark.parametrize(
    ("host", "forbidden"),
    [
        (client_patch.FORBIDDEN_DOMAIN, True),
        (f"state.{client_patch.FORBIDDEN_DOMAIN}", True),
        (f"STATE.{client_patch.FORBIDDEN_DOMAIN}.", True),
        (f"not{client_patch.FORBIDDEN_DOMAIN}", False),
        ("state.chronon.test", False),
    ],
)
def test_is_forbidden(host: str, forbidden: bool) -> None:
    assert client_patch.is_forbidden(host) is forbidden


def test_guard_blocks_upstream_requests() -> None:
    with pytest.raises(client_patch.ForbiddenHostError):
        _mock_client().get(UPSTREAM)


def test_guard_allows_chronon_requests() -> None:
    r = _mock_client().get("https://state.chronon.test:8443/x/state/")
    assert r.status_code == 200


def test_state_property_points_at_chronon() -> None:
    qc = object.__new__(IQCC_Cloud)
    qc.backend = "sim-qpu"
    qc.headers = {}
    assert qc.state.url == client_patch.CHRONON_STATE_URL


def test_constructor_requires_explicit_token() -> None:
    with pytest.raises(ValueError, match="api_token"):
        IQCC_Cloud("sim-qpu")


def test_constructor_refuses_upstream_url() -> None:
    with pytest.raises(client_patch.ForbiddenHostError):
        IQCC_Cloud(
            "sim-qpu",
            api_token="t",
            url=f"https://cloud.{client_patch.FORBIDDEN_DOMAIN}",
        )
