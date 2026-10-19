# Architecture

**Status:** only the repository scaffold exists. Each component below gets
its own page under *Components* once it's built; until then it's listed as
*planned*.

## Repository layout

| Path | Holds | Status |
|---|---|---|
| `src/chronon/auth.py` | RS256 provider-token verification: signature, window, roles, projects | planned |
| `src/chronon/contract.py` | Pydantic models mirroring the client (datasets, task status) | planned |
| `src/chronon/api/app.py` | task API: `/task/{backend}/{workflow}`, `/task/{backend}/{id}`, `DELETE`, `/metrics` | planned |
| `src/chronon/state/app.py` | state service: `/{backend}/state/`, `/{backend}/state/{id}`, `/children`, `/{backend}/timeseries/` | planned |
| `src/chronon/queue.py` | Valkey queue, fifo and per-user fair modes | planned |
| `src/chronon/db.py` | SQLAlchemy models for tasks and datasets; Alembic | planned |
| `src/chronon/worker/` | sim-qpu device loop and its synthetic physics | planned |
| `src/chronon/arc/` | Stark-map chunk and merge CLIs | planned |
| `src/chronon/instrument/` | mock VISA-like instrument | planned |
| `tests/unit/` | unit tests | exists (client patch) |
| `tests/contract/` | the real client against a running site | planned |
| `vendor/iqcc-cloud-client-0.20.0/` | the client sdist, read-only reference | exists |
| `scripts/client_patch.py` | points the real client at chronon, blocks upstream | exists |
| `scripts/` (others) | connect helper, rehearsal, token minting, bootstrap | planned |
| `docker/Dockerfile` | images: `base` and `arc` targets | planned |
| `clusters/local/` | the local site: kind bootstrap, Argo CD apps, values | planned |
| `platform/` | shared components: cilium, cert-manager, cnpg, valkey, argo-workflows, gateway | planned |
| `backends/sim-qpu/`, `backends/arc/` | per-backend manifests | planned |
| `services/k8s/base/` | API and state Deployments, Services, HTTPRoutes | planned |
| `docs/` | this site (MkDocs Material) | exists |
| `.github/workflows/ci.yml` | gates, images, docs deploy | exists |
