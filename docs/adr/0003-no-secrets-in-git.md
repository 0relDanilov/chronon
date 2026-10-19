# ADR-0003: No secrets in git this round

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

GitOps wants everything in git, and secrets can't go there in plain text.
Today nothing needs one: CloudNativePG generates its own database
credentials in-cluster, the CA is minted in-cluster by cert-manager, and the
token provider's private key stays on the operator's laptop.

## Options

| Option | Where it breaks |
|---|---|
| **A. No secrets in git until one is needed** | The day a real external credential appears (a registry token, an SSO client secret), a mechanism has to be chosen under time pressure. |
| B. Sealed Secrets (controller key decrypts in-cluster) | The controller's private key is per cluster: back it up or bring your own, or a rebuilt site can't decrypt its own repo. |
| C. SOPS + age through an Argo CD plugin | Readable diffs and per-file keys, but one more moving part to bootstrap before Argo CD can sync anything. |
| D. External Secrets Operator | Needs a secret backend (Vault, a cloud KMS) that a lab site may not have. |

## Decision

A. When a secret appears, B with a bring-your-own key shared by every
site, so a rebuilt cluster can decrypt immediately.

## Consequences

- `make seal` exists and says so instead of pretending.
- `.gitignore` excludes `.tokens/`, `.certs/`, `*.pem` and `*.key`.

## Measured numbers

None yet.
