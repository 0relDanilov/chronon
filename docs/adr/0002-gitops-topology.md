# ADR-0002: One Argo CD per site; Cilium and Argo CD are bootstrap-managed

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

The platform is meant to run at more than one site from the same repo. The
CNI and the GitOps engine are special: pods can't get addresses before the
CNI exists, and Argo CD is itself pods.

## Options

| Option | Where it breaks |
|---|---|
| **A. One Argo CD per site, same repo, `clusters/<site>/` app-of-apps. CNI and Argo CD installed by a script.** | Cilium and Argo CD upgrades are a scripted step, not a commit; drift in those two isn't auto-healed. |
| B. Hub-and-spoke: one central Argo CD managing every site | The WAN link to the hub becomes a dependency for every site's changes; one compromised hub reaches every site. |
| C. ApplicationSet with a cluster generator | Good for many similar clusters; adds a templating layer that hides what a single site runs. Worth it at 5+ sites, not 1–2. |
| D. Argo CD also manages Cilium after bootstrap (adoption) | A bad Cilium commit auto-syncs, breaks pod networking, including Argo CD's, and Argo can no longer roll it back. |

## Decision

A. `scripts/bootstrap/local.sh` runs kind → Gateway API CRDs → Cilium →
images → Argo CD → the root Application. Everything else is an Application,
ordered by sync waves (−2 cert-manager; −1 CNPG operator, PKI;
0 Valkey, Argo Workflows, Gateway; 1 chronon services).

## Consequences

- A site is rebuilt by `make down-local && make up-local`. No state lives
  outside git, except the CA, which is minted fresh (ADR-0007).
- App-of-apps waves need the `argoproj.io/Application` health check restored
  in `argocd-cm`; the bootstrap does it.
- Argo CD reads GitHub, so every change is a push.

## Measured numbers

| What | Value | Command |
|---|---|---|
| kind cluster (3 nodes) created | 91 s | `scripts/bootstrap/local.sh` stage stamps (`.logs/bootstrap-1.log`) |
| Cilium installed and `cilium status --wait` OK | 200 s | same, stage 3 → 4 |
| Argo CD installed and rolled out | 109 s | same (`bootstrap-2.log`), stage 5 → 6 |
| Full rebuild from git | *to be measured Tue 07:30* | `time make down-local && time make up-local` |
