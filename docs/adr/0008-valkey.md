# ADR-0008: Valkey for hot task state and the queue

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

Every waiting student polls `GET /task/...` once per second; a 50-student
workshop is about 50 reads per second of tiny, short-lived state. The device
queue (rung 3) needs atomic push and pop.

## Options

| Option | Where it breaks |
|---|---|
| **A. Valkey 8 (BSD-3), one instance, AOF on, `noeviction`** | One instance is a single point of failure: restarts replay the AOF, but there's no failover. |
| B. Redis 8 | Same engine; tri-licensed (RSALv2 / SSPLv1 / AGPLv3). The licence choice becomes a question for every site that runs it. |
| C. Poll Postgres directly | Works at 50 rps, but every poll becomes a query and a connection, and it competes with the writes that matter. |
| D. Separate instances for cache and queue | The right split when cache eviction is wanted; here nothing may be evicted, so one `noeviction` instance serves both. |

## Decision

A. Valkey via redis-py, `appendonly yes`, `appendfsync everysec`,
`maxmemory 256mb`, `maxmemory-policy noeviction`, ClusterIP only. Task hashes
expire after 24 h; Postgres keeps the durable record and is the fallback.

## Consequences

- A poll for a known task costs one `HGETALL` and no database read.
- Polls for ids that were never issued fall back to Postgres (a known gap;
  a negative cache would close it).
- A Valkey restart loses at most about 1 s of writes (`everysec`).

## Measured numbers

| What | Value | Command |
|---|---|---|
| DB reads while polling known tasks | 0 (`chronon_db_reads_total{path="poll"}` unchanged across a run) | `make contract` (`test_polls_are_served_from_valkey`) |
| Rehearsal: polls and DB reads under load | *Tuesday* | `make rehearsal MODE=fair` |
