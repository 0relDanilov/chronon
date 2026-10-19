# Argo CD (GitOps)

## What it is

Argo CD v3.5.5 keeps the cluster equal to `main`. One **root Application**
(`clusters/local/bootstrap/root-app.yaml`) points at `clusters/local/apps/`,
which holds one Application per component. That's the *app-of-apps*
pattern. Every change after bootstrap is a git commit.

## Why it's built this way

- **Substrate below GitOps.** Argo CD can't install the network it runs on,
  or itself, so the bootstrap script installs Cilium and Argo CD
  ([ADR-0002](../adr/0002-gitops-topology.md)).
- **Sync waves order the platform:**

  | Wave | Applications |
  |---|---|
  | −2 | cert-manager (and its CRDs) |
  | −1 | CNPG operator, PKI (issuers and the serving Certificate) |
  | 0 | Valkey, Argo Workflows, Gateway |
  | 1 | chronon services, each with its own HTTPRoute |

- **Waves only wait if Applications have health.** Argo CD removed health
  assessment for `Application` resources in 1.8. Without it, wave −1 would
  apply `ClusterIssuer`s before cert-manager's CRDs exist. The bootstrap
  restores it in `argocd-cm`.
- **Server-Side Apply and Server-Side Diff.** SSA avoids the size limit
  of client-side apply's annotation on large CRDs. Server-side diff (in
  `argocd-cmd-params-cm`) lets the API server compute the predicted state, so
  fields it defaults don't show up as permanent drift.
- **Helm charts with values from git:** each chart Application has two
  sources, the chart repo and this repo (`ref: values`), so values files are
  versioned with everything else.

## How it fails

- **An app stuck `Progressing` holds back every later wave.** Example from
  this build: an HTTPRoute in wave 1 waited for a Gateway in wave 2, a
  deadlock. Fix: the Gateway moved to wave 0.
- **`OutOfSync` right after a successful sync.** The live object has
  defaulted fields that git doesn't. Server-side diff fixes it.
- **A running sync uses the revision it started with.** Pushing a fix
  doesn't unstick it; terminate the operation first.
- **Argo CD reads GitHub, not the laptop.** Unpushed commits don't exist
  for the cluster.

## How to debug it

```bash
kubectl config set-context --current --namespace=argocd
argocd login --core                       # CLI straight to the API, no server login
argocd app list
argocd app get <app>                      # per-resource sync and health
argocd app terminate-op root              # unstick a sync waiting on an old revision
kubectl -n argocd annotate application <app> argocd.argoproj.io/refresh=hard --overwrite
kubectl -n argocd logs sts/argocd-application-controller --since=5m | grep <app>
kubectl -n argocd port-forward svc/argocd-server 8081:443   # UI at https://localhost:8081
argocd admin initial-password -n argocd   # UI password for user admin
```

Note: since Argo CD 3.0, per-resource health is no longer stored in the
Application's `.status.resources`. Use `argocd app get` or the UI.
