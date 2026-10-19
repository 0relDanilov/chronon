# ADR-0007: A private CA in cert-manager for the local site

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

The client verifies TLS certificates. The local site has no public DNS, so
public CAs can't issue for `*.chronon.test`.

## Options

| Option | Where it breaks |
|---|---|
| **A. cert-manager: self-signed issuer → CA certificate → CA issuer → one explicit serving Certificate; clients trust the exported CA** | Every rebuild mints a new CA; clients must re-export it (`make ca`). |
| B. mkcert on the laptop | The CA lives outside the cluster and outside git; a rebuilt site can't recreate it, and the setup is per laptop. |
| C. A self-signed certificate per service | Every client trusts every leaf; rotation means touching every client. |
| D. Let's Encrypt (HTTP-01 through the Gateway, or DNS-01) | Needs a public name. The right choice for a public site, not for `.test`. |

## Decision

A for the local site; D (HTTP-01 through the Gateway) for a public one.
Usages are explicit: the CA has `cert sign, crl sign, digital signature, key
encipherment`; the leaf has `server auth, digital signature, key
encipherment`. Stricter TLS stacks reject a CA without signing usages or a
leaf without `serverAuth` (for example Python 3.13's default
`VERIFY_X509_STRICT`). The client environment here is Python 3.12; this
has **not** been tested against 3.13 yet.

## Consequences

- One trust anchor: `SSL_CERT_FILE=.certs/ca.pem`.
- No cert-manager Gateway shim: the listener names its Secret, visible in git.

## Measured numbers

| What | Value | Command |
|---|---|---|
| Chain verifies end to end | `SSL certificate verify ok`, issuer `CN=chronon local CA` | `curl -v --cacert .certs/ca.pem https://api.chronon.test:8443/healthz` |
