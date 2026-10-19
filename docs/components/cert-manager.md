# cert-manager (the site's private CA)

## What it is

cert-manager v1.21.2 mints and renews certificates from Kubernetes
resources. The local site has its own small PKI (public-key
infrastructure), all in git:

```
ClusterIssuer selfsigned
  └─ signs Certificate chronon-ca (isCA, 1 year)  → Secret cert-manager/chronon-ca
       └─ backs ClusterIssuer chronon-ca
            └─ signs Certificate chronon-tls (90 days) → Secret gateway/chronon-tls
                 └─ referenced by the Gateway's HTTPS listener (8443)
```

The serving certificate covers `api`, `state`, `argocd` and
`hubble.chronon.test`.

## Why it's built this way

- **A CA, not self-signed leaves.** Clients trust one file (`make ca` writes
  `.certs/ca.pem`); leaves rotate without touching clients
  ([ADR-0007](../adr/0007-local-ca.md)).
- **Usages are explicit.** CA: `cert sign, crl sign, digital signature, key
  encipherment`; leaf: `server auth, digital signature, key encipherment`.
  Stricter TLS stacks (Python 3.13's default `VERIFY_X509_STRICT`) reject a
  CA without signing usages, or a leaf without `serverAuth`.
- **One explicit Certificate, no Gateway shim.** The listener names its
  Secret directly, so what's served is visible in git.
- **Inside the cluster.** A rebuilt site recreates its PKI from git. The cost:
  every rebuild mints a **new** CA, so re-run `make ca` after `make up-local`.

## How it fails

- **`CERTIFICATE_VERIFY_FAILED` in the client or curl.** Stale `ca.pem` from
  an earlier cluster: run `make ca` and set `SSL_CERT_FILE=.certs/ca.pem`.
- **Certificate stuck `Ready=False`.** The issuer isn't ready (its Secret
  is missing), or cert-manager's webhook isn't up yet.
- **Gateway listener `ResolvedRefs=False`.** The Secret `chronon-tls` is
  missing in namespace `gateway`.

## How to debug it

```bash
kubectl get clusterissuer
kubectl get certificate,certificaterequest -A
kubectl -n gateway describe certificate chronon-tls
make ca                                            # prints subject and expiry
openssl s_client -connect api.chronon.test:8443 -servername api.chronon.test \
  -CAfile .certs/ca.pem -alpn h2 </dev/null 2>/dev/null | grep -E 'Verify|ALPN'
```
