# Architecture

**Status:** the local site (rung 1) exists: kind, Cilium, Argo CD, cert-manager, the CNPG operator, Valkey, Argo Workflows, and a Gateway serving `/healthz`. Each component below gets
its own page under *Components* once it's built; until then it's listed as
*planned*.

## Repository layout

| Path | Holds | Status |
|---|---|---|
| `src/chronon/auth.py` | RS256 provider-token verification: signature, window, roles, projects | planned |
| `src/chronon/contract.py` | Pydantic models mirroring the client (datasets, task status) | planned |
| `src/chronon/api/app.py` | task API: `/task/{backend}/{workflow}`, `/task/{backend}/{id}`, `DELETE`, `/metrics` | `/healthz` only |
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
| `scripts/bootstrap/local.sh` | the substrate: kind, Gateway API CRDs, Cilium, images, Argo CD, root app | exists |
| `scripts/` (others) | connect helper, rehearsal, token minting | planned |
| `docker/Dockerfile` | images: `base` (exists) and `arc` (planned) targets | partly |
| `clusters/local/` | the local site: kind bootstrap, Argo CD apps, values, overlays | exists |
| `platform/` | shared components: cilium, cert-manager, pki, cnpg, valkey, argo-workflows, gateway | exists |
| `backends/sim-qpu/`, `backends/arc/` | per-backend manifests | planned |
| `services/k8s/base/` | API and state Deployments, Services, HTTPRoutes | API only |
| `docs/` | this site (MkDocs Material) | exists |
| `.github/workflows/ci.yml` | gates, images, docs deploy | exists |
