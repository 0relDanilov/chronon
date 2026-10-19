"""Pod-per-run (Argo Workflows) vs the warm worker, for the same T1 run.

``uv run --extra dev python scripts/rehearsal/overhead.py --runs 10``

Both paths run the same device code (reconfigure 0.5 s → T1 ≈ 2.1 s →
reset 0.2 s). Runs are sequential, on an idle device.

- submit: the laptop clock just before the request (HTTP POST, or `argo
  submit`).
- start: when the device code begins. Warm: the task's ``started_at``.
  Pod: the container's first log line, ``CHRONON_START <epoch>``, printed
  before any import, so image start and Python imports count as overhead.
- total: when the device code finishes. Warm: ``finished_at``. Pod: the
  ``finished_at`` the container prints. `argo submit` → `argo wait` wall time
  (including Argo's own bookkeeping) is reported too.

Container and server times come from the Docker VM's clock; the measured
laptop↔VM skew is printed with the results.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import httpx  # noqa: E402
from mint_tokens import mint  # noqa: E402
from run import API, BACKEND, pct, stamps, valkey_port_forward, wait_idle  # noqa: E402

ROOT = HERE.parent.parent
os.environ.setdefault("SSL_CERT_FILE", str(ROOT / ".certs" / "ca.pem"))
NS = "chronon"


def clock_skew() -> float:
    """Docker VM clock minus laptop clock, in seconds (midpoint estimate).

    Returns:
        The skew; positive means the VM is ahead.
    """
    before = time.time()
    out = subprocess.run(
        ["docker", "exec", "chronon-control-plane", "date", "+%s.%N"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    after = time.time()
    return float(out.strip()) - (before + after) / 2


def warm(runs: int, token: str) -> list[dict[str, float]]:
    """Time ``runs`` T1 runs through the API and the warm worker.

    Args:
        runs: How many.
        token: A student token.

    Returns:
        Per-run ``submit_to_start`` and ``total`` seconds.
    """
    out: list[dict[str, float]] = []
    headers = {"Authorization": f"Bearer {token}"}
    with (
        valkey_port_forward() as v,
        httpx.Client(http2=True, http1=False, headers=headers) as c,
    ):
        for _ in range(runs):
            wait_idle(v)
            t = time.time()
            task = c.post(f"{API}/task/{BACKEND}/t1", json={"qubit": 0})
            task_id = task.json()["task_id"]
            while True:
                s = c.get(f"{API}/task/{BACKEND}/{task_id}").json()
                if s["task_status"] in ("SUCCESS", "FAILURE"):
                    break
                time.sleep(0.2)
            st = stamps(v, task_id)
            out.append(
                {
                    "submit_to_start": st["started"] - t,
                    "total": st["finished"] - t,
                }
            )
    return out


def pod_per_run(runs: int) -> list[dict[str, float]]:
    """Time ``runs`` T1 runs as one Argo workflow (one pod) each.

    Args:
        runs: How many.

    Returns:
        Per-run ``submit_to_start``, ``total`` and ``argo_wall`` seconds.
    """
    out: list[dict[str, float]] = []
    for _ in range(runs):
        t = time.time()
        name = subprocess.run(
            [
                "argo",
                "submit",
                "-n",
                NS,
                "--from",
                "workflowtemplate/t1-pod-per-run",
                "-o",
                "name",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ["argo", "wait", "-n", NS, name],
            capture_output=True,
            text=True,
            check=True,
        )
        argo_wall = time.time() - t
        logs = subprocess.run(
            ["argo", "logs", "-n", NS, name, "--no-color"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        start = re.search(r"CHRONON_START (\d+\.\d+)", logs)
        done = re.search(r"(\{.*\"finished_at\".*\})", logs)
        if not start or not done:
            raise RuntimeError(f"{name}: no timing lines in its log:\n{logs}")
        finished = float(json.loads(done.group(1))["finished_at"])
        out.append(
            {
                "submit_to_start": float(start.group(1)) - t,
                "total": finished - t,
                "argo_wall": argo_wall,
            }
        )
    return out


def summary(rows: list[dict[str, float]], key: str) -> str:
    """Format mean and p95 of one measure.

    Args:
        rows: Per-run measurements.
        key: The measure.

    Returns:
        ``"mean / p95 s"``.
    """
    xs = [r[key] for r in rows]
    return f"{sum(xs) / len(xs):.2f} / {pct(xs, 95):.2f} s"


def main() -> None:
    """Measure both paths and print the comparison."""
    from rich.console import Console
    from rich.table import Table

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--out", type=Path, default=ROOT / ".logs" / "rehearsal")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    now = time.time()
    token = mint("overhead-01", now - 60, now + 3600, [], ["workshop"])
    skew = clock_skew()
    w = warm(args.runs, token)
    p = pod_per_run(args.runs)

    t = Table(
        title=f"T1 run: warm worker vs pod per run ({args.runs} runs each, "
        f"sequential, idle device; simulated)"
    )
    t.add_column("path")
    t.add_column("submit → start (mean / p95)", justify="right")
    t.add_column("submit → done (mean / p95)", justify="right")
    t.add_column("argo submit→wait wall", justify="right")
    t.add_row(
        "warm worker", summary(w, "submit_to_start"), summary(w, "total"), "-"
    )
    t.add_row(
        "pod per run",
        summary(p, "submit_to_start"),
        summary(p, "total"),
        summary(p, "argo_wall"),
    )
    Console(width=140).print(t)
    print(
        f"laptop↔Docker VM clock skew: {skew * 1000:+.0f} ms (not subtracted)"
    )
    (args.out / "overhead.json").write_text(
        json.dumps(
            {"runs": args.runs, "skew_s": skew, "warm": w, "pod": p}, indent=1
        )
    )


if __name__ == "__main__":
    main()
