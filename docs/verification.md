# Verification record

Checked on 11 November 2026. This is a source release candidate. Authenticated core flows and optional user-scoped Hub inventory passed on an independent foundation. Each installation still needs its own configuration, credentials and acceptance checks.

## Local checks completed

- Prepared all four Linux/amd64 artifacts, verified official archive/executable hashes, source-tree pins and output digests.
- Passed 69 Python orchestration, ownership, credential handling and launcher checks; both Go test suites; four Market integration tests on Java 21 / Spring Boot 4.1.2. `bin/verify --offline` passed with populated caches.
- Checked the native phase/mode plans with Hub enabled and disabled, source syntax, package boundaries and 32 local documentation links.
- Interactively checked the loopback presenter guide, native architecture diagram and endpoint filtering. The rebuilt Market served its synthetic catalog and Produce filter returned three products. These were unauthenticated local previews.
- Gitleaks 8.30.1 reported no findings in the selected source export or initial clean Git history. Old repository history, local profiles, state, credentials, logs and build caches are excluded from this new repository.

Independent review found no code-level release blocker. Its deployment-risk and cleanup documentation findings were corrected; artifact integrity, stack compatibility and runtime-only SSO configuration also received focused fixes and regression checks. A bounded follow-up found no actionable defects in the integrity and stack gates. The reviewed code at `2d6bd3e` passed [fresh-clone CI](https://github.com/nkuhn-vmw/northstar-platform-demo/actions/runs/43071146059). This evidence-only documentation update changes no application or deployment code. Use the [latest workflow run](https://github.com/nkuhn-vmw/northstar-platform-demo/actions/workflows/verify.yml) for subsequent revisions. Every deployment must complete the signed-in checks in [the deployment guide](deploy.md).

## Independent foundation rehearsal

Deployed phase 4 from this standalone kit into a newly created, isolated space on
a second foundation. The operator explicitly accepted the unresolved proxy risk
below for this rehearsal only. The original deployment was not changed.

- The guide and native agent admitted the allowed presenter through SSO with
  verified email still required. A real model response completed.
- An agent-originated `northstar_search_products` call returned the three
  expected Produce products and SKUs through the MCP Gateway.
- Native `save_memory` stored a unique synthetic fact. In a separate new
  conversation, `search_memories` retrieved its saved value without that value
  being supplied in the retrieval prompt.
- The unauthenticated agent API was denied. Temporarily excluding the signed-in
  presenter from the guide's allowlist produced HTTP 403. The original allowlist
  was restored exactly and allowed admission was verified again.
- The optional Hub client, internal relay, gateway OAuth binding and descriptor
  deployed. After an operator approved the missing exact foundation SSO callback,
  the presenter completed both consent steps and saved an OAuth credential with
  User scope. The agent called `get_organizations`, `get_spaces` and
  `get_applications` through Hub, filtering applications by the new space's GUID.
  The raw result contained exactly the four expected apps: agent, Market, guide
  and relay. Their reported STARTED/RUNNING states matched a separate Cloud
  Foundry status check. No Hub write tool was invoked. The
  [Hub walkthrough](hub-oauth.md) includes callback and session-reconnect steps.
- Cleanup was previewed only; no service data was deleted.

Observed platform components: Agent Buildpack 0.2.39, Java Buildpack 5.0.0,
Binary Buildpack 1.1.95, and `tanzucflinuxfs1`. These are observed rehearsal
versions, not a promise of compatibility with every platform release.

## Built-artifact security assessment

Trivy 0.70.0 `rootfs --scanners vuln` scanned the prepared Market JAR, guide, relay and official oauth2-proxy executable with the 11 November 2026 vulnerability database. Four language artifacts were recognized. No OS/container image or platform-managed agent runtime was scanned. These are local artifacts, not proof of live container contents.

The Market's RabbitMQ client was upgraded to the official [5.37.1 maintenance release](https://github.com/rabbitmq/rabbitmq-java-client/releases/tag/v5.37.1), removing the ten findings in the managed 5.30.0 baseline. Final scan: zero findings in Market, guide and relay; two findings with unknown severity in oauth2-proxy 7.15.6. No suppressions were used.

| Remaining finding | Evidence and disposition |
| --- | --- |
| [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932) | Module-level match for `golang.org/x/crypto v0.58.0`; the advisory concerns the abandoned OpenPGP packages. Go's `govulncheck 1.9.0 -mode=binary` found the module but no affected OpenPGP package/symbol in this executable. The raw match remains visible; this is not an assertion about other binaries. |
| [CVE-2026-97054 / GO-2026-6859](https://pkg.go.dev/vuln/GO-2026-6859) | The official binary embeds Go 1.26.10; fixes are Go 1.26.11 / 1.27.4. Binary analysis confirms affected `net/http` symbols. The advisory describes a possible HTTP/1 server panic when request-body limiting and concurrent response-header writes overlap. Exploitability in this configuration has not been established. The latest official [oauth2-proxy 7.15.6 release](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.6) predates this fix; no fixed official binary was available at assessment time. This remains an unresolved upstream finding, requiring an operator decision before deployment. No local fork or upstream rebuild is included. |

### Artifact identities

These hashes identify the local scan inputs; source-built outputs may differ with toolchains or embedded Git build metadata. The preparation journal records each build's actual digests.

| Artifact | SHA-256 |
| --- | --- |
| oauth2-proxy | `cbaad42f283a1f729ced94b39f7c453039c3aa8d20c9a44c6ff67a4f02072fb2` |
| northstar-market | `babc830f5087fce90f0c2e167dafced13b628009567d5f5a86560624b92274ca` |
| demo-guide | `a9981dde36ca283fad207eaefe0578e14a5e1d06e79d258f511807d2ea3c16e7` |
| hub-mcp-relay | `4f4d75b3161a8554ab9efbc2baf61d9fd573c0be7abe977935b7c19e630caa59` |
