"""Mint demo tokens with the client's own provider flow (``make tokens``).

The provider key pair was created once with
``HOME=.tokens/provider-home iqcc-cloud provider --backend-name sim-qpu``; its
public half (PKCS#1) is in services/k8s/base/provider-keys/. The private half
stays in .tokens/ (gitignored). Tokens are minted with the client's
``TokenGenerator.time_window`` (vendor/.../tokens.py:34-71), exactly as a
backend provider would.

Writes .tokens/<name>, one token per file:
- student-01..NN: window now → +2 h, project "workshop"
- greedy-01: same window (the rehearsal's eager student)
- calibrator-01: same window, role "calibrator"
- expired-01: window −3 h → −2 h
"""

import argparse
import contextlib
import io
import os
import time
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / ".tokens"
PROVIDER_HOME = Path(os.environ.get("PROVIDER_HOME", TOKENS / "provider-home"))


@contextlib.contextmanager
def _provider_home() -> Iterator[None]:
    # The client reads the provider key from ~/.config/iqcc_cloud/config.toml
    # (cli.py:21-30); point ~ at our gitignored copy for the duration.
    old = os.environ.get("HOME")
    os.environ["HOME"] = str(PROVIDER_HOME)
    try:
        yield
    finally:
        if old is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = old


def mint(
    user: str,
    start: float,
    end: float,
    roles: list[str] | None = None,
    projects: list[str] | None = None,
    backend: str = "sim-qpu",
) -> str:
    """Mint one token with the client's TokenGenerator.

    Args:
        user: The user id.
        start: Window start, Unix seconds.
        end: Window end (and ``expires``), Unix seconds.
        roles: Roles such as ``calibrator``.
        projects: Projects the user may use.
        backend: The backend the token grants.

    Returns:
        The encoded JWT.
    """
    from iqcc_cloud_client.tokens import TokenGenerator

    with _provider_home(), contextlib.redirect_stdout(io.StringIO()):
        gen = TokenGenerator(backend)
        gen._console.quiet = True  # pyright: ignore[reportPrivateUsage]
        return gen.time_window(
            user, start, end, roles=roles or [], projects=projects or []
        )


def main() -> None:
    """Write the demo token set to .tokens/."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=50)
    parser.add_argument("--hours", type=float, default=2.0)
    args = parser.parse_args()

    now = time.time()
    end = now + args.hours * 3600
    plan: dict[str, tuple[float, float, list[str]]] = {
        f"student-{i:02d}": (now, end, []) for i in range(1, args.students + 1)
    }
    plan["greedy-01"] = (now, end, [])
    plan["calibrator-01"] = (now, end, ["calibrator"])
    plan["expired-01"] = (now - 3 * 3600, now - 2 * 3600, [])

    TOKENS.mkdir(exist_ok=True)
    for name, (start, stop, roles) in plan.items():
        token = mint(name, start, stop, roles, ["workshop"])
        path = TOKENS / name
        path.write_text(token)
        path.chmod(0o600)
    print(f"wrote {len(plan)} tokens to {TOKENS} (valid {args.hours:g} h)")


if __name__ == "__main__":
    main()
