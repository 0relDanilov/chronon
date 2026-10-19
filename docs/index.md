# chronon

chronon is an independent learning project: a staging slice of a
time-shared quantum-datacenter platform. It is not affiliated with, endorsed
by, or connected to IQCC or Quantum Machines, and it never contacts their
services. The "device" is a simulation.

**Status:** rungs 1–2. The local site runs (kind, Cilium, Argo CD and the
platform components), and the task and state services pass the contract test
with the unmodified client. The simulated device (rung 3) isn't built yet.

- [Architecture](architecture.md): what lives where.
- [Client contract](contract.md): the API the unmodified client expects, with
  source references.
- [Build log](build-log.md): decisions, failures and measured numbers.
