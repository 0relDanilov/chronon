# ADR-0005: Per-user round-robin ("fair") scheduling with a per-user cap

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

One device, many students: a 50-person workshop where each student presses
"run" around the same time, and one eager student submits 20 runs first.
With first-come-first-served, everyone else waits behind those 20 runs, about
a minute at 3 s per run.

## Options

| Option | Where it breaks |
|---|---|
| **A. "fair": per-user queues served round-robin, plus a cap of 5 queued runs per user** | Equal turns per *user*, not per project or per paying group; a user with many tokens (identities) gets many turns. |
| B. FIFO, one global queue | One greedy user delays everyone; waits depend on who clicked first. Kept as a mode (`fifo`) for the comparison. |
| C. Weighted fair queuing by project | The right next step when projects have quotas; needs a quota source. |
| D. Deadline / reservation slots | The model for booked hardware time; heavier than a workshop needs. |
| E. Valkey Streams with consumer groups | They solve *many* consumers sharing a stream; this device has exactly one consumer, and streams have no per-user rotation. |

## Decision

A, with B selectable at run time through the Valkey key `sched:sim-qpu`.
"fair" bundles two mechanisms, and the rehearsal reports both: the rotation
(turn order) and the cap (bounded queue per user, a readable 429).

Push and pop are Lua scripts, so each is atomic. The scripts build per-user
key names at run time: fine on one Valkey instance, but on Valkey Cluster all
keys of a backend would need one hash tag, `{sim-qpu}`, to stay on one shard.

## Consequences

- The greedy user is held to 5 queued and gets one turn per round; other
  users' first runs start within one round.
- Switching modes strands nothing: pop drains the other mode's structures
  too.
- The cap applies only to queued runs, not to the one running.

## Measured numbers

| What | Value | Command |
|---|---|---|
| Order, 20 greedy queued then 5 users × 1 (unit test, real Lua) | fair: all 5 within the first 6 pops; fifo: after all 20 | `pytest tests/unit/test_queue.py` |
| Rehearsal, p50/p95 wait, greedy share (FIFO vs fair, 50 users) | *Tuesday* | `make rehearsal MODE=fifo` / `MODE=fair` |
