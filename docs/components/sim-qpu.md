# sim-qpu (the simulated time-shared device)

## What it is

A **simulated** single-qubit device and the worker that owns it. Everything
it "measures" is synthetic. It runs two device workflows:

| Workflow | Role | What it does |
|---|---|---|
| `t1` | any | excite, wait, read out, at 25 wait times × 500 shots by default; fits T1 |
| `calibrate` | `calibrator` | a T1 run, then a new `state` dataset linked to the previous one |

Each task goes through the device lifecycle **reconfigure (0.5 s) → run (≈2.1 s
by default) → reset (0.2 s)**, and the client sees `PENDING` → `STARTED` →
`SUCCESS` (or `FAILURE`, or `REVOKED`).

## Why it's built this way

- **One worker owns the device.** `replicas: 1` and `strategy: Recreate`:
  an update stops the old pod before starting the new one, so two processes
  never drive the same hardware. A RollingUpdate would overlap them.
- **A warm, long-lived worker** instead of a pod per run: a run takes about 3 s,
  and starting a pod costs seconds of its own (measured in
  [ADR-0004](../adr/0004-warm-worker-vs-pod-per-run.md)).
- **Scheduling is a Valkey key** (`sched:sim-qpu`: `fifo` or `fair`), read on
  every pop ([ADR-0005](../adr/0005-fair-scheduling.md)):
  - `fifo`: one global list, no cap.
  - `fair`: one list per user and a rotation of users with queued work. The
    device serves one run per user per turn, and each user may have at most 5
    queued (a readable 429 beyond that).
- **Atomic queue operations.** Push and pop are Lua scripts in Valkey:
  the cap check, the enqueue, the rotation update and the task's hot status
  happen in one step, so concurrent submits can't overshoot the cap.
- **Crash-safe.** A popped task sits in `q:sim-qpu:processing` until it
  finishes; a restarted worker re-queues whatever was left there.
- **The device publishes its own summary.** At startup the worker migrates and
  runs the (idempotent) seed. The summary is defined in code, so it changes
  with the image, which a git-triggered hook wouldn't notice.
- **Physics, honestly fake.** The hidden true T1 starts at 60 µs and
  random-walks within 40–80 µs. Shots are Bernoulli draws with
  p = exp(−t/T1), 2% of readouts are flipped, and `scipy.optimize.curve_fit`
  fits A·exp(−t/T1)+B. The reported uncertainty is honest: the fit lands
  within ±2σ of the truth in 95.5% of 200 trials (95.4% expected).
- **Special result keys** the client pretty-prints:
  `__qpu_execution_time_seconds` (device time; the client labels it "QUA
  execution time"), `__total_python_runtime_seconds`, and `__fridge_info` as
  `{"mxc": {"temperature_kelvin": 0.0118, "unix_timestamp": …}}`, all simulated.

## How it fails

- **Runs stay `PENDING`.** The worker isn't running, or it's stuck: the
  liveness probe restarts it if its loop hasn't touched `/tmp/heartbeat` for
  60 s.
- **429 in fair mode:** the user already has 5 queued. This is by design.
- **A run fails:** `FAILURE`, with the exception in `stderr`; the loop
  continues with the next task.
- **Revoke while running.** The flag is checked after reconfigure, before the
  run phase. A run already in its run phase finishes.

## How to debug it

```bash
kubectl -n chronon logs deploy/sim-qpu-worker --tail=30
kubectl -n chronon exec valkey-0 -- valkey-cli GET sched:sim-qpu        # mode (nil = fair)
kubectl -n chronon exec valkey-0 -- valkey-cli SET sched:sim-qpu fifo   # switch
kubectl -n chronon exec valkey-0 -- valkey-cli LRANGE q:sim-qpu:rot 0 -1
kubectl -n chronon exec valkey-0 -- valkey-cli LRANGE q:sim-qpu:processing 0 -1
kubectl -n chronon exec valkey-0 -- valkey-cli XREVRANGE occupancy:sim-qpu + - COUNT 5
uv run --extra dev pytest -q tests/unit/test_queue.py tests/unit/test_physics.py
```
