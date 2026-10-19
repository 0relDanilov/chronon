# Repository layout

## What it is

One Python package (`chronon`, under `src/`) for every service and worker,
plus Kubernetes manifests laid out by **site** and **component**, plus docs.
The [architecture page](../architecture.md) lists every path and whether
it exists yet.

```
src/chronon/        one package: auth, contract, api, state, queue, db,
                    worker, arc, instrument
tests/unit/         fast tests, run by `make check`
tests/contract/     the real client against a running site (`make contract`)
scripts/            client_patch.py, and later bootstrap, rehearsal, tokens
vendor/             the client sdist: read-only reference
clusters/<site>/    what one site runs (bootstrap, Argo CD apps, values)
platform/<comp>/    shared component config reused by every site
backends/<name>/    per-backend manifests (sim-qpu, arc)
services/k8s/base/  the API and state services
docs/               this site
```

## Why it's built this way

- **One package, several entry points.** The API, state service and workers
  share models (`contract.py`), auth and DB code. One package means one
  image and one version, and a change to a shared model can't drift between
  services. The cost: every image carries all the code. The ARC dependencies
  are heavy, so they live behind an extra (`chronon[arc]`) and a second
  image target.
- **`src/` layout.** Tests import the *installed* package, not the working
  directory, so a missing file in the package shows up in tests rather than
  in production.
- **`clusters/<site>` over `platform/*`.** A site is a thin overlay; shared
  config is written once. A second site means a new `clusters/<site>/`, not
  a copy of everything.
- **`vendor/` is reference, not a dependency.** The client is installed from
  PyPI (pinned `==0.20.0` in the `dev` extra); `vendor/` holds the same
  sdist so its source can be read and cited line by line.

## How it fails

- **Missing extra.** `uv run pyright` without `--extra dev` fails with
  "pyright not found". The Makefile always passes `--extra dev`.
- **Domain gate.** `make check` fails if the upstream service domain appears
  outside the allow-listed files; the output names the file and line.
- **Manifest gate.** Any `kustomization.yaml` under `clusters/`,
  `platform/`, `backends/` or `services/k8s/base` is rendered and validated.
  A render or schema error fails `make check` (`pipefail` is on).

## How to debug it

```bash
make help                         # every target and what it does
uv sync --extra dev               # rebuild the environment from uv.lock
make check                        # run the gates; the first failing one stops
uv run --extra dev pytest -q tests/unit -k client_patch   # one test file
kustomize build platform/<comp> | kubeconform -strict -summary
```
