# Postgres (CloudNativePG)

## What it is

The durable store: tables `datasets` and `tasks` in database `chronon`, on a
CloudNativePG `Cluster` named `chronon-db` with **2 instances**: one primary
and one streaming replica. PostgreSQL is pinned to 17.11; the operator's own
default is 18.

## Why it's built this way

- **An operator, not a StatefulSet.** CNPG handles what a plain StatefulSet
  doesn't: failover to the replica, the `-rw`/`-ro` Services that follow
  the primary, and generated credentials ([ADR-0009](../adr/0009-postgres-cnpg-jsonb.md)).
- **No secret in git.** CNPG writes `Secret chronon-db-app`; the services
  read its `uri` key ([ADR-0003](../adr/0003-no-secrets-in-git.md)).
- **JSONB with a GIN `jsonb_path_ops` index** on `datasets.data`, for
  jsonpath containment queries.
- **Migrations in every service's initContainer** (`python -m
  chronon.migrate`), serialized by a Postgres advisory lock. The schema is
  always the one the starting image expects, even when only the image
  changed, which a git-triggered hook would miss.

## How it fails

- **Pods stuck in `Init`.** The migrate container waits up to 2 minutes for
  the database. Before CNPG creates `chronon-db-app`, pods show
  `CreateContainerConfigError`, and the kubelet retries.
- **Primary lost.** CNPG promotes the replica; `chronon-db-rw` follows it.
  In-flight transactions fail once; the connection pool's `pre_ping`
  reconnects.

## How to debug it

```bash
kubectl -n chronon get cluster chronon-db          # instances, primary, phase
kubectl -n chronon get pods -l cnpg.io/cluster=chronon-db -L role
kubectl -n chronon exec -it chronon-db-1 -- psql -U postgres chronon -c '\dt'
kubectl -n chronon exec -it chronon-db-1 -- psql -U postgres chronon \
  -c "select version_num from alembic_version"
```
