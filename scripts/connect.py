"""``connect(backend)``: the real client, pointed at chronon, in one call.

Used by the notebook and the rehearsal. Importing this module imports
client_patch first, so a caller can't forget it (see docs/components/
client-patch.md, "Not imported, or imported too late").
"""

import client_patch  # noqa: F401, I001 - must come before the client

import os
from pathlib import Path

from iqcc_cloud_client.computers import IQCC_Cloud

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("SSL_CERT_FILE", str(ROOT / ".certs" / "ca.pem"))


def connect(backend: str = "sim-qpu", token: str = "student-01") -> IQCC_Cloud:
    """Construct the unmodified client for a chronon backend.

    Args:
        backend: The backend name.
        token: A token name in .tokens/ (see ``make tokens``).

    Returns:
        A connected client; its constructor has already read the summary.
    """
    api_token = (ROOT / ".tokens" / token).read_text().strip()
    return IQCC_Cloud(
        backend,
        api_token=api_token,
        url=client_patch.CHRONON_URL,  # pyright: ignore[reportArgumentType]
    )
