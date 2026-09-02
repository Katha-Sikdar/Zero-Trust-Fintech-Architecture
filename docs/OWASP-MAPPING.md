# OWASP mapping

## Instruments and roles (proposal §5.1)

| Document | Role in this project |
|---|---|
| **OWASP API Security Top 10 (2023)** | The instrument. The attack corpus and block-rate metric are defined against these IDs. |
| **OWASP Top 10:2025** | The crosswalk. Findings are reported against these for auditors/examiners. |
| **OWASP ASVS** | The requirements baseline for what "implemented" means. |

## The five risks under empirical test

| Risk (2023) | Name | Where enforced | Attack script | 2025 crosswalk |
|---|---|---|---|---|
| API2 | Broken Authentication | sidecar / app | `loadgen/attacks/api2_auth.js` | A07 |
| API4 | Unrestricted Resource Consumption | gateway / sidecar | `loadgen/attacks/api4_resource.js` | A02 |
| API1 | Broken Object Level Authorization | sidecar (OPA) / app | `loadgen/attacks/api1_api5_authz.js` | A01 |
| API5 | Broken Function Level Authorization | sidecar (OPA) / app | `loadgen/attacks/api1_api5_authz.js` | A01 |
| API8 | Security Misconfiguration | sidecar (mTLS mode) | `loadgen/attacks/api8_misconfig.js` | A02 |
| A10:2025 | Mishandling of Exceptional Conditions | sidecar (fail-open) | `loadgen/attacks/a10_failopen.js` | A10 |

## The API2 attack cases (all in the corpus, all adversarially realizable)

| Case | What it forges | Correct outcome |
|---|---|---|
| `alg_none` | header `alg:none`, admin claim | reject (algorithm pinned) |
| `key_confusion` | RSA public key used as an HS256 secret | reject |
| `expired` | valid signature, `exp` in the past | reject |
| `wrong_signature` | signed by an untrusted key | reject |
| `tampered` | real token, payload elevated to admin | reject (signature mismatch) |

Minted deterministically by `scripts/mint-tokens.js` into `loadgen/tokens.json`.

## The A10 experiment (RQ5)

`envoy/envoy-authz.yaml` (fail-closed, `failure_mode_allow:false`) vs
`envoy/envoy-authz-failopen.yaml` (fail-open, `true`) — a single-variable change.
Under load past λ\*, the OPA ext_authz call saturates; the fail-open mesh admits
requests **without authorization**, and the A10 probe (a valid user reaching for
a foreign object) starts returning 2xx. That collapse is the load-induced
enforcement bypass.
