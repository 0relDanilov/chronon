# Architecture

**Status:** rungs 1–3 exist: the local site (kind, Cilium, Argo CD, cert-manager, CNPG, Valkey, Argo Workflows, the Gateway) and the task and state services, which pass the contract test with the real client, and the simulated sim-qpu device with its fifo/fair queue. Only one site (`local`) exists, and the ARC backend is planned, not built. Each component below gets
its own page under *Components* once it's built; until then it's listed as
*planned*.

## Repository layout

| Path | Holds | Status |
|---|---|---|
| `src/chronon/auth.py` | RS256 provider-token verification: signature, window, roles, projects | exists |
| `src/chronon/contract.py` | Pydantic models mirroring the client (datasets, task status) | exists |
| `src/chronon/api/app.py` | task API: `/task/{backend}/{workflow}`, `/task/{backend}/{id}`, `DELETE`, `/metrics` | exists (inline `echo`; `t1` and `calibrate` through the device queue) |
| `src/chronon/state/app.py` | state service: `/{backend}/state/`, `/{backend}/state/{id}`, `/children`, `/{backend}/timeseries/` | exists |
| `src/chronon/queue.py` | Valkey queue, fifo and per-user fair modes | exists |
| `src/chronon/db.py`, `alembic/` | SQLAlchemy models for tasks and datasets; Alembic | exists |
| `src/chronon/{backends,tasks,web,schema,seed}.py` | backend registry and summaries; task hot/durable status; JSON errors and auth dependency; payload validation; the seed job | exists |
| `src/chronon/worker/` | sim-qpu device loop and its synthetic physics | exists |
| `src/chronon/arc/` | Stark-map chunk and merge CLIs | planned |
| `src/chronon/instrument/` | mock VISA-like instrument | planned |
| `tests/unit/` | unit tests: client patch, auth, schema, queue, physics | exists |
| `tests/contract/` | the real client against a running site | exists |
| `vendor/iqcc-cloud-client-0.20.0/` | the client sdist, read-only reference | exists |
| `scripts/client_patch.py` | points the real client at chronon, blocks upstream | exists |
| `scripts/bootstrap/local.sh` | the substrate: kind, Gateway API CRDs, Cilium, images, Argo CD, root app | exists |
| `scripts/mint_tokens.py` | demo tokens via the client's TokenGenerator | exists |
| `scripts/connect.py` | `connect(backend)`: the patched client in one call | exists |
| `scripts/rehearsal/` | the workshop rehearsal and overhead measurement | exists (50-student runs in both modes and a 10-run overhead measurement done) |
| `notebooks/demo.ipynb` | the demo: connect, summary, t1 with fit, calibrations and trend, an expired token's 401 | exists |
| `docker/Dockerfile` | images: `base` (exists) and `arc` (planned) targets | partly |
| `clusters/local/` | the local site: kind bootstrap, Argo CD apps, values, overlays | exists |
| `platform/` | shared components: cilium, cert-manager, pki, cnpg, postgres, valkey, argo-workflows, gateway | exists |
| `backends/sim-qpu/` | the device worker (replicas 1, Recreate) and the `t1-pod-per-run` WorkflowTemplate | exists |
| `backends/arc/` | the Stark-map backend | planned |
| `services/k8s/base/` | API and state Deployments, Services, HTTPRoutes, provider keys, seed hook | exists |
| `docs/` | this site (MkDocs Material) | exists |
| `.github/workflows/ci.yml` | gates; `base` image to GHCR; docs built and pushed to the `gh-pages` branch (GitHub Pages isn't enabled, so the site isn't published) | exists |
