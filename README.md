# chronon

chronon is an independent learning project built over two days to understand the shape of a time-shared quantum-datacenter platform: a GitOps-managed Kubernetes platform, laid out for multiple sites, serving a simulated time-shared device and a parallel classical-compute backend to many users through the public `iqcc-cloud-client` contract. It is not affiliated with, endorsed by, or connected to IQCC or Quantum Machines; it never contacts their services. The "device" is a simulation. See `docs/built-with-claude-code.md` for how it was built and verified.

## Status

Scaffold only. The repository layout, static gates and the client contract
summary exist; no services or cluster manifests do yet. `docs/build-log.md`
records progress as it happens.

## Quick start

```bash
uv sync --extra dev   # Python 3.12 environment, including the real client
make check            # format, lint, types, unit tests, manifest and domain gates
make help             # all targets
```

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
