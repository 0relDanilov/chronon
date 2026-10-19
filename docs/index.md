# chronon

chronon is an independent learning project: a staging slice of a
time-shared quantum-datacenter platform. It is not affiliated with, endorsed
by, or connected to IQCC or Quantum Machines, and it never contacts their
services. The "device" is a simulation.

**Status:** rungs 1–3. The local site runs (kind, Cilium, Argo CD and the
platform components), and the task and state services pass the contract test
with the unmodified client. The simulated device `sim-qpu` runs `t1` and `calibrate` with fifo or fair
scheduling; `notebooks/demo.ipynb` drives it with the real client.

- [Architecture](architecture.md): what lives where.
- [Client contract](contract.md): the API the unmodified client expects, with
  source references.
- [Build log](build-log.md): decisions, failures and measured numbers.
