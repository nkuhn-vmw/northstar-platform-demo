# Runtime contract

`apps/agent/runtime/launch-agent.sh` starts the foundation-provided `tanzu-agent` on loopback and the pinned oauth2-proxy on the CF-facing port. It requires Bash 4+, curl, jq, sha256sum, base64, one `p-identity` binding, `PORT`, `TANZU_AGENT_BASE_URL` and an explicit `APP_ALLOWED_EMAILS` policy. SSO is required even for the explicit all-authenticated-users option. Only health routes bypass authentication. `SSO_ALLOW_UNVERIFIED_EMAIL` defaults false; see the [issuer requirement](../docs/deploy.md).

The agent consumes native model, `tanzu-agent-memory`, `credential-store` and `mcp-server` bindings. Memory uses user identity. Filesystem/shell access, uploads, admin/debug UI and token endpoints remain disabled. Customer branding comes from `apps/agent/branding` and is staged only in phase 4.

The guide embeds its static assets, listens on loopback, and uses its own SSO binding/proxy. It receives non-secret `GUIDE_*` URLs and labels. It never binds memory, models, MCP descriptors or Hub client credentials. Preview mode is loopback-only and refused in CF.

The optional Hub relay accepts internal `/mcp` traffic through the MCP Gateway's OAuth app binding. The gateway forwards the presenter's OAuth bearer token; the relay sends it only to the configured HTTPS Hub MCP origin, rejects redirects, and forwards bounded protocol traffic. It provides no token storage or authentication fallback. The operator's OAuth client is a separate user-provided service bound to the gateway authentication mechanism, not uploaded in an app.

`bin/prepare` produces four Linux/amd64 artifacts, verifies official release hashes, and binds source-built output to source-tree digests. Deployment preflight rechecks those digests and modes without requiring Go or Java; it is local integrity checking, not runtime attestation. The lifecycle stages explicit files, never the build cache, credential directory or deployment journal. See [provenance](../provenance/SOURCES.md).
