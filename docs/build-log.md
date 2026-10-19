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
