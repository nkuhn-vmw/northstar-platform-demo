# Northstar demo guide

Phase 4 adds a small, SSO-protected presenter guide at the generated `-guide` route.
It includes launch links, sample prompts, an endpoint directory, and authentication
and rehearsal instructions. The connections section includes a responsive architecture
diagram, a full-size view, and an SVG download behind the same SSO protection. The
reference diagram illustrates the full optional integration setup; the endpoint
directory reflects the selected deployment. No credential-entry fields or backend administration
operations are provided. The page is a deployment guide, not live telemetry.

The standard-library Go server embeds its assets and listens only on loopback.
The existing pinned oauth2-proxy binary owns the CF-facing port and authenticates
against the bound `p-identity` service. The same email policy as Copilot applies: exact addresses, or the explicit
`*` opt-in for all users authenticated through the bound SSO service. Only `/health` is exempt among guide routes; oauth2-proxy also exposes its own login and health endpoints. Without a valid SSO binding, startup fails closed.

`bin/prepare` builds `.artifacts/demo-guide-server`. The lifecycle stages only that
binary and the prepared oauth2-proxy executable, sets non-secret `GUIDE_*` URLs and
labels from the selected profile, binds SSO, and records app/route ownership. The
guide does not bind models, memory, MCP descriptors, or provider credentials.

Local development: `go run . --preview` serves a loopback-only preview at
`http://127.0.0.1:8766`. Set the `GUIDE_*` environment values from the rendered
manifest for meaningful links. Preview mode is refused when `VCAP_APPLICATION`
is present. Run `go test ./...` here and the kit's Python regression suite from
its root after changing the deployment integration.
