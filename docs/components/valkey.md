# Valkey (hot state)

## What it is

A single Valkey 8.1.10 instance (official image) in namespace `chronon`,
reachable only inside the cluster at `valkey:6379`. It holds each task's hot
status (`task:{id}`, a hash with a 24 h TTL) and, from rung 3, the device
queue.

## Why it's built this way

- **Polls never touch Postgres.** Fifty students polling once per second is
  fifty reads per second; a hash lookup in memory serves that without
  loading the database ([ADR-0008](../adr/0008-valkey.md)).
- **Persistence on (AOF, `appendfsync everysec`).** A restart keeps queued
  work: at most about a second of writes is lost.
- **`noeviction` with a 256 MB cap.** When full, Valkey refuses writes
  instead of silently evicting queued tasks; a loud failure beats lost work.
- **The hot copy can be lost.** Postgres holds every task too, and a poll
  that misses in Valkey falls back to it (counted in
  `chronon_db_reads_total`).

## How it fails

- **`OOM command not allowed`** on writes: the 256 MB cap was reached.
- **Pod restart.** The AOF replays; task hashes and queues survive.

## How to debug it

```bash
kubectl -n chronon exec valkey-0 -- valkey-cli INFO memory | grep used_memory_human
kubectl -n chronon exec valkey-0 -- valkey-cli --scan --pattern 'task:*' | head
kubectl -n chronon exec valkey-0 -- valkey-cli HGETALL task:<id>
kubectl -n chronon exec valkey-0 -- valkey-cli CONFIG GET maxmemory-policy
```
