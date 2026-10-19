#!/usr/bin/env bash
# Bootstrap the local site: the substrate that GitOps can't install itself.
#
#   kind -> Gateway API CRDs -> Cilium -> images -> Argo CD -> root Application
#
# Everything after the root Application is synced by Argo CD from git.
# Idempotent: re-running skips what already exists.
set -euo pipefail

CLUSTER=chronon
GATEWAY_API_VERSION=v1.6.3
CILIUM_VERSION=1.20.3
ARGOCD_VERSION=v3.5.5

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
START=$(date +%s)

stage() { printf '\n[%s +%ss] == %s\n' "$(date +%H:%M:%S)" \
  "$(($(date +%s) - START))" "$*"; }

stage "1/6 kind cluster"
if kind get clusters | grep -qx "$CLUSTER"; then
  echo "cluster $CLUSTER exists"
else
  kind create cluster --config clusters/local/bootstrap/kind.yaml
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

stage "2/6 Gateway API CRDs $GATEWAY_API_VERSION (before Cilium, so it creates its GatewayClass)"
kubectl apply --server-side -f \
  "https://github.com/kubernetes-sigs/gateway-api/releases/download/$GATEWAY_API_VERSION/standard-install.yaml"

stage "3/6 Cilium $CILIUM_VERSION"
helm repo add cilium https://helm.cilium.io >/dev/null 2>&1 || true
helm repo update cilium >/dev/null
helm upgrade --install cilium cilium/cilium --version "$CILIUM_VERSION" \
  --namespace kube-system \
  -f platform/cilium/values.yaml -f clusters/local/values/cilium.yaml
cilium status --wait --wait-duration 10m
kubectl wait --for=condition=Ready nodes --all --timeout=5m

stage "4/6 local images"
# Only images we build are kind-loaded. Upstream images (one Docker Hub image:
# valkey) are pulled by the nodes: `kind load` of a multi-platform image fails
# under Docker Desktop's containerd image store (see the build log).
make images-local

stage "5/6 Argo CD $ARGOCD_VERSION"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply --server-side -n argocd -f \
  "https://raw.githubusercontent.com/argoproj/argo-cd/$ARGOCD_VERSION/manifests/install.yaml"
# Restore health for Application resources, so the root app's sync waves wait
# for each child app to be Healthy (removed upstream in Argo CD 1.8).
kubectl -n argocd patch configmap argocd-cm --type merge \
  --patch-file clusters/local/bootstrap/argocd-cm-patch.yaml
# Server-side diff, so API-server defaults don't show as permanent drift.
kubectl -n argocd patch configmap argocd-cmd-params-cm --type merge \
  --patch-file clusters/local/bootstrap/argocd-cmd-params-patch.yaml
kubectl -n argocd rollout status deploy/argocd-server --timeout=5m
kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=5m
kubectl -n argocd rollout status statefulset/argocd-application-controller \
  --timeout=5m
# Restart so the controller is certain to run with the patched settings.
kubectl -n argocd rollout restart statefulset/argocd-application-controller
kubectl -n argocd rollout status statefulset/argocd-application-controller \
  --timeout=5m

stage "6/6 root Application (Argo CD takes over from here)"
kubectl apply -f clusters/local/bootstrap/root-app.yaml

stage "done in $(($(date +%s) - START)) s; watch: kubectl -n argocd get applications -w"
