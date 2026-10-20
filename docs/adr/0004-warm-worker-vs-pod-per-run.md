# ADR-0004: A warm worker for short exclusive runs; Argo Workflows for long or parallel work

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

Device runs are short (≈3 s including reconfigure and reset) and exclusive (one
at a time). Some work is long and parallel instead, like the Stark-map fan-out.
The client's task states (`PENDING`, `RECEIVED`, `STARTED`, `SUCCESS`, …) look
like a Celery-style task queue, and the client never says how runs are
executed.

## Options

| Option | Where it breaks |
|---|---|
| **A. One warm, long-lived worker per device, fed by a Valkey queue** | The worker is a single process: its health is the device's availability. Mitigated by the liveness probe and the crash-safe processing list. |
| B. A pod per run (Argo Workflows, `synchronization.mutexes` for exclusivity) | Every run pays pod scheduling, image start and Python import time, which can exceed a 3 s run. |
| C. Celery workers | The same shape as A, with a framework around it; more moving parts than one loop and two Lua scripts. |
| D. A sidecar per user session | Isolation per user, but the device can still be driven by only one of them at a time. |

## Decision

A for device runs; Argo Workflows (B) for long, parallel jobs where startup
cost is amortized over minutes (the Stark-map backend).

## Consequences

- Device time isn't spent on pod startup between users.
- The worker publishes its own summary and re-queues stranded tasks on start.

## Measured numbers

| What | Value | Command |
|---|---|---|
| Warm worker, one default `t1` run, submit to SUCCESS seen by the client | 3.6 s wall (2.08 s device + 0.7 s reconfigure and reset + 1 s poll granularity) | `qc.run("t1", {"qubit": 0})` at 23:23 |
| Smoke (2 runs each, not a measurement): submit→start · submit→done | warm 0.24 s · 2.85 s; pod per run 11.46 s · 17.34 s (clock skew +70 ms) | `overhead.py --runs 2`, Mon 23:47 |
| **10 runs each**: submit→start mean / p95 | warm 0.08 / 0.11 s; pod per run 3.47 / 3.97 s | `uv run --extra dev python scripts/rehearsal/overhead.py --runs 10`, Tue 20 Oct 13:05 |
| 10 runs each: submit→done mean / p95 | warm 2.68 / 2.71 s; pod per run 9.43 / 10.07 s (≈3.5×) | same |
| 10 runs: `argo submit`→`argo wait` wall (incl. Argo bookkeeping) | 20.46 / 20.76 s | same |
| Laptop↔Docker VM clock skew (not subtracted) | +65 ms | same |
