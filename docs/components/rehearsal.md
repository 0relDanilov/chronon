# The workshop rehearsal and the overhead measurement

## What it is

Two scripts that put numbers on the platform's main claims, against the live
local site. Everything the device does is simulated; the numbers measure the
**platform** (queueing, scheduling, polling), not physics.

| Script | Answers |
|---|---|
| `scripts/rehearsal/run.py --mode fifo\|fair --users N` (`make rehearsal`) | How long do students wait when N of them press "run" together, one eager student got there first, and the scheduler is FIFO or fair? |
| `scripts/rehearsal/overhead.py --runs N` | What does a pod per run (Argo Workflows) cost against the warm worker, for the same 3 s run? |

## How the rehearsal works

1. Sets `sched:sim-qpu` to the mode, through a `kubectl port-forward` to
   Valkey (no new endpoint), and waits for an idle device.
2. Mints fresh tokens with the client's own `TokenGenerator`.
3. `greedy-01` submits 20 `t1` runs, **2 s before the cohort**, and keeps
   resubmitting after each 429 (fair mode holds it to 5 queued).
4. Each student submits one `t1` and polls once per second, each on its own
   HTTP/2 connection. **student-01 uses the unmodified client** in a
   subprocess, output captured.
5. An out-of-window token is tried once, to record the rejection.
6. Joins submit records with the tasks' **server** timestamps and the
   occupancy stream, and reads the API's counters before and after.

Reported: student wait (submit→start) p50/p95/max; total as a student sees it;
device utilization; the greedy user's share of device time **until the last
student finished** (over the whole run every task completes, so the overall
share is the same in both modes and says nothing); polls served vs DB reads;
the real client's result; the rejection's detail. Output goes to
`.logs/rehearsal/`: `rehearsal-<mode>.json` and `rehearsal-<mode>.png` (a
timeline of who held the device, plus the wait CDF; both modes once both have
run).

## Smoke run (5 students, not the 50-student result)

| | fifo | fair |
|---|---|---|
| student wait p50 / p95 | 60.1 / 63.6 s | 9.5 / 15.4 s |
| last student done after the cohort arrived | 68.4 s | 20.7 s |
| greedy share until the last student | 79.7% | 32.8% |
| greedy submissions refused (429) | 0 | 52 |
| polls · DB reads while polling | 893 · 0 | 424 · 0 |
| device utilization | 99.5% | 99.5% |

`make rehearsal MODE=fifo USERS=5` and `MODE=fair`, Mon 19 Oct 23:42.

## How the overhead measurement works

Both paths run identical device code (reconfigure → T1 → reset), one run at a
time on an idle device. *Start* is when the device code begins: the warm
task's `started_at`, or the pod's first log line `CHRONON_START`, printed
before any import, so image start and Python imports count as pod overhead.
The script prints the laptop↔Docker VM clock skew (+70 ms in the smoke run).

Smoke run, **2 runs each** (not a measurement):

| | submit → start | submit → done |
|---|---|---|
| warm worker | 0.24 s | 2.85 s |
| pod per run | 11.46 s | 17.34 s |

## How it fails

- **`TimeoutError: the device is still busy`**: another run is queued;
  wait, or check `valkey-cli LLEN q:sim-qpu:processing`.
- **`CERTIFICATE_VERIFY_FAILED`**: `make ca`; the scripts default
  `SSL_CERT_FILE` to `.certs/ca.pem`.
- **`argo` errors**: the `t1-pod-per-run` WorkflowTemplate isn't synced
  (`kubectl -n chronon get workflowtemplate`).
- **Mode left as the last run's**: the scripts set `sched:sim-qpu` and leave
  it; the default (key missing) is `fair`.

## How to debug it

```bash
make rehearsal MODE=fair USERS=5              # a quick check
cat .logs/rehearsal/rehearsal-fair.json | jq '{wait_p50_s, wait_p95_s, polls, db_reads}'
argo list -n chronon                           # pod-per-run workflows
kubectl -n chronon exec valkey-0 -- valkey-cli XLEN occupancy:sim-qpu
```
