# ADR-0009: Postgres on CloudNativePG, datasets as JSONB

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

Datasets are arbitrary JSON (summaries, calibrations, results) with lineage
(`parent_id`), and the client asks for trends: a jsonpath evaluated across
many datasets, newest first.

## Options

| Option | Where it breaks |
|---|---|
| **A. PostgreSQL on CNPG, 2 instances; one `datasets` table with JSONB `data`, GIN `jsonb_path_ops`** | jsonpath queries scan the filtered rows; past millions of datasets per type, trends need a time-partitioned table or a dedicated series store. |
| B. A plain Postgres StatefulSet | No failover, no primary-following Service, credentials by hand. Kept as the kill-switch fallback. |
| C. A document database | Native JSON, but no relational lineage, transactions with the tasks table, or SQL jsonpath. One more system to run. |
| D. A table per dataset type | Typed columns and fast trends, but every new type is a migration, and the client's datasets are schemaless by design. |
| E. TimescaleDB for trends | Good for high-rate series; calibrations arrive a few times a day. |

## Decision

A. PostgreSQL 17.11 pinned (CNPG 1.30.1 defaults to 18.6). SQLAlchemy 2 and
Alembic; each service's initContainer runs `python -m chronon.migrate` under
a Postgres advisory lock, so the schema always matches the image that's
starting.

## Consequences

- CNPG owns the credentials (`Secret chronon-db-app`); nothing secret in git.
- Backups (Barman Cloud plugin) are documented, not configured: a rebuilt
  local site starts empty.
- `trend()` is one SQL query: `jsonb_path_query_array(data, $path)`, with a
  single match unwrapped to a scalar so the client can plot it.

## Measured numbers

| What | Value | Command |
|---|---|---|
| Cluster ready from first sync | ~2.5 min (initdb, then the replica joins) | `kubectl -n chronon get pods -w` during the 23:00 sync |
| Seed (migrate + summary + initial state) | 0.3 s | `kubectl -n chronon logs job/chronon-seed` |
