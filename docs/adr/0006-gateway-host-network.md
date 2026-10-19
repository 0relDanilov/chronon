# ADR-0006: Cilium Gateway API in host-network mode for the local site

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

Clients reach the site through one HTTPS endpoint, with TLS and HTTP/2 (the
client refuses HTTP/1.1). kind has no load balancer, and on Docker Desktop
for Mac the laptop can't route to the kind network's container IPs.

## Options

| Option | Where it breaks |
|---|---|
| **A. Cilium Gateway, Envoy on the node's host network, on nodes labelled `chronon.io/gateway=true`; kind maps 8443/8080 to the laptop** | One node is the entry point: no failover. Ports below 1024 would need `NET_BIND_SERVICE`, hence 8443/8080. |
| B. Gateway behind a `LoadBalancer` Service with Cilium LB-IPAM + L2 announcements | The right shape for a multi-node site on a flat L2 network. Here the IP lives on a network the Mac can't reach, so it still needs a port-forward. |
| C. BGP from Cilium to a top-of-rack router (ECMP) | The production shape for a real datacenter. No router here. |
| D. MetalLB, kube-vip, or NodePort + DNAT | Duplicate what Cilium already provides, or expose high ports and a second hop. |
| E. `kubectl port-forward` to the Gateway's Service | Works anywhere; one more manual process that dies silently. Kept as the kill-switch fallback. |

## Decision

A for the local site. `gatewayAPI.enableAlpn: true` so TLS listeners offer
h2; its chart default is `false`. B for a multi-node site, C for a
datacenter with a router.

## Consequences

- **Shortcut:** a single entry node, named as such in the docs.
- Backends get HTTP/1.1 from Envoy; only the edge speaks h2.

## Measured numbers

| What | Value | Command |
|---|---|---|
| TLS + ALPN through the Gateway | `ALPN: server accepted h2`, `HTTP/2 200` | `curl --http2 -v --cacert .certs/ca.pem https://api.chronon.test:8443/healthz` |
| With the client's transport settings | `HTTP/2 200` | `httpx.Client(http2=True, http1=False).get(...)` |
