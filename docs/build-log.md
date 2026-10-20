# Build log

Timestamps are IDT (UTC+3). Newest entries at the bottom.

## Mon 19 Oct 2026: scaffold

**16:35 · Tooling on an Intel Mac.** `brew install uv kind kubeconform
kustomize` sat for over 10 minutes building `libgit2` and `xz` from source.
Root cause: Homebrew no longer ships prebuilt bottles for these formulae
on Intel macOS 15, so every dependency compiles locally. Fix: stopped
brew and installed the official release binaries into `~/.local/bin` after
checking each SHA-256 against the project's published checksums (uv 0.13.1,
kind v0.33.0, kubeconform v0.8.0, kustomize v5.8.3). Prevention: on this
machine, prefer upstream release binaries over brew for single-binary
tools.

**16:45 · Vendored the client.** `iqcc_cloud_client-0.20.0.tar.gz` from PyPI,
SHA-256 `a7c038b8…ef791a` matches PyPI's published digest. Extracted
unmodified into `vendor/iqcc-cloud-client-0.20.0/`, with its BSD-3 LICENSE.

**16:50 · The client's state URL can't be overridden by argument.**
`IQCC_Cloud.state` is a property with a default parameter (`computers.py:747`).
Properties take no arguments, so the default is always used, and the
constructor calls it three times. Decision: replace the property on the class
before construction (`scripts/client_patch.py`), plus a second layer that
guards `httpx.Client.send` against the upstream domain. Unit tests use
`httpx.MockTransport`, so even a broken guard can't reach the network.

**16:55 · Two holes in the planned `check` gate, found before first use.**
1. The manifest loop ended in `… | kubeconform … || true`. The `|| true`
   swallowed kubeconform's failure, so the gate could never fail. And
   without `pipefail`, a failing `kustomize build` piped empty input into
   kubeconform, which passes. Fix: `SHELL := /bin/bash`,
   `.SHELLFLAGS := -eu -o pipefail -c`, and an `if` instead of `&& … || true`.
2. The upstream-domain grep used `git grep`, which only searches tracked
   files. Before the first commit nothing is tracked, so it passed while
   checking nothing. Fix: `git grep --untracked`. On its first run it
   flagged `CLAUDE.md`, which names the domain in the rule forbidding it;
   CLAUDE.md is now on the allow-list.

**17:00 · pyright vs an upstream annotation.** The client annotates `url` as
`AnyUrl` but defaults it to a `str` and concatenates it as one
(`computers.py:44, 379`). We pass a `str` through `cast(Any, …)` with a
comment, rather than silencing the rule.

**Numbers**
- `uv lock`: 136 packages resolved in 5.3 s (`time uv lock`).
- `uv sync --extra dev`: 2 min 29 s wall, 379 s CPU. Some dependency built
  from source on Intel macOS (`time uv sync --extra dev`).
- `make check`: 10 unit tests pass in 1.8 s.

**20:02 · Correction found during the explain-back.** The first draft of the
client-patch page said that importing the patch "too late" would be caught
by the `send` guard. It wouldn't: the guard is installed by the same import,
so a process that never imports the patch, or constructs the client first,
is unprotected. The page now says so. The defences are structural (entry points
import the patch themselves) plus an OS-level hosts sinkhole. A second
finding from the same discussion: any `calibrator` could push a
`qmm_capabilities` dataset, which the client unpickles. The state service
will refuse writes of reserved types (`docs/contract.md`).

## Mon 19 Oct 2026: rung 1, the local site

**20:15 · argocd CLI skew.** Homebrew's `argocd` was 2.14.5, and the server is
v3.5.5. Installed the v3.5.5 binary (checksum verified) and ran `brew unlink
argocd` (reversible with `brew link argocd`), because `/usr/local/bin` comes
before `~/.local/bin` on PATH.

**20:18 · Two upstream facts checked before writing manifests.**
`helm show values cilium/cilium --version 1.20.3`: `enableAlpn: false` by
default, and `gatewayClass.create: auto` creates the GatewayClass only if the
Gateway API CRDs already exist, so the CRDs go first. Argo CD v3.5.5 docs
(`operator-manual/health.md`): Application health was removed in 1.8 and must
be restored for app-of-apps sync waves. The bootstrap patches `argocd-cm`.

**20:28 · CI rejected the workflow file.** Root cause: `hashFiles()` isn't
allowed in a job-level `if:` (only status functions are), so GitHub failed the
whole file before any job ran. Fix: drop the condition; the Dockerfile exists.

**20:29 · Committed an editor swap file** (`src/chronon/api/.app.py.swp`,
from vim). Untracked it, kept it on disk, and now ignore `*.swp`. Prevention:
look at `git status` before `git add -A`.

**20:30 · `kind load` failed for `valkey/valkey:8.1.10`:** `ctr: content
digest sha256:d2a1…: not found`. Root cause: Docker Desktop uses the
containerd image store (`docker info`: `io.containerd.snapshotter.v1`), which
keeps a multi-platform image's index but only the amd64 layers. kind exports
the index, and `ctr import --all-platforms` on the node looks for the missing
platforms. Images we build (`chronon:dev`) are single-platform and load fine.
Fix: the nodes pull the one Docker Hub image themselves (one image, one
replica, far under the anonymous rate limit). Rejected: retagging a locally
rebuilt single-platform copy under the upstream tag.

**20:36 · `valkey` and `chronon` OutOfSync right after "successfully synced".**
Root cause: fields the API server defaults (StatefulSet claim-template fields,
the HTTPRoute's default `PathPrefix /` match) aren't in git. Argo's diff for
SSA apps (structured-merge) reports them as drift. Fix: Server-Side Diff
(`controller.diff.server.side: "true"`, stable since v3.1), plus a controller
restart.

**20:45 · Sync-wave deadlock.** `chronon` (wave 1) stayed Progressing, so
the `gateway` app (wave 2) was never created. Root cause: an HTTPRoute is
Progressing until a Gateway accepts it, and its Gateway was in a later wave.
Fix: Gateway to wave 0 (it only needs the wave −1 certificate); routes stay
with their services. The in-flight root sync was pinned to the old revision,
so it needed `argocd app terminate-op root`. Side lesson: since Argo CD 3.0,
per-resource health isn't stored in `.status.resources`; use `argocd app get`.

**20:51 · Rung 1 DoD passes.** `curl --http2 -v --cacert .certs/ca.pem
https://api.chronon.test:8443/healthz` → `ALPN: server accepted h2`,
`SSL certificate verify ok`, `HTTP/2 200`. The client's transport
(`httpx.Client(http2=True, http1=False)`) also gets `HTTP/2 200`.
`argocd app list`: 8/8 Synced/Healthy. `cilium status`: OK. Hubble UI: HTTP
200 over a port-forward.

**Numbers**
- kind create (3 nodes, v1.37.0): 91 s; Cilium to `status OK`: 200 s
  (bootstrap stage stamps, `.logs/bootstrap-1.log`).
- Argo CD install and rollout: 109 s; full bootstrap re-run on an existing
  cluster: 156 s (`.logs/bootstrap-2.log`).
- `docker build --target base`: 1 min 19 s cold (`time docker build …`).

## Mon 19 Oct 2026: rung 2, API, state service and contract test (overnight)

**22:45 · CNPG's default image is PostgreSQL 18.** `pkg/versions/versions.go`
at v1.30.1: `DefaultImageName = …postgresql:18.6-system-trixie`. Pinned
`17.11-system-trixie` to keep the planned major version.

**22:47 · Provider key from the client's own CLI, kept out of `~`.**
`HOME=.tokens/provider-home iqcc-cloud provider --backend-name sim-qpu`: the
CLI is offline (RSA generation, `cli.py:86-126`) and writes
`~/.config/iqcc_cloud/config.toml`. Pointing `HOME` at the gitignored
`.tokens/` keeps the private key out of the real home directory; the PKCS#1
public key goes to `services/k8s/base/provider-keys/`.

**22:52 · pyright strict caught a runtime bug.** `jsonschema.validators` was
used after only `import jsonschema`, which doesn't load that submodule: an
`AttributeError` on the first submit. Moved validation to `chronon.schema`
with explicit imports.

**22:55 · An unsigned token would have been a 500.** The unit test for
`alg: none` failed: PyJWT raises `InvalidAlgorithmError`, which my code
didn't catch, so it would have reached the generic handler. Fix: also catch
PyJWT's base `InvalidTokenError` as a 401.

**23:00 · Argo CD couldn't build `services/k8s/base`:** `lstat
…/provider-keys: no such file or directory`. Root cause: the blanket `*.pem`
rule in `.gitignore` (meant for private keys) also excluded the public
provider key. Local `kustomize build` and `make check` passed, because the
file existed on disk. Fix: a narrow negation for
`services/k8s/base/provider-keys/*.pem`. Prevention: gates that render from a
clean checkout (`git stash -u` or a CI job) catch "works on my disk".

**23:04 · The seed PostSync hook didn't run on the automatic sync** that
followed the comparison-error fix; `argocd app sync chronon` ran it (Job
Complete in 6 s). Cause not established. To check after a rebuild:
`kubectl -n chronon get job chronon-seed`.

**23:05 · The client's `trend(terminal_output=True)` crashed inside the
client:** `AttributeError: module 'plotext' has no attribute 'date_form'`
(`state.py:205`). Root cause: the client requires `plotext>=5.3.2` with no
upper bound; uv resolved plotext 6.1.0, which no longer has `date_form`
(5.3.2 defines it in `_core.py:331`). A fresh install of the client today
hits this. Fix: `plotext>=5.3.2,<6` in our `dev` extra; the client is
unchanged.

**23:06:06 · First green contract run:** `make contract` → `11 passed in
1.82s`. The real client: constructor, `summary()` (with "Latest
calibration"), `run("echo")` with and without `terminal_output`, a
server-side 422, the out-of-window 401 with its window and current time, a
non-crashing constructor on an expired token, the calibrator-only push,
refusal of the reserved type `qmm_capabilities`, lineage (`push` →
`list_children` → `get_latest`), `trend()` returning scalars newest first and
plotting, JSON on every error, and polls served from Valkey.

**Numbers**
- Contract suite: 11 tests in 1.8 s (`make contract`).
- Unit suite: 24 tests in 5.4 s (`make check`).
- CNPG `chronon-db`, 2 instances, ready about 2.5 min after the first sync.
- Seed: 0.3 s (`kubectl -n chronon logs job/chronon-seed`).
- `chronon_db_reads_total{path="poll"}` = 3 after three contract runs, all
  from the deliberate lookup of a nonexistent task id. Polls of real tasks: 0.

## Mon 19 Oct 2026: rung 3, the simulated device (overnight)

**23:15 · The fit's uncertainty is honest.** Over 200 simulated T1 runs (true
T1 60 µs, 25 points × 500 shots), the fitted T1 fell within ±2σ of the truth
in 95.5% of runs, against 95.4% expected for a correct Gaussian error.
`curve_fit` takes 4.5 ms per fit. (One-off script, seed 7; the unit test
checks 3σ coverage ≥ 97/100.)

**23:18 · Queue unit tests run the real Lua.** `fakeredis[lua]` (lupa 2.8)
executes the same push/pop scripts as Valkey: fairness order, cap, fifo, mode
switch, revoke, crash requeue. 35 unit tests in 8.7 s.

**23:21 · PodSecurity check by server-side dry run.** `kubectl label
--dry-run=server ns chronon pod-security.kubernetes.io/enforce=restricted`
listed only `valkey-0` as violating (no seccomp, capabilities, runAsNonRoot,
allowPrivilegeEscalation). Fixed in its manifest. The enforce label itself
isn't applied yet.

**23:22 · The worker publishes its own summary at startup.** The summary is
defined in code (`chronon.backends`), so a new workflow arrives with a new
image, and git-triggered hooks don't see image-only changes. The worker runs the
idempotent seed when it starts: `published sim-qpu: summary`, then `sim-qpu
worker ready`.

**23:23 · First real-client T1 on the device:** `T1 = 59.7 ± 2.4 µs`; the
client printed the result, both timings and `mxc temperature = 0.0118 K
measured just now`, so the `__fridge_info` shape works. Wall 3.6 s (2.08 s
device + 0.7 s reconfigure/reset + 1 s poll granularity).

**23:23 · Three calibrations → three linked datasets** (2 → 10 → 11 → 12, T1
56.5 / 60.7 / 61.9 µs), and `qc.state.trend("$.qubits[0].t1",
terminal_output=True)` drew the client's own terminal plot. A student calling
`calibrate` got the 403 with its detail.

**23:30 · The notebook runs end to end** (nbclient: 4 code cells, 0 errors,
1 figure, 68 s mostly kernel start and the client's `qm` import). Its saved
outputs contain no tokens (`grep -c eyJ` → 0).

**23:35 · Cap and revoke on the live cluster.** Seven rapid submits by one
student in fair mode → `[200, 200, 200, 200, 200, 200, 429]`; the device had
already taken the first, and the cap counts queued runs only. Detail: "You
already have 5 runs queued on sim-qpu, the per-user limit in fair mode. …".
Revoking a queued run → `REVOKED` at once; the rest → `SUCCESS`.

**Numbers**
- Default `t1`: 1.387 s raw device time × 1.5 time scale = 2.08 s; plus 0.7 s
  reconfigure/reset (`physics.device_seconds`).
- Fair order, 20 greedy queued then 5 users × 1: the last of the 5 is served at
  pop 6; in fifo, after all 20 (`tests/unit/test_queue.py` plus a one-off
  check).

## Mon 19 Oct 2026: R5 scripts, smoke-tested (overnight)

**23:40 · argo CLI v4.1.5** installed from the release binary (checksum
verified), to match the server.

**23:42 · Rehearsal smoke runs, 5 students + greedy (20 runs).**
`make rehearsal MODE=fair USERS=5`: student wait p50/p95 9.5/15.4 s, last
student done 20.7 s after the cohort arrived, greedy share until then 32.8%,
52 greedy submissions refused with 429, 424 polls with 0 DB reads,
utilization 99.5%, student-01 on the real client OK. `MODE=fifo`: wait p50/p95
60.1/63.6 s, last student 68.4 s, greedy share 79.7%, 893 polls with 0 DB
reads. 77 s and 76 s wall. The 50-student runs are for Tuesday morning.

**23:47 · Overhead smoke run, 2 runs each** (`overhead.py --runs 2`):
submit→start warm 0.24 s vs pod 11.46 s; submit→done 2.85 s vs 17.34 s;
`argo submit`→`argo wait` 25.6 s. Laptop↔Docker VM skew +70 ms. Two runs
aren't a measurement; the 10-run result is for Tuesday.

## Tue 20 Oct 2026: the 50-student run and the overhead measurement

**12:56 · Health check.** `make contract` 11 passed; 10/10 Argo CD apps
Synced/Healthy; `chronon-seed` Complete. Nothing to fix.

**12:57 · 50-student run, fifo** (`make rehearsal MODE=fifo`): student wait
p50/p95/max 122.6/184.5/190.5 s; last student done 195.4 s after the cohort
arrived; greedy share until then 27.9%; 6,672 polls, 0 DB reads; utilization
99.5%; student-01 on the real client OK. 207 s wall.

**13:01 · 50-student run, fair** (`make rehearsal MODE=fair`): student wait
p50/p95/max 74.9/136.6/142.5 s; last student 147.4 s; greedy share 4.5%; 175
greedy submissions refused with 429; 4,742 polls, 0 DB reads; utilization
99.5%. 208 s wall.

**13:05 · Overhead, 10 runs each** (`overhead.py --runs 10`): submit→start
mean/p95 warm 0.08/0.11 s vs pod per run 3.47/3.97 s; submit→done 2.68/2.71 s
vs 9.43/10.07 s; `argo submit`→`argo wait` 20.46 s. Clock skew +65 ms. The
earlier 2-run smoke (11.46 s) included a cold first pod.
