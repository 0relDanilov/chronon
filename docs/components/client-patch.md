# Client patch

## What it is

`scripts/client_patch.py` is a module that every test, script or notebook
using the real `iqcc-cloud-client` imports first. It points the unmodified
client at a chronon site and makes it impossible for that process to reach
the upstream service.

## Why it's here

The client can't be pointed elsewhere by configuration alone:

- The task API URL is a constructor argument, but without an explicit token
  the constructor reads `~/.config/iqcc_cloud/config.toml`, whose `url` key
  overrides it.
- The state service URL is the default of a parameter on a **property**
  (`IQCC_Cloud.state`). Properties take no arguments, so the default is
  always used, and the constructor calls it three times before returning.

So the patch works on the class, before construction:

| Layer | What it does |
|---|---|
| `IQCC_Cloud.state` | replaced with a property returning a `StateService` bound to `CHRONON_STATE_URL` |
| `IQCC_Cloud.data` | replaced with a property that raises: the datastore isn't part of chronon |
| `IQCC_Cloud.__init__` | wrapped: requires `api_token`, refuses an upstream `url` and any `datastore` |
| `httpx.Client.send`, `httpx.AsyncClient.send` | guarded: any request whose host is the upstream domain or a subdomain raises `ForbiddenHostError` before it is sent |

The first three make the client *work* against chronon. The last one is a
backstop that makes a *mistake* fail loudly instead of sending a request.
It covers code paths the first three miss.

## How it fails

- **Not imported, or imported too late.** The guard is installed by the same
  import, so it can't protect a process that never imported the patch. If
  `IQCC_Cloud(...)` runs first, its constructor contacts the upstream state
  service before anything is patched. The guard only catches code paths
  missed by a patch that is loaded. Defences for a forgotten import are
  structural: entry points that use the client (contract-test `conftest.py`,
  `scripts/connect.py`) import the patch themselves; an `/etc/hosts`
  sinkhole on the laptop is the OS-level backstop.
- **Wrong or missing env vars.** The defaults are
  `https://api.chronon.test:8443` and `https://state.chronon.test:8443`.
  If the site isn't up, or `/etc/hosts` lacks the names, httpx raises
  `ConnectError`.
- **TLS.** The client verifies certificates. Against the local CA, set
  `SSL_CERT_FILE` to the CA bundle, or the handshake fails with
  `CERTIFICATE_VERIFY_FAILED`.
- **A future client version** could rename `state`, or call another HTTP
  library. The guard covers httpx only, and the unit tests pin the
  behaviour for 0.20.0.

## How to debug it

```bash
uv run --extra dev pytest -q tests/unit/test_client_patch.py -v
uv run --extra dev python -c "import sys; sys.path.insert(0, 'scripts'); \
  import client_patch as p; print(p.CHRONON_URL, p.CHRONON_STATE_URL)"
```
