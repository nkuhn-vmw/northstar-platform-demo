# Northstar Platform Demo contributor guidance

Keep this example portable and native: Platform 11 Agent Buildpack, Agent Memory,
Credential Store, MCP Gateway, Market and optional user-scoped Hub OAuth. Do not
add live foundation identifiers, credentials, local profiles, deployment state,
platform binaries or private-source build dependencies.

Preserve SSO admission, native user identity, internal relay routing, credential
redaction, exact-target and ownership checks, and guarded cleanup. Runtime AGENTS.md
in apps/agent governs the deployed agent. Update runtime/CONTRACT.md when binding,
environment or staging contracts change.

Use coherent increments and retained regression tests. Update the relevant source
recipe digest after intentional changes, prepare, then run bin/verify. Keep local,
CI, preview and authenticated live acceptance separate. Never claim manual-required
checks passed or scanner matches proven exploitable without evidence.

Repository publication needs explicit owner approval for the exact owner/repo.
Keep licensing and third-party notices accurate. Do not upload ignored local state
or secrets in reviews, app packages or releases.
