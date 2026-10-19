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
