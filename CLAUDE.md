# CLAUDE.md — chronon

chronon is an independent learning project: a staging slice of a time-shared
quantum-datacenter platform. It is not affiliated with IQCC or Quantum Machines.
Orel owns every decision; you write most of the code. Orel must be able to
explain and defend every line in a technical review. Work accordingly.

## Hard rules
1. NEVER send a request to any `*.i-qcc.com` host (cloud, state, ds, auth,
   docs). Never try to obtain or use an IQCC token. Reading the vendored
   PyPI sources in `vendor/` is fine. Any test or script that uses the real
   `iqcc_cloud_client` MUST import `scripts/client_patch.py` first, which
   patches `IQCC_Cloud.state` before construction and points `url` at our host.
   Grep for `i-qcc.com` before every commit; the only allowed occurrences are
   in `vendor/` and in docs explaining the patch.
2. No IQCC/QM names, logos, or look-alike UI anywhere in code, docs or UI.
   The project is "chronon"; backends are "sim-qpu" and "arc"; the site is
   "local" (a second site is future work).
3. Never describe something as built when it isn't. Docs describe exactly
   what exists. Label synthetic data as synthetic. Experiments that are not
   wired in are labelled "experiment".
4. Code freeze: Tuesday 11:30 IDT. After that only fixes to demo paths, with
   Orel's explicit go.

## How we work
- Options first. For any architectural choice (storage, queueing, networking,
  auth, scheduling, layout, images), propose 2–3 options, each with trade-offs
  and "where it breaks", then STOP and wait for Orel's choice. Do not start
  coding an option he has not picked. When a prompt lists decisions as already
  made, don't re-ask them; stop only if one of them cannot work, and say why.
- Small diffs. One component or one behaviour per step. State the files you
  will create/change before writing. Prefer editing to rewriting.
- ADR per decision in `docs/adr/NNNN-title.md`: Context / Options (each with
  where it breaks) / Decision / Consequences / Measured numbers (with the
  command that produced them). One page max.
- Explain after building. After each component, write
  `docs/components/<name>.md` in plain language: what it is, why it is here,
  how it fails, how to debug it (exact commands). Then ask Orel three
  questions to check he can explain it back, and grade his answers honestly;
  fill gaps with one paragraph each.
- Build log. Append to `docs/build-log.md` with timestamps: decisions,
  surprises, failures, fixes, every measured number and its command.
- Verification gates before "done": run `make check` (ruff format --check,
  ruff check, pyright, pytest tests/unit, kubeconform on rendered manifests
  for every clusters/*/ and platform/*/ target). For anything touching the
  API or state service also run `make contract`. Paste the output. If a gate
  fails: fix it or report it; never claim done.
- Timeboxes are real. If a step runs past the timebox Orel gave, stop, write
  what works and what doesn't, and propose the kill-switch path.
- Honesty over polish. Shortcuts (host-network gateway, single node, stubs)
  are named as shortcuts in the docs and the relevant ADR.

## Stack and conventions
- Python 3.12, uv, hatchling. ruff (line-length 80), Google docstrings,
  pyright strict on src/chronon. pytest; httpx for tests. Type everything.
- Services: FastAPI + uvicorn, HTTP/1.1 behind the gateway. Queue/hot state:
  Valkey via redis-py. DB: PostgreSQL via CloudNativePG, SQLAlchemy 2 + Alembic,
  JSONB for datasets, GIN jsonb_path_ops index. Errors are always
  {"detail": "<human-readable, actionable>"} with the right status code.
- Kubernetes: kustomize; clusters/<site>/ overlays over platform/* and
  backends/*. Argo CD app-of-apps with sync-wave annotations; Cilium and
  Argo CD are bootstrap-managed. No secrets in git (none are needed yet).
  Official upstream images only (no Bitnami). Pin chart and image versions
  explicitly; ServerSideApply for large CRDs (Argo Workflows, CNPG).
- Images: one Dockerfile, two targets (base, arc). Locally they are built for
  the host architecture and loaded with `kind load docker-image` as
  chronon:dev / chronon-arc:dev with imagePullPolicy IfNotPresent (never
  :latest). CI builds amd64 images to ghcr.io/0reldanilov/ for later sites.
- Contract: docs/contract.md is the source of truth for the task/state API as
  the client uses it. When in doubt, read vendor/iqcc-cloud-client-0.20.0/
  (computers.py, state.py, tokens.py) — read-only.

## Commands
- make up-local / make down-local — kind + Cilium + Argo CD bootstrap (clusters/local)
- make check — static gates; make contract — real client against CHRONON_URL
- make rehearsal MODE=fifo|fair — the 50-student rehearsal
- make images-local — build images for the host arch and kind-load them
- make docs — mkdocs serve; make tokens — mint demo tokens

## Definition of done (every rung)
1. Gates green; contract test green where applicable.
2. Component explanation written; Orel has explained it back; gaps filled.
3. ADR(s) written; build log updated with numbers.
4. The demo path works from a clean checkout (no uncommitted hacks).
