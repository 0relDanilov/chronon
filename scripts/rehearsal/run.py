"""Workshop rehearsal: N students and one greedy user share the sim-qpu device.

``make rehearsal MODE=fifo|fair`` (or ``run.py --mode fair --users 50``).

1. Sets the scheduling mode (Valkey key ``sched:sim-qpu``) through a
   ``kubectl port-forward`` to Valkey; waits until the queue is empty.
2. Mints fresh tokens with the client's own TokenGenerator (provider flow).
3. The greedy user submits ``--greedy-runs`` t1 runs, 2 s before the cohort
   arrives, and tops up after 429s (fair mode caps it at 5 queued).
4. Each student submits one t1 run and polls once per second until done:
   student-01 with the real client in a subprocess (output captured), the
   rest with async httpx over HTTP/2, each on its own connection.
5. One out-of-window token is tried, to show the rejection.
6. Reads the occupancy stream, the tasks' own timestamps and the API's
   counters, prints a table, and writes JSON plus a PNG (overlaying both modes
   once both result files exist).

Waits are server-side (``started_at - submitted_at``, one clock). "Total" is
what a student experiences: submit until their poll sees a terminal state.
Everything the device does is simulated.
"""

import argparse
import asyncio
import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import httpx  # noqa: E402
import redis  # noqa: E402
from mint_tokens import TOKENS, mint  # noqa: E402

ROOT = HERE.parent.parent
API = os.environ.get("CHRONON_URL", "https://api.chronon.test:8443")
BACKEND = "sim-qpu"
PAYLOAD: dict[str, Any] = {"qubit": 0}
TERMINAL = {"SUCCESS", "FAILURE", "REVOKED"}
os.environ.setdefault("SSL_CERT_FILE", str(ROOT / ".certs" / "ca.pem"))


@dataclass
class Run:
    """One submitted task, as the submitter saw it."""

    user: str
    task_id: str
    submitted: float
    observed_done: float = 0.0
    status: str = "PENDING"
    polls: int = 0
    server: dict[str, float] = field(default_factory=dict[str, float])


@contextlib.contextmanager
def valkey_port_forward() -> Iterator[redis.Redis]:
    """Port-forward to the in-cluster Valkey and yield a client.

    Yields:
        A redis-py client on a local port.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    pf = subprocess.Popen(
        [
            "kubectl",
            "-n",
            "chronon",
            "port-forward",
            "svc/valkey",
            f"{port}:6379",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        client = redis.Redis(port=port, decode_responses=True)
        for _ in range(50):
            try:
                client.ping()
                break
            except redis.ConnectionError:
                time.sleep(0.2)
        yield client
    finally:
        pf.terminate()


def wait_idle(v: redis.Redis, timeout: float = 300) -> None:
    """Block until nothing is queued or running on the device.

    Args:
        v: Valkey client.
        timeout: Give up after this many seconds.

    Raises:
        TimeoutError: If the device stays busy.
    """
    deadline = time.time() + timeout
    keys = [f"q:{BACKEND}:fifo", f"q:{BACKEND}:rot", f"q:{BACKEND}:processing"]
    while time.time() < deadline:
        if all(v.llen(k) == 0 for k in keys):
            return
        time.sleep(1)
    raise TimeoutError("the device is still busy; try again later")


def counters(text: str) -> dict[str, float]:
    """Pick chronon's counters out of a Prometheus exposition.

    Args:
        text: The ``/metrics`` body.

    Returns:
        ``polls`` and ``db_reads`` (poll path) totals.
    """
    out = {"polls": 0.0, "db_reads": 0.0}
    for line in text.splitlines():
        if line.startswith("chronon_poll_total"):
            out["polls"] += float(line.rsplit(" ", 1)[1])
        elif line.startswith('chronon_db_reads_total{path="poll"}'):
            out["db_reads"] += float(line.rsplit(" ", 1)[1])
    return out


async def poll_until_done(c: httpx.AsyncClient, run: Run) -> None:
    """Poll once per second until the task is terminal, like the client.

    Args:
        c: The user's HTTP client.
        run: The task.
    """
    while run.status not in TERMINAL:
        await asyncio.sleep(1)
        r = await c.get(f"{API}/task/{BACKEND}/{run.task_id}")
        run.polls += 1
        run.status = r.json()["task_status"]
    run.observed_done = time.time()


def _client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        http2=True,
        http1=False,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )


async def student(name: str, token: str) -> Run:
    """One student: submit one t1 run and wait for it.

    Args:
        name: User id.
        token: Their token.

    Returns:
        The run.
    """
    async with _client(token) as c:
        t = time.time()
        r = await c.post(f"{API}/task/{BACKEND}/t1", json=PAYLOAD)
        r.raise_for_status()
        run = Run(name, r.json()["task_id"], t)
        await poll_until_done(c, run)
        return run


async def greedy(name: str, token: str, runs: int) -> tuple[list[Run], int]:
    """The eager student: submit ``runs`` runs as fast as allowed.

    Args:
        name: User id.
        token: Their token.
        runs: How many runs in total.

    Returns:
        The runs, and how many submissions were refused with 429.
    """
    done: list[Run] = []
    refused = 0
    async with _client(token) as c:
        pollers: list[asyncio.Task[None]] = []
        while len(done) < runs:
            t = time.time()
            r = await c.post(f"{API}/task/{BACKEND}/t1", json=PAYLOAD)
            if r.status_code == 429:
                refused += 1
                await asyncio.sleep(1)
                continue
            r.raise_for_status()
            run = Run(name, r.json()["task_id"], t)
            done.append(run)
            pollers.append(asyncio.create_task(poll_until_done(c, run)))
        await asyncio.gather(*pollers)
    return done, refused


_REAL_CLIENT = """
import sys, time
sys.path.insert(0, {scripts!r})
from connect import connect
qc = connect("sim-qpu", token="student-01")
t = time.time()
r = qc.run("t1", {payload!r})
print("RESULT_T1", r["result"]["t1_us"], "SECONDS", round(time.time() - t, 3))
"""


def real_client_student() -> tuple[str, float]:
    """student-01, with the unmodified client in a subprocess.

    Returns:
        The captured output and the wall time.
    """
    code = _REAL_CLIENT.format(scripts=str(HERE.parent), payload=PAYLOAD)
    t = time.time()
    p = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=900,
    )
    return p.stdout + p.stderr, time.time() - t


async def rehearse(
    users: int, greedy_runs: int, tokens: dict[str, str]
) -> dict[str, Any]:
    """Run the cohort.

    Args:
        users: Number of students, including student-01.
        greedy_runs: Runs the greedy user submits.
        tokens: Token per user.

    Returns:
        Raw results.
    """
    greedy_task = asyncio.create_task(
        greedy("greedy-01", tokens["greedy-01"], greedy_runs)
    )
    await asyncio.sleep(
        2
    )  # the eager student pressed run as the session opened
    cohort_start = time.time()
    real = asyncio.create_task(asyncio.to_thread(real_client_student))
    students = await asyncio.gather(
        *(
            student(f"student-{i:02d}", tokens[f"student-{i:02d}"])
            for i in range(2, users + 1)
        )
    )
    real_out, real_wall = await real
    greedy_runs_done, refused = await greedy_task
    return {
        "cohort_start": cohort_start,
        "students": students,
        "greedy": greedy_runs_done,
        "greedy_refused": refused,
        "real_client": {"output": real_out, "wall_s": real_wall},
    }


def pct(xs: list[float], p: float) -> float:
    """Percentile with linear interpolation.

    Args:
        xs: Values.
        p: Percentile, 0 to 100.

    Returns:
        The percentile, or NaN for no values.
    """
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def stamps(v: redis.Redis, task_id: str) -> dict[str, float]:
    """Read a task's server-side timestamps from its hot hash.

    Args:
        v: Valkey client.
        task_id: The task.

    Returns:
        Whichever of ``submitted``, ``started``, ``finished`` are set.
    """
    fields = ("submitted_at", "started_at", "finished_at")
    raw = cast(list[str | None], v.hmget(f"task:{task_id}", list(fields)))
    return {
        name.removesuffix("_at"): float(x)
        for name, x in zip(fields, raw, strict=True)
        if x
    }


def analyse(raw: dict[str, Any], v: redis.Redis, t0: float) -> dict[str, Any]:
    """Join submitter records with server timestamps and occupancy.

    Args:
        raw: From ``rehearse``.
        v: Valkey client.
        t0: When the run began (greedy's first submit).

    Returns:
        Summary statistics and per-task records.
    """
    runs: list[Run] = [*raw["students"], *raw["greedy"]]
    real_id = re.search(r"id = ([0-9a-f-]{36})", raw["real_client"]["output"])
    for r in runs:
        r.server = stamps(v, r.task_id)

    occ: list[dict[str, Any]] = []
    entries = cast(
        list[tuple[str, dict[str, str]]],
        v.xrange(f"occupancy:{BACKEND}", min=str(int(t0 * 1000) - 1000)),
    )
    for _, f in entries:
        if float(f["start"]) >= t0 - 1:
            occ.append(
                {k: f[k] for k in ("user", "task")}
                | {"start": float(f["start"]), "end": float(f["end"])}
            )
    if real_id:
        rid = real_id.group(1)
        st = stamps(v, rid)
        if len(st) == 3:
            sub, start, fin = st["submitted"], st["started"], st["finished"]
            runs.append(
                Run(
                    "student-01",
                    rid,
                    sub,
                    sub + raw["real_client"]["wall_s"],
                    "SUCCESS",
                    0,
                    {"submitted": sub, "started": start, "finished": fin},
                )
            )

    cohort = [
        r
        for r in runs
        if r.user.startswith("student-") and "started" in r.server
    ]
    g = [
        r for r in runs if r.user.startswith("greedy") and "started" in r.server
    ]
    waits = [r.server["started"] - r.server["submitted"] for r in cohort]
    totals = [r.observed_done - r.submitted for r in cohort if r.observed_done]
    last_student = max((r.server["finished"] for r in cohort), default=t0)
    first, last = min(o["start"] for o in occ), max(o["end"] for o in occ)
    busy = sum(o["end"] - o["start"] for o in occ)

    def device_s(pred: Any) -> float:
        return sum(
            max(
                0.0,
                min(o["end"], last_student)
                - max(o["start"], raw["cohort_start"]),
            )
            for o in occ
            if pred(o)
        )

    in_window = device_s(lambda o: True)
    return {
        "students": len(cohort),
        "greedy_runs": len(g),
        "greedy_refused_429": raw["greedy_refused"],
        "wait_p50_s": pct(waits, 50),
        "wait_p95_s": pct(waits, 95),
        "wait_max_s": max(waits, default=float("nan")),
        "total_p50_s": pct(totals, 50),
        "total_p95_s": pct(totals, 95),
        "greedy_wait_p50_s": pct(
            [r.server["started"] - r.server["submitted"] for r in g], 50
        ),
        "utilization": busy / (last - first) if last > first else float("nan"),
        "greedy_share_until_last_student": (
            device_s(lambda o: o["user"].startswith("greedy")) / in_window
            if in_window
            else float("nan")
        ),
        "last_student_done_s": last_student - raw["cohort_start"],
        "wall_s": last - t0,
        "real_client_wall_s": raw["real_client"]["wall_s"],
        "real_client_ok": "successfully executed"
        in raw["real_client"]["output"],
        "occupancy": occ,
        "waits": waits,
        "runs": [asdict(r) for r in runs],
        "cohort_start": raw["cohort_start"],
    }


def table(mode: str, res: dict[str, Any], users: int) -> None:
    """Print the results as a rich table.

    Args:
        mode: fifo or fair.
        res: From ``analyse`` plus counters and the rejection.
        users: Cohort size.
    """
    from rich.console import Console
    from rich.table import Table

    t = Table(
        title=f"Rehearsal · mode={mode} · {users} students + 1 greedy "
        f"({res['greedy_runs']} runs) · simulated device"
    )
    t.add_column("metric")
    t.add_column("value", justify="right")
    rows = [
        ("students served", f"{res['students']}"),
        (
            "wait submit→start p50 / p95 / max",
            f"{res['wait_p50_s']:.1f} / {res['wait_p95_s']:.1f} / "
            f"{res['wait_max_s']:.1f} s",
        ),
        (
            "total as seen by a student p50 / p95",
            f"{res['total_p50_s']:.1f} / {res['total_p95_s']:.1f} s",
        ),
        (
            "last student done after cohort arrived",
            f"{res['last_student_done_s']:.1f} s",
        ),
        ("device utilization (busy / wall)", f"{res['utilization']:.1%}"),
        (
            "greedy share of device time until last student",
            f"{res['greedy_share_until_last_student']:.1%}",
        ),
        (
            "greedy wait p50 · submissions refused (429)",
            f"{res['greedy_wait_p50_s']:.1f} s · {res['greedy_refused_429']}",
        ),
        (
            "polls served · DB reads while polling",
            f"{res['polls']:.0f} · {res['db_reads']:.0f}",
        ),
        (
            "real client (student-01) ok · wall",
            f"{res['real_client_ok']} · {res['real_client_wall_s']:.1f} s",
        ),
        (
            "out-of-window token",
            f"{res['rejected_status']}: {res['rejected_detail']}",
        ),
    ]
    for k, val in rows:
        t.add_row(k, val)
    Console(width=140).print(t)


def chart(out: Path) -> Path:
    """Occupancy timeline per mode plus the wait CDF; overlays modes found.

    Args:
        out: The results directory.

    Returns:
        The PNG written (named after the most recent mode).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    found = {
        m: json.loads(p.read_text())
        for m in ("fifo", "fair")
        if (p := out / f"rehearsal-{m}.json").exists()
    }
    fig, axes = plt.subplots(
        len(found) + 1,
        1,
        figsize=(11, 2.2 * len(found) + 3.2),
        gridspec_kw={"height_ratios": [1] * len(found) + [2]},
    )
    colours = {"fifo": "#c0504d", "fair": "#4f81bd"}
    for ax, (m, res) in zip(axes, found.items(), strict=False):
        t0 = res["cohort_start"]
        for o in res["occupancy"]:
            u = o["user"]
            c = (
                "#d62728"
                if u.startswith("greedy")
                else "#ffbf00"
                if u == "student-01"
                else ("#7f9fbf" if int(u.split("-")[1]) % 2 else "#a8bfd6")
            )
            ax.barh(
                0,
                o["end"] - o["start"],
                left=o["start"] - t0,
                color=c,
                edgecolor="white",
                linewidth=0.3,
            )
        ax.set_yticks([])
        ax.set_xlabel("seconds since the cohort arrived")
        ax.set_title(
            f"{m}: who held the device "
            "(red = greedy, gold = student-01 on the real client)",
            fontsize=9,
        )
    cdf = axes[-1]
    for m, res in found.items():
        w = sorted(res["waits"])
        cdf.step(
            w,
            [(i + 1) / len(w) for i in range(len(w))],
            where="post",
            label=f"{m}: p50 {res['wait_p50_s']:.1f} s, "
            f"p95 {res['wait_p95_s']:.1f} s",
            color=colours[m],
        )
    cdf.set_xlabel("student wait, submit → start (s)")
    cdf.set_ylabel("fraction of students")
    cdf.legend()
    cdf.grid(alpha=0.3)
    fig.suptitle(
        "chronon workshop rehearsal (simulated device, synthetic data)",
        fontsize=10,
    )
    fig.tight_layout()
    latest = max(
        found, key=lambda m: (out / f"rehearsal-{m}.json").stat().st_mtime
    )
    path = out / f"rehearsal-{latest}.png"
    fig.savefig(path, dpi=130)
    return path


def main() -> None:
    """Run one rehearsal."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--mode", choices=["fifo", "fair"], required=True)
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--greedy-runs", type=int, default=20)
    ap.add_argument("--out", type=Path, default=ROOT / ".logs" / "rehearsal")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    now = time.time()
    names = [f"student-{i:02d}" for i in range(1, args.users + 1)] + [
        "greedy-01"
    ]
    tokens = {
        n: mint(n, now - 60, now + 2 * 3600, [], ["workshop"]) for n in names
    }
    expired = mint(
        "expired-01", now - 3 * 3600, now - 2 * 3600, [], ["workshop"]
    )
    TOKENS.mkdir(exist_ok=True)
    (TOKENS / "student-01").write_text(tokens["student-01"])

    with valkey_port_forward() as v:
        wait_idle(v)
        v.set(f"sched:{BACKEND}", args.mode)
        print(
            f"mode={args.mode}: {args.users} students, "
            f"greedy submits {args.greedy_runs}"
        )
        with httpx.Client(http2=True, http1=False, timeout=30) as c:
            before = counters(c.get(f"{API}/metrics").text)
            rej = c.post(
                f"{API}/task/{BACKEND}/t1",
                json=PAYLOAD,
                headers={"Authorization": f"Bearer {expired}"},
            )
            t0 = time.time()
            raw = asyncio.run(rehearse(args.users, args.greedy_runs, tokens))
            after = counters(c.get(f"{API}/metrics").text)
        res = analyse(raw, v, t0)
    res |= {
        "mode": args.mode,
        "users": args.users,
        "polls": after["polls"] - before["polls"],
        "db_reads": after["db_reads"] - before["db_reads"],
        "rejected_status": rej.status_code,
        "rejected_detail": rej.json()["detail"],
        "real_client_output_tail": raw["real_client"]["output"][-600:],
    }
    (args.out / f"rehearsal-{args.mode}.json").write_text(
        json.dumps(res, indent=1, default=str)
    )
    table(args.mode, res, args.users)
    print(f"chart: {chart(args.out)}")


if __name__ == "__main__":
    main()
