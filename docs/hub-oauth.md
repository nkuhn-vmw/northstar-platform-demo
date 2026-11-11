# Hub through the gateway’s OAuth app binding

Use this path with the Platform 11 package and a gateway whose app-binding schema
supports `auth.service-instance` with type `OAUTH`. The [vendor binding guidance](https://knowledge.broadcom.com/external/article/447310/onplatform-mcp-endpoint-discovery-uses-e.html) describes app-bound OAuth routes and avoiding ambiguous public/internal routing. This example uses the app-binding route so the gateway can resolve stored user credentials.

The Hub OAuth scene requires phase 3 or later, when Credential Store is bound.
Keep Hub disabled for earlier phases. The kit runs a small internal-only Hub MCP relay. The gateway owns authorization,
resolves the presenter's Credential Store grant, and sends the resulting Hub
access token to the relay. The relay forwards only to the configured HTTPS Hub
MCP URL. It stores no credentials, has no browser login, and receives no OAuth
client binding. SpaceDevelopers can read the client secret from its user-provided service; deploy
this client only in a space whose developers you trust. It is not a presenter
access token. The installation's OAuth client is separate from each presenter's
user-scoped grant. No vendor runtime code is modified.

## Install in your environment

1. Follow the [independent foundation walkthrough](deploy.md),
   initially leaving `integrations.hub` false. Deploy phase 4 so the gateway,
   native Credential Store, native memory and guide exist.
2. In your private profile, set `hub.mcp_url`, `hub.resource_metadata_url` and
   `hub.authorization_server` from **your** Hub's discovery metadata. Keep
   `hub.auth_mode` set to `gateway-oauth`. Obtain the actual gateway dashboard
   URL with `cf service <your-prefix>-gateway` in the verified target space.
3. Preview, then register an installation-specific OAuth client:

   ```bash
   bin/register-hub --config my-foundation.local.json --gateway-url https://YOUR-GATEWAY
   bin/register-hub --config my-foundation.local.json --gateway-url https://YOUR-GATEWAY --apply
   ```

   The command checks resource and issuer metadata, registers the exact callback
   `https://YOUR-GATEWAY/<your-prefix>-hub-relay/auth/callback`, and writes
   `.credentials/hub-oauth.json` with mode 0600 (relative to your profile).
   Repeating the command retains a matching client. An interrupted registration
   leaves an empty-object marker to prevent duplicate clients: resolve the
   uncertain registration with your Hub operator before removing that marker.
   If dynamic registration is unavailable, ask the operator to register the same
   exact callback with `client_secret_post`, authorization code and refresh
   grants, and supply the private JSON fields `client_id`, `client_secret`,
   `authorization_endpoint`, `token_endpoint`, and `redirect_uri`.
4. Set `integrations.hub` true, then run preflight, deploy and validate again:

   ```bash
   bin/demo --config my-foundation.local.json preflight --phase 4
   bin/demo --config my-foundation.local.json deploy --phase 4 --apply
   bin/demo --config my-foundation.local.json validate --phase 4
   ```

The registration helper requires upstream `client_secret_post` support and validates the advertised resource and issuer. If your provider does not support that contract, keep Hub disabled and consult its supported OAuth integration guidance.

Keep the client file, private profile and `.state` with the installation owner;
never share them in the portable source kit. Use separate files and registrations
for a different gateway or phase-space prefix. For phase-spaces deployments, pass
the same `--mode phase-spaces --phase N` to registration and lifecycle commands.
TLS validation remains enabled. When retiring an installation, ask its Hub operator
to remove its OAuth client; CF cleanup does not deregister that Hub client. Default cleanup also retains the local Hub OAuth service and its client secret; see [cleanup and data retention](reset.md).

## Presenter consent and read-only acceptance

Open this installation's Credential Store in Tanzu Hub. Add the Hub descriptor,
keep **Scope credential to current user** checked, allow the authentication popup,
complete the gateway and Hub OAuth flow, then save. Use the descriptor for this installation's `/<prefix>-hub-relay/mcp` resource; a grant for another resource or installation is not interchangeable.
Reconnect in Copilot and request the applications in your own org and space,
explicitly using read-only operations. Inspect the actual tool result. A healthy
app, successful consent or discovered tool list alone is not inventory acceptance.

SSO and CF roles are environment-specific. An empty resource picker means the
presenter needs appropriate access to the store's space; the kit does not grant
roles. An identity-provider callback error needs an operator to register the exact
HTTPS callback for that Hub/gateway flow. Never widen those callbacks to a wildcard or use a shared personal token. The separate native agent SSO client uses a redirect pattern restricted to its own exact application origin to support the platform runtime's login paths.
If a connection is not ready, switch it off in your session to keep other scenes
usable. Hub retains the user's existing permissions; the demo's read-only prompt
is not an authorization boundary for every tool Hub may expose.
