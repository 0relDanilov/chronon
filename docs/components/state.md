# chronon-state (datasets)

## What it is

A FastAPI service at `https://state.chronon.test:8443` that stores
**datasets**: versioned JSON documents per backend (the `summary`, calibration
`state`, results), each optionally linked to a parent. It serves exactly the
paths the client's `StateService` calls.

| Endpoint | Client method |
|---|---|
| `GET /{backend}/state/?skip&limit&datatype&producer` | `list`, `get_latest` |
| `GET /{backend}/state/{id}` | `get` |
| `POST /{backend}/state/` | `push` (role `calibrator`) |
| `GET /{backend}/state/{id}/children?skip&limit&type&producer` | `list_children` |
| `GET /{backend}/timeseries/?jsonpath&skip&limit&datatype&producer` | `trend` |

## Why it's built this way

- **Exact paths and names.** Trailing slashes matter, and the filter is
  `datatype` everywhere except `/children`, where the client sends `type`.
  Results are newest first.
- **jsonpath in the database.** `trend("$.qubits[0].t1")` becomes
  `jsonb_path_query_array(data, '$.qubits[0].t1')` in Postgres, so a trend
  over many datasets is one query. When exactly one value matches, it is
  returned as a scalar: the client plots only `int`/`float` values, so a
  one-element list would draw nothing.
- **Write protection.** `POST` needs the `calibrator` role, and the types
  `qmm_capabilities` and `key_qua` are refused for everyone. The client
  unpickles the first and encrypts to the second, so whoever writes them
  controls every client.
- **Seeded.** A PostSync hook (`chronon.seed`) writes each backend's
  `summary` (only when it changes) and an initial, synthetic `state` dataset,
  because the client's `summary()` crashes when it lists `state` and none
  exists.

## How it fails

- **The client's constructor prints an error and `summary()` returns None.**
  The token was rejected (401/403); the detail says why. Every error is JSON,
  because the client parses error bodies without a `try`.
- **No summary.** The seed hook didn't run (see below).
- **422 on `/timeseries/`.** The jsonpath doesn't parse; the detail quotes
  Postgres's message.

## How to debug it

```bash
kubectl -n chronon logs deploy/chronon-state -c app --tail=50
kubectl -n chronon get job chronon-seed && kubectl -n chronon logs job/chronon-seed
# If the seed Job is missing after a sync, run the app's sync by hand:
kubectl config set-context --current --namespace=argocd
argocd login --core && argocd app sync chronon
kubectl -n chronon exec -it chronon-db-1 -- psql -U postgres chronon \
  -c "select id, type, producer, timestamp from datasets order by id desc limit 5"
```
