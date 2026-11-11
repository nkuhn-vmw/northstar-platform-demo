# Verification record

Checked on 11 November 2026. This is a source release candidate; authenticated acceptance on an independent foundation is still pending. Local results do not certify a model, native memory or Hub grant in your environment.

## Local checks completed

- Prepared all four Linux/amd64 artifacts, verified official archive/executable hashes, source-tree pins and output digests.
- Passed 67 Python orchestration, ownership, credential handling and launcher checks; both Go test suites; four Market integration tests on Java 21 / Spring Boot 4.1.2. `bin/verify --offline` passed with populated caches.
- Checked the native phase/mode plans with Hub enabled and disabled, source syntax, package boundaries and 27 local documentation links.
- Interactively checked the loopback presenter guide, native architecture diagram and endpoint filtering. The rebuilt Market served its synthetic catalog and Produce filter returned three products. These were unauthenticated local previews.
- Gitleaks 8.30.1 reported no findings in the selected source export. Old repository history, local profiles, state, credentials, logs and build caches are excluded from this new repository.

Fresh-clone CI and final independent review are pending. This file will be updated with their actual results. Every deployment must complete the signed-in checks in [the deployment guide](deploy.md).

## Built-artifact security assessment

Trivy 0.70.0 `rootfs --scanners vuln` scanned the prepared Market JAR, guide, relay and official oauth2-proxy executable with the 11 November 2026 vulnerability database. Four language artifacts were recognized. No OS/container image or platform-managed agent runtime was scanned. These are local artifacts, not proof of live container contents.

The Market's RabbitMQ client was upgraded to the official [5.37.1 maintenance release](https://github.com/rabbitmq/rabbitmq-java-client/releases/tag/v5.37.1), removing the ten findings in the managed 5.30.0 baseline. Final scan: zero findings in Market, guide and relay; two findings with unknown severity in oauth2-proxy 7.15.6. No suppressions were used.

| Remaining finding | Evidence and disposition |
| --- | --- |
| [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932) | Module-level match for `golang.org/x/crypto v0.58.0`; the advisory concerns the abandoned OpenPGP packages. Go's `govulncheck 1.9.0 -mode=binary` found the module but no affected OpenPGP package/symbol in this executable. The raw match remains visible; this is not an assertion about other binaries. |
| [CVE-2026-97054 / GO-2026-6859](https://pkg.go.dev/vuln/GO-2026-6859) | The official binary embeds Go 1.26.10; fixes are Go 1.26.11 / 1.27.4. Binary analysis confirms affected `net/http` symbols. The advisory describes a possible HTTP/1 server panic when request-body limiting and concurrent response-header writes overlap. Exploitability in this configuration has not been established. The latest official [oauth2-proxy 7.15.6 release](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.6) predates this fix; no fixed official binary was available at assessment time. This remains an unresolved upstream finding, requiring an operator decision before deployment. No local fork or upstream rebuild is included. |

### Artifact identities

These hashes identify the local scan inputs; source-built outputs from other toolchains may differ. The preparation journal records each build's actual digests.

| Artifact | SHA-256 |
| --- | --- |
| oauth2-proxy | `cbaad42f283a1f729ced94b39f7c453039c3aa8d20c9a44c6ff67a4f02072fb2` |
| northstar-market | `babc830f5087fce90f0c2e167dafced13b628009567d5f5a86560624b92274ca` |
| demo-guide | `4d64d028a1d93ba26630a56951f4e0127708dd4590ac32f7326f468f9a341241` |
| hub-mcp-relay | `02eca50f2182669dd93ab2c06b793018a675d8d5a1efe2afb8bf464774deb2b8` |
