# ADR-0012: Token semantics and the in-cluster write path

**Status:** accepted (draft) · Mon 19 Oct 2026

## Context

Tokens are minted by a backend provider with the client's `TokenGenerator`:
RS256, payload `{user_id, qpu: {<backend>: {from, to, access, project}},
expires}`. They carry no `exp`, `iat`, `kid` or `jti`. The provider shares
only a PKCS#1 public key.

## Options

| Option | Where it breaks |
|---|---|
| **A. Verify as the tokens are: RS256 only, try every key registered for the backend, check `expires` and the window by hand** | Without `kid`, verification cost grows with the number of keys; without `jti`, one token can't be revoked, only the key. |
| B. Require `exp`/`kid`/`jti` | Standard tooling works, but it needs a client change; existing tokens would stop working. |
| C. Revocation by token hash (deny-list in Valkey) | Works with today's tokens; the list must outlive the longest window. A stretch, not built. |

For in-cluster writers (worker, seed job, later the ARC merge step):

| Option | Where it breaks |
|---|---|
| **A. Write through the chronon library, straight to Postgres/Valkey** | Every writer needs database credentials; the boundary is the library, not an API. |
| B. An `/internal` API with service tokens | A clean boundary and audit trail, but one more token type to mint, rotate and protect. The production option. |

## Decision

A for both. `algorithms=["RS256"]` is pinned, so `alg: none` and HS256
tokens are rejected (a unit test covers it). Every PyJWT rejection is a 401,
never a 500. Window errors state the window, the current time, and how far
off it is.

## Consequences

- Rotating a provider key means adding a second PEM to the ConfigMap, then
  removing the old one; both work in between.
- A leaked token is valid until its window closes.

## Measured numbers

| What | Value | Command |
|---|---|---|
| Out-of-window token | 401, `Your access window for backend sim-qpu is … → …; it is now …, so it closed 2 h 0 min ago. …` | `make contract` (`test_expired_window_is_a_readable_401`) |
