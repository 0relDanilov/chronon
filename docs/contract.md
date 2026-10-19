# The client contract

This page is the source of truth for the task and state API **as
`iqcc-cloud-client` 0.20.0 uses it**. Every behaviour cites the vendored
source: `vendor/iqcc-cloud-client-0.20.0/src/iqcc_cloud_client/<file>:<line>`.
Paths below are relative to that directory. chronon implements the server
side of this contract; it never changes the client.

## How chronon points the client at itself

Upstream defaults: the task API is `https://cloud.i-qcc.com`
(`computers.py:44`), the state service `https://state.i-qcc.com`
(`computers.py:747-761`) and the datastore `https://ds.i-qcc.com`
(`computers.py:100`).

`IQCC_Cloud.state` is a property with a `state_service_url` default
argument. A property can't receive arguments, so the default is always used,
and the constructor calls it three times (`computers.py:108, 114, 137`). The
URL can't be overridden per call. `scripts/client_patch.py` therefore
replaces the property on the class **before any instance is constructed**, and
also:

- requires an explicit `api_token`, because without one the constructor reads
  `~/.config/iqcc_cloud/config.toml`, whose `url` key overrides the
  argument (`computers.py:61-73`);
- disables `.data` (the datastore, `computers.py:763-779`);
- guards `httpx.Client.send` so a request to the upstream domain raises
  before it leaves the process.

## Transport

| Behaviour | Source |
|---|---|
| Task client: `http2=True, http1=False` for every URL except `http://localhost:8000`. Over TLS, that means ALPN must negotiate `h2`; an HTTP/1.1-only server fails the handshake. | `computers.py:371-376`, `443-448`, `474-479` |
| State client: `http2=True, http1=False` **always**. There's no localhost exception. | `state.py:29-31` |
| Headers on every request: `Authorization: Bearer <token>`, `User-agent: iqcc-cloud-client/0.20.0`. | `computers.py:91-96` |
| Timeouts: 60 s default; task polls use 10 s, then 5 s. | `computers.py:107`, `424-441`, `464-471` |

## Errors (both services)

- Success means **exactly HTTP 200** (`httpx.codes.OK`). A 201 or 202 is
  treated as an error (`computers.py:343`, `state.py:65, 126, 146, 194, 332`).
  `POST` endpoints must therefore return 200.
- The task client prints the status phrase, then tries `r.json()["detail"]`.
  If the body isn't JSON it raises `ConnectionError`; otherwise
  `ValueError` (`computers.py:343-354`).
- The state client calls `r.json()["detail"]` on errors **without a `try`**
  (`state.py:94-95, 129-130, 155-156, 214-215, 361-362`). A non-JSON error
  body (for example a plain-text 500 from a proxy or a framework default)
  raises inside the client, and inside the constructor that kills
  `IQCC_Cloud(...)` (`computers.py:108`).
- **Rule for chronon:** every error from either service is
  `{"detail": "<human-readable, actionable>"}`, including 500s.

## Constructor side effects

`IQCC_Cloud(backend, api_token, url)` immediately makes these state calls:

| Call | Expected by the client | chronon serves | Source |
|---|---|---|---|
| `get_latest("summary")` | a `summary` dataset, or none | a seeded `summary` dataset | `computers.py:108-110` |
| `get_latest("key_qua")` | an ML-KEM public key record, or none; errors are caught | none (an empty list), so end-to-end encryption is off | `computers.py:113-133` |
| `get_latest("qmm_capabilities")` | base64 of a **pickle**, which the client unpickles; errors are *not* caught | none (an empty list), ever | `computers.py:136-141` |

`get_latest(t)` is `list(datatype=t, limit=1)` followed by `get(id)`. An
empty list returns `None` (`state.py:217-233`).

Observation: because the client unpickles `qmm_capabilities`, whoever can
write that dataset can run arbitrary code on every client that connects.
`key_qua` is similar: whoever writes it chooses the key clients encrypt to.
`push` is open to any `calibrator`, for any `type`. **Rule for chronon:** the
state service refuses writes of the reserved types `qmm_capabilities` and
`key_qua`, whatever the caller's role.

## `summary` dataset (`data` shape)

Read by `summary()` (`computers.py:650-745`), `run()` (`computers.py:294-310`)
and `_available_on_demand()` (`computers.py:630-648`):

```json
{
  "online": true,
  "description": "…",
  "state": {"<datatype>": {"description": "…"}},
  "ondemand": {"<workflow>": {"description": "…", "schema": {"…": "JSON Schema"}}},
  "runtime": {"visa": {}}
}
```

- `online`, `description`, `state`, `ondemand` and `runtime.visa` are all
  indexed without `.get`, so a missing key is a `KeyError`
  (`computers.py:664-668, 673, 639, 729`).
- If `"state"` is a key of `state`, `summary()` calls
  `get_latest("state").timestamp` (`computers.py:679-685`). With no `state`
  dataset that is `None.timestamp`, an `AttributeError`. **List `state` only
  once a `state` dataset exists.**
- `transpiler_target` in `state` triggers a native-gates table
  (`computers.py:689-727`). Optional.

## State service API

| Client method | Request | Response (200) | Source |
|---|---|---|---|
| `list` | `GET /{backend}/state/?skip&limit[&datatype][&producer]` | `[DatasetMeta]`, newest first | `state.py:33-95` |
| `get` | `GET /{backend}/state/{id}` | `Dataset`; the client warns if `backend` differs | `state.py:133-156` |
| `push` | `POST /{backend}/state/` body `{type, data, comment, parent_id}` | `Dataset`; restricted to role `calibrator` (docstring) | `state.py:97-131` |
| `trend` | `GET /{backend}/timeseries/?jsonpath&skip&limit[&datatype][&producer]` | `[{id, t, value}]`, newest first | `state.py:158-215` |
| `list_children` | `GET /{backend}/state/{id}/children?skip&limit[&type][&producer]` | `[DatasetMeta]` | `state.py:298-362` |

Notes:

- The filter is called `datatype` on `list` and `trend`, but **`type`** on
  `list_children` (`state.py:58` vs `state.py:325`).
- Trailing slashes matter: `/state/` and `/timeseries/` end in `/`;
  `/state/{id}` and `/children` don't.
- `trend(..., terminal_output=True)` plots only values whose
  `type(...)` is exactly `int` or `float` (`state.py:199`). A one-element list
  isn't plotted, so the server unwraps a single match to a scalar.
- Models (`interfaces.py:5-55`): `DatasetMeta` = `id, timestamp, type
  (≤60), comment (≤300), producer (≤60), parent_id (nullable)`. `Dataset`
  adds `backend (≤60)` and `data` (any JSON). `timestamp` is parsed by
  pendulum, so an ISO 8601 string is used.

## Task API

| Step | Request | Response | Source |
|---|---|---|---|
| Submit | `POST /task/{backend}/{workflow}` with the JSON payload | 200 `{"task_id": "…"}` | `computers.py:379-397` |
| Poll | `GET /task/{backend}/{task_id}`, about once per second | 200 `{"task_status": …, "task_result": "<JSON string>"}` | `computers.py:423-485` |
| Revoke | `DELETE /task/{backend}/{task_id}` on Ctrl-C | ignored | `computers.py:399-408` |

- `run()` validates the payload against `summary.ondemand[workflow].schema`
  **client-side** before sending (`computers.py:308-318`). Server-side
  validation only guards non-client callers.
- Polling loops while `task_status == "PENDING"` (`computers.py:430`), then
  while it is `RECEIVED` or `STARTED` (`computers.py:461`). Any other value
  ends the wait. `SUCCESS` is reported as success; anything else is printed
  in red (`computers.py:513-534`).
- `task_result` is passed to `json.loads` with a complex-number decoder
  (`computers.py:496`, `utilities.py:155-158`). It must **always be a valid
  JSON string encoding an object**, because `.get("encrypted")` is called on
  the result (`computers.py:499`). Use `"{}"` while not finished.
- A finished result is `{"result": {…}, "stdout": "…", "stderr": "…"}`.
  A non-empty `stderr` is printed as an error, and the strings
  `Execution timed out after` or `Timeout occured while waiting for result
  streams` make the client raise `TimeoutError` (`computers.py:515-527,
  626-627`).
- Complex numbers are encoded as `{"__type__": "complex", "data": [re, im]}`
  (`utilities.py:155-158`).
- `execute()` (QUA programs) posts to `/task/{backend}/qua`
  (`computers.py:259-267`). **chronon doesn't implement it.**

### Special result keys

With `terminal_output=True` the client pops these keys from `result` and
pretty-prints them (`computers.py:545-623`):

| Key | Shape | Source |
|---|---|---|
| `__total_python_runtime_seconds` | number (printed `%.3f`) | `computers.py:599-605` |
| `__qpu_execution_time_seconds` | number (printed `%.3f`) | `computers.py:606-612` |
| `__fridge_info` | `{"<name>": {"temperature_kelvin": float, "unix_timestamp": epoch}}` | `computers.py:613-620` |
| `__pre_hook`, `__sync_hook`, `__post_hook` | `{"stdout": str, "stderr": str}` | `computers.py:567-598` |

In chronon these values come from the simulated device and are labelled
as simulated.

## Tokens

| Behaviour | Source |
|---|---|
| The provider key pair is RSA 2048. The private key is PEM PKCS#8; the printed public key is PEM **PKCS#1**. | `cli.py:86-98` |
| Tokens are RS256 JWTs with payload `{"user_id", "qpu": {"<backend>": {"from", "to", "access": [roles], "project": [projects]}}, "expires"}`, where `expires == to`, all in Unix seconds. | `tokens.py:54-67` |
| There are no standard `exp`, `iat`, `kid` or `jti` claims. A verifier checks `expires` and the window by hand, and can't key revocation on a token ID. | `tokens.py:54-65` |
| The client reads its own roles by decoding **without verifying** the signature (display only; the server must verify). | `computers.py:143-159` |
| The role that may push datasets is `calibrator`. | `tokens.py:48`, `state.py:104-105` |
