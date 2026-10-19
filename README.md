# chronon

chronon is an independent learning project built over two days to understand the shape of a time-shared quantum-datacenter platform: a GitOps-managed Kubernetes platform, laid out for multiple sites, serving a simulated time-shared device and a parallel classical-compute backend to many users through the public `iqcc-cloud-client` contract. It is not affiliated with, endorsed by, or connected to IQCC or Quantum Machines; it never contacts their services. The "device" is a simulation. See `docs/built-with-claude-code.md` for how it was built and verified.

## Status

Rungs 1–3: the local site runs on kind, with Cilium (kube-proxy replacement,
Gateway API with TLS and HTTP/2, Hubble) and Argo CD syncing cert-manager,
CloudNativePG, Valkey and Argo Workflows from git. The task API and state
service pass the contract test with the unmodified client (`make contract`).
The simulated device `sim-qpu` runs `t1` and `calibrate` with fifo or fair
scheduling; `notebooks/demo.ipynb` drives it with the real client. `docs/build-log.md`
records progress as it happens.

## Quick start

```bash
uv sync --extra dev   # Python 3.12 environment, including the real client
make check            # format, lint, types, unit tests, manifest and domain gates
make help             # all targets
make up-local         # kind + Cilium + Argo CD; then Argo CD syncs the rest
make ca               # export the site's CA to .certs/ca.pem
curl --http2 --cacert .certs/ca.pem https://api.chronon.test:8443/healthz
```

The local hostnames need `/etc/hosts` entries:
`127.0.0.1 api.chronon.test state.chronon.test argocd.chronon.test hubble.chronon.test`.

## Layout

See [`docs/components/repo-layout.md`](docs/components/repo-layout.md).

## Documentation

- [`docs/contract.md`](docs/contract.md): the task/state API as the client
  uses it, with file and line references into `vendor/`.
- [`docs/build-log.md`](docs/build-log.md): decisions, failures and numbers.

## Third-party code

`vendor/iqcc-cloud-client-0.20.0/` is the unmodified sdist of the public
`iqcc-cloud-client` package from PyPI, kept as read-only reference under its
BSD-3-Clause license (`vendor/iqcc-cloud-client-0.20.0/LICENSE`).
