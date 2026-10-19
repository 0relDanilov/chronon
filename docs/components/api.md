# chronon-api (tasks)

## What it is

A FastAPI service behind the Gateway at `https://api.chronon.test:8443`.
It accepts workflow runs, reports their status, and revokes them, using the
paths and shapes the unmodified client expects ([contract](../contract.md)).

| Endpoint | Does |
|---|---|
| `POST /task/{backend}/{workflow}` | verify the token → find the workflow → check its role → validate the payload (JSON Schema) → record the task → run inline (`echo`) or queue it for the device. Returns **200** `{"task_id"}` (the client rejects 201/202). |
| `GET /task/{backend}/{id}` | the task's `{task_status, task_result}`, from **Valkey only**. Only the submitter sees a task. |
| `DELETE /task/{backend}/{id}` | revoke: a pending task becomes `REVOKED`; a running one gets a flag the worker checks between runs. |
| `GET /metrics` | Prometheus counters: `chronon_poll_total`, `chronon_db_reads_total{path}`, `chronon_submit_total`. |

## Why it's built this way

- **The token path** (`chronon.auth`): RS256 signature against every
  provider key registered for the backend (tokens have no `kid`); then the
  `qpu[backend]` grant; then `expires` and the `from`/`to` window, by hand,
  because the tokens use `expires`, not `exp`; then the workflow's role. Any
  token PyJWT rejects (including unsigned `alg: none`) is a 401, never a 500.
- **Readable errors.** Every error is `{"detail": "…"}`, and auth errors
  say what to do. Real output, out-of-window token:

  > Your access window for backend sim-qpu is 2026-10-19 17:07:42 UTC →
  > 2026-10-19 18:07:42 UTC; it is now 2026-10-19 20:07:44 UTC, so it closed
  > 2 h 0 min ago. Ask the backend provider for a token covering the current
  > time.

- **The polling hot path.** Each student polls once per second while waiting.
  Polls read `HGETALL task:{id}` from Valkey; Postgres is read only if the
  hot copy is missing, and each such read is counted.
- **Synchronous endpoints.** Database and Valkey calls block, so the
  handlers are plain `def`, and FastAPI runs them in its threadpool instead
  of blocking the event loop.
- **`task_result` is always a JSON object string** (`"{}"` until done),
  because the client calls `json.loads(...)` and then `.get` on it.

## How it fails

- **401/403 with a detail.** Read the detail; it names the window, the
  roles, or the backend the token covers.
- **Unknown task ids reach Postgres.** A miss in Valkey falls back to the
  database, so polling ids that were never issued costs one DB read each.
  *Known gap*: a short negative cache, or rejecting ids that were never
  issued, would close it.
- **Gateway errors aren't JSON.** If no API pod is ready, Envoy answers 503
  `no healthy upstream` in plain text, and the client raises
  `ConnectionError`. The service's own errors are always JSON; the edge's
  aren't.
- **Valkey down.** Submits and polls fail with a JSON 500 carrying a `ref`;
  the log line with that ref has the traceback.

## How to debug it

```bash
kubectl -n chronon logs deploy/chronon-api -c app --tail=50
kubectl -n chronon logs deploy/chronon-api -c migrate      # the initContainer
curl -s --cacert .certs/ca.pem https://api.chronon.test:8443/metrics | grep ^chronon_
kubectl -n chronon exec valkey-0 -- valkey-cli HGETALL task:<id>
make contract                                              # the real client, end to end
```
