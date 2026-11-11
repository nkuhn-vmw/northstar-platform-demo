#!/usr/bin/env bash
set -euo pipefail
set +x

# Platform 11 uses native service bindings. This launcher only preserves the
# exact-email SSO gate until native authorization offers equivalent behavior.
app_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
allowed_file=""
agent_pid=""
proxy_pid=""
cleanup() {
  local pid
  for pid in "$proxy_pid" "$agent_pid"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  [[ -z "$allowed_file" ]] || rm -f -- "$allowed_file"
}
trap cleanup EXIT INT TERM
external_port="${PORT:?Cloud Foundry PORT is required}"
internal_port="${TANZU_AGENT_INTERNAL_PORT:-8091}"
if [[ -z "${VCAP_SERVICES:-}" ]]; then
  export VCAP_SERVICES='{}'
fi

# Require SSO in both exact-email and explicitly enabled all-SSO-user modes.
sso_binding_json="$(
  printf '%s' "$VCAP_SERVICES" |
    jq -c '[to_entries[] | select(.key == "p-identity") | .value[]?][0] // empty'
)"
[[ -n "$sso_binding_json" ]] || {
  echo "ERROR: p-identity binding is required" >&2
  exit 1
}
allowed_emails="${APP_ALLOWED_EMAILS:-}"
[[ -n "$allowed_emails" ]] || {
  echo "ERROR: APP_ALLOWED_EMAILS must contain exact emails or explicitly be *" >&2
  exit 1
}

auth_domain="$(printf '%s' "$sso_binding_json" | jq -er '.credentials.auth_domain | sub("/+$"; "")')"
client_id="$(printf '%s' "$sso_binding_json" | jq -er '.credentials.client_id')"
client_secret="$(printf '%s' "$sso_binding_json" | jq -er '.credentials.client_secret')"
discovery_json="$(curl --fail --silent --show-error --max-time 15 "$auth_domain/.well-known/openid-configuration")"
issuer="$(printf '%s' "$discovery_json" | jq -er '.issuer')"
login_url="$(printf '%s' "$discovery_json" | jq -er '.authorization_endpoint')"
redeem_url="$(printf '%s' "$discovery_json" | jq -er '.token_endpoint')"
jwks_url="$(printf '%s' "$discovery_json" | jq -er '.jwks_uri')"
route="${TANZU_AGENT_BASE_URL:?TANZU_AGENT_BASE_URL is required}"
route_host="${route#https://}"
route_host="${route_host%%/*}"
redirect_url="https://${route_host}/oauth2/callback"

if [[ "$allowed_emails" == "*" ]]; then
  email_auth_args=(--email-domain='*')
else
  allowed_file="$(mktemp "${TMPDIR:-/tmp}/agent-allowed-emails.XXXXXX")"
  chmod 600 "$allowed_file"
  printf '%s' "$allowed_emails" |
    awk -F, '
      {
        for (entry = 1; entry <= NF; entry++) {
          email = $entry
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", email)
          if (email == "" || email ~ /[*?]/ || email !~ /^[^@[:space:]]+@[^@[:space:]]+$/) {
            invalid = 1
          } else {
            print tolower(email)
          }
        }
      }
      END { if (invalid) exit 1 }
    ' |
    sort -u >"$allowed_file" || {
    echo "ERROR: APP_ALLOWED_EMAILS contains an invalid email" >&2
    exit 1
  }

  email_auth_args=(--authenticated-emails-file="$allowed_file")
fi

cookie_seed="$(printf '%s' "${client_secret}:agent-beta-cookie-v1" | sha256sum | awk '{print substr($1,1,32)}')"
cookie_secret="$(printf '%s' "$cookie_seed" | base64 | tr -d '\n')"
export OAUTH2_PROXY_CLIENT_ID="$client_id"
export OAUTH2_PROXY_CLIENT_SECRET="$client_secret"
export OAUTH2_PROXY_COOKIE_SECRET="$cookie_secret"
unset client_id client_secret cookie_seed cookie_secret sso_binding_json discovery_json

export TANZU_AGENT_HOST=127.0.0.1
export TANZU_AGENT_PORT="$internal_port"

tanzu-agent &
agent_pid=$!
for _attempt in {1..240}; do
  curl --fail --silent --max-time 1 "http://127.0.0.1:${internal_port}/health" >/dev/null 2>&1 && break
  kill -0 "$agent_pid" 2>/dev/null || {
    wait "$agent_pid" || true
    echo "ERROR: tanzu-agent exited before the SSO proxy started" >&2
    exit 1
  }
  sleep 0.25
done
curl --fail --silent --max-time 2 "http://127.0.0.1:${internal_port}/health" >/dev/null

"$app_root/bin/oauth2-proxy" \
  --provider=oidc \
  --provider-display-name="Platform SSO" \
  --skip-oidc-discovery=true \
  --oidc-issuer-url="$issuer" \
  --login-url="$login_url" \
  --redeem-url="$redeem_url" \
  --oidc-jwks-url="$jwks_url" \
  --skip-claims-from-profile-url=true \
  --scope="${TANZU_AGENT_AUTH_OAUTH_SCOPES:-openid roles}" \
  --prompt=select_account \
  --code-challenge-method=S256 \
  --redirect-url="$redirect_url" \
  --whitelist-domain="$route_host" \
  --http-address="0.0.0.0:${external_port}" \
  --upstream="http://127.0.0.1:${internal_port}/" \
  --upstream-timeout=24h \
  --flush-interval=100ms \
  --proxy-websockets=true \
  --skip-provider-button=true \
  "${email_auth_args[@]}" \
  --insecure-oidc-allow-unverified-email="${SSO_ALLOW_UNVERIFIED_EMAIL:-false}" \
  --cookie-name=__Host-agent_beta_sso \
  --cookie-secure=true \
  --cookie-httponly=true \
  --cookie-samesite=lax \
  --cookie-expire=8h \
  --session-cookie-minimal=true \
  --skip-auth-route='GET=^/health$' \
  --skip-auth-route='HEAD=^/health$' \
  --pass-basic-auth=false \
  --pass-authorization-header=false \
  --pass-access-token=false \
  --pass-user-headers=true \
  --silence-ping-logging=true \
  --banner=- \
  --footer=- &
proxy_pid=$!

wait -n "$agent_pid" "$proxy_pid"
