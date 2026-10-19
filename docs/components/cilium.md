# Cilium (CNI, kube-proxy replacement, Gateway, Hubble)

## What it is

Cilium 1.20.3 is the cluster's network. It gives every pod an address
(CNI), load-balances Services in eBPF instead of kube-proxy's iptables
chains (`kubeProxyReplacement: true`), runs the Envoy that implements the
Gateway API, and records every flow for Hubble.

## Why it's here, and why it's installed by script

Nothing schedules without a CNI: pods, Argo CD's included, never get an
address. So Cilium is part of the **substrate** that
`scripts/bootstrap/local.sh` installs with Helm, before Argo CD exists
([ADR-0002](../adr/0002-gitops-topology.md)). Its values live in git anyway
(`platform/cilium/values.yaml` plus `clusters/local/values/cilium.yaml`), so
the install is still reproducible from the repo.

Choices that matter:

| Setting | Why |
|---|---|
| `k8sServiceHost: chronon-control-plane`, port 6443 | With no kube-proxy, nothing translates the `kubernetes` Service IP until Cilium runs, so Cilium needs the API server's real address. |
| `gatewayAPI.enableAlpn: true` | Defaults to false. Without it TLS listeners offer only HTTP/1.1, and the client refuses HTTP/1.1. |
| `gatewayAPI.hostNetwork` on nodes labelled `chronon.io/gateway=true` | kind has no load balancer; Envoy binds 8443/8080 on the control-plane node, and kind maps them to the laptop ([ADR-0006](../adr/0006-gateway-host-network.md)). **Shortcut.** |
| Gateway API CRDs installed **before** Cilium | `gatewayClass.create: auto` creates the `cilium` GatewayClass only if the CRDs already exist. |

## How it fails

- **Nodes `NotReady` right after `kind create`.** That's expected until
  Cilium is up; the bootstrap waits for it.
- **No `cilium` GatewayClass.** The CRDs were installed after Cilium. Re-run
  the Helm upgrade, or restart the operator.
- **`curl` connects but gets HTTP/1.1, or the client fails with a protocol
  error.** ALPN is off (`cilium config view | grep alpn`).
- **Connection refused on :8443.** No Gateway, or no listener on that port, or
  the Envoy DaemonSet isn't running on the labelled node.

## How to debug it

```bash
cilium status                                    # agents, operator, Envoy, Hubble
cilium config view | grep -E 'kube-proxy-replacement|gateway-api'
kubectl get gatewayclass,gateway -A               # Accepted / Programmed conditions
kubectl -n gateway describe gateway chronon
kubectl -n kube-system port-forward svc/hubble-ui 12000:80   # http://localhost:12000
kubectl -n kube-system exec ds/cilium -c cilium-agent -- \
  hubble observe --verdict DROPPED --last 20      # flows dropped on that node
```
