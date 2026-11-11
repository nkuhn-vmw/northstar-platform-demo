# Deploy on your own foundation

Use an existing dedicated org and space on a compatible Tanzu Platform 11 foundation. Your operator must already provide Agent Buildpack on `tanzucflinuxfs1`, Java and binary buildpacks, and model, `p-identity`, MCP Gateway, native Agent Memory and Credential Store service plans visible to your org. Platform licensing and access are supplied by your organization; the source license does not provide platform products or entitlements.

Install the [build prerequisites](development.md). Trust the foundation's CA on your workstation and the platform. Never disable TLS verification to make a demo work.

## Configure and inspect

```sh
cp profiles/platform-11.example.json my-foundation.local.json
cf login -a https://api.YOUR-FOUNDATION --sso
cf target -o YOUR_ORG -s YOUR_DEDICATED_SPACE
cf target
cf marketplace
cf buildpacks
cf domains
```

Fill the ignored local profile with your operator's values:

| Profile field | Your value |
| --- | --- |
| `target` | Exact API, org, space and a unique installation prefix |
| `routes` | Public app domain and internal routing domain |
| `buildpacks` | Installed Agent, Java and binary buildpack names |
| `services` | Offering/plan pairs accessible in your org; native memory must use `agent-memory` |
| `models.interactive` | A real model ID available from the selected model plan |
| `sso` | SSO plan's identity provider, registered scopes, a runtime scope subset containing `openid`, and exact allowed presenter emails |
| `customer` | Display name, description and welcome prompts; edit `apps/agent/branding` for your visual assets |
| `guide.documentation_url` | This walkthrough or your own deployment instructions |
| `credential_store_ui_base` | Optional Hub collection URL; the guide appends this installation's store GUID |
| `hub` and `integrations.hub` | Leave disabled until the initial installation is ready; then follow [Hub setup](hub-oauth.md) |

The profile defaults to requiring verified email claims. Set `sso.allow_unverified_email` to `true` only if the operator confirms the bound SSO issuer supplies a trustworthy, administrator-controlled email claim but omits `email_verified`. Never use that compatibility option with self-asserted or editable unverified emails. The exact-email list controls admission; `['*']` (JSON uses double quotes) explicitly admits every user authenticated by that SSO service.

Confirm that Agent Memory trusts the presenter's SSO issuer. Configure callbacks in your own environment; do not copy a colleague's roles, client secrets, memory, or OAuth grants. The kit does not modify shared SSO configuration.

## Build, plan and deploy

```sh
bin/prepare
bin/prepare --check
bin/verify
bin/demo --config my-foundation.local.json plan --phase 4 --json
bin/demo --config my-foundation.local.json preflight --phase 4 --json
```

Inspect the exact target and planned app/service names. Preflight checks plan access, installed buildpacks, domains, ownership collisions and CF quotas. An operator must separately confirm broker/model capacity and staging headroom; a quota response cannot establish those.

```sh
bin/demo --config my-foundation.local.json deploy --phase 4 --apply
bin/demo --config my-foundation.local.json validate --phase 4 --json
```

The lifecycle uses an isolated CF CLI context, labels its resources with an installation owner, and journals resource GUIDs under ignored `.state/`. Keep that journal securely with the installation owner for reconciliation and [cleanup](reset.md). Do not distribute it with the source.

## Verify as a presenter

Open `https://<prefix>-guide.<apps-domain>/` and follow [the presenter checklist](present.md). Require an allowed login, a denied identity, a real model response, a Market tool result, and native memory recall in a fresh conversation. A CLI result containing `manual-required` is not full live acceptance.

Hub is optional. After [registering your own gateway callback](hub-oauth.md), enable it, redeploy, complete user consent, and verify one read-only inventory call. Credentials belong in Credential Store and private operator files, never in chat or Git.

## Rehearsal spaces

`--mode phase-spaces` targets an existing `<space>-phaseN` and adds `-pN` to the prefix. The space must already exist; the kit will not create it or grant roles. Each such deployment includes the complete dependency set for that phase. A Hub OAuth client must use the callback for that exact phase prefix.
