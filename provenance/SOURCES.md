# Source provenance

The initial public example was extracted from the owner-controlled Northstar demo kit at revision `8fc0c6bd2238a3931cac78d1a27b677d226a5dce`. It starts with fresh Git history. The owner confirmed authority to release the retained code/assets and selected Apache-2.0 on 11 November 2026. Third-party licenses remain separate.

| Included source | Origin and changes |
| --- | --- |
| `apps/market` | Northstar Market originated at `78f0026093360feec275513496473918f60c36a2`, with the demo's MCP/security changes. This extraction upgrades Spring Boot/Jackson and supporting libraries; the synthetic commerce and catalog behavior is retained. |
| `apps/agent` | Native Platform 11 package and Northstar branding from the demo kit. Uses the platform-provided runtime and a pinned external SSO proxy; no native vendor runtime is redistributed. Verified-email admission is now the default, with a documented operator opt-in for compatible trusted issuers. |
| `apps/demo-guide` | Northstar guide server and assets from the demo kit. Removed live-lab links and excluded integration scenes; generalized deployment links and replaced the diagram with the native architecture. |
| `runtime/hub-mcp-relay` | Supported gateway OAuth relay from the demo kit. Preserves the configured upstream origin, header timeouts and no-token-storage contract. |
| `northstar_kit`, `bin`, `tests` | Existing lifecycle, configuration, registration, preparation and safety regressions. Restricted to native phases 1–4 and optional Hub; static verification now checks this standalone package. |

The extraction excludes live lab profiles/records, credentials/state, old Git history, legacy memory/CredHub bridges, optional search/GitHub servers, headless examples and the older slide deck. The private operator kit is not a build dependency.

[dependencies.json](dependencies.json) identifies every prepared artifact, source recipe, public release archive, digest and license. [NOTICE](../NOTICE) preserves third-party attribution; the [asset record](../apps/market/ASSET-PROVENANCE.md) documents generated imagery. Source-tree pins describe this maintained example, not unchanged upstream bytes.
