# Architecture

**Status:** rungs 1–2 exist: the local site (kind, Cilium, Argo CD, cert-manager, CNPG, Valkey, Argo Workflows, the Gateway) and the task and state services, which pass the contract test with the real client. Each component below gets
its own page under *Components* once it's built; until then it's listed as
*planned*.

## Repository layout

| Path | Holds | Status |
|---|---|---|
| `src/chronon/auth.py` | RS256 provider-token verification: signature, window, roles, projects | exists |
| `src/chronon/contract.py` | Pydantic models mirroring the client (datasets, task status) | exists |
| `src/chronon/api/app.py` | task API: `/task/{backend}/{workflow}`, `/task/{backend}/{id}`, `DELETE`, `/metrics` | exists (inline `echo`; device queue in rung 3) |
| `src/chronon/state/app.py` | state service: `/{backend}/state/`, `/{backend}/state/{id}`, `/children`, `/{backend}/timeseries/` | exists |
| `src/chronon/queue.py` | Valkey queue, fifo and per-user fair modes | planned |
| `src/chronon/db.py`, `alembic/` | SQLAlchemy models for tasks and datasets; Alembic | exists |
| `src/chronon/{backends,tasks,web,schema,seed}.py` | backend registry and summaries; task hot/durable status; JSON errors and auth dependency; payload validation; the seed job | exists |
| `src/chronon/worker/` | sim-qpu device loop and its synthetic physics | planned |
| `src/chronon/arc/` | Stark-map chunk and merge CLIs | planned |
| `src/chronon/instrument/` | mock VISA-like instrument | planned |
| `tests/unit/` | unit tests: client patch, auth, schema | exists |
| `tests/contract/` | the real client against a running site | exists |
| `vendor/iqcc-cloud-client-0.20.0/` | the client sdist, read-only reference | exists |
| `scripts/client_patch.py` | points the real client at chronon, blocks upstream | exists |
| `scripts/bootstrap/local.sh` | the substrate: kind, Gateway API CRDs, Cilium, images, Argo CD, root app | exists |
| `scripts/mint_tokens.py` | demo tokens via the client's TokenGenerator | exists |
| `scripts/` (others) | connect helper, rehearsal | planned |
| `docker/Dockerfile` | images: `base` (exists) and `arc` (planned) targets | partly |
| `clusters/local/` | the local site: kind bootstrap, Argo CD apps, values, overlays | exists |
| `platform/` | shared components: cilium, cert-manager, pki, cnpg, postgres, valkey, argo-workflows, gateway | exists |
| `backends/sim-qpu/`, `backends/arc/` | per-backend manifests | planned |
| `services/k8s/base/` | API and state Deployments, Services, HTTPRoutes, provider keys, seed hook | exists |
| `docs/` | this site (MkDocs Material) | exists |
| `.github/workflows/ci.yml` | gates, images, docs deploy | exists |
