"""Register an installation-specific Hub OAuth client using public discovery."""
import json
import http.client
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .config import ConfigError, read_secret, require_https, target_for


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, url):
        return None


def request_json(url, payload=None):
    require_https(url, 'Hub discovery endpoint')
    headers = {'Accept': 'application/json'}
    body = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('oversized response')
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError('expected object')
        return value
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
        raise ConfigError('Hub discovery or registration failed (response suppressed)') from None


def callback_url(config, gateway_url):
    require_https(gateway_url, 'gateway URL')
    return gateway_url.rstrip('/') + '/' + config['target']['prefix'] + '-hub-relay/auth/callback'


def register(config, gateway_url, apply=False, phase=4, mode='cumulative'):
    if phase < 3:
        raise ConfigError('Hub OAuth registration requires phase 3 or later for Credential Store')
    config = dict(config, target=target_for(config, phase, mode))
    callback = callback_url(config, gateway_url)
    result = {'callback': callback, 'credential_file': config['credentials']['hub_oauth']}
    if not apply:
        return dict(result, action='register this callback in Hub and save the client credentials with mode 0600')
    path = Path(config['credentials']['hub_oauth'])
    if path.exists():
        credential = read_secret(config, 'hub_oauth')
        if credential['redirect_uri'] != callback:
            raise ConfigError('Hub client file belongs to another gateway callback; use a separate credential file')
        return dict(result, action='existing client retained')
    hub = config['hub']
    resource = request_json(hub['resource_metadata_url'])
    if resource.get('resource') != hub['mcp_url'] or hub['authorization_server'] not in resource.get('authorization_servers', []):
        raise ConfigError('Hub protected-resource metadata does not match this profile')
    parsed = urlsplit(hub['authorization_server'])
    discovery_url = urlunsplit((parsed.scheme, parsed.netloc, '/.well-known/oauth-authorization-server' + parsed.path.rstrip('/'), '', ''))
    discovery = request_json(discovery_url)
    if discovery.get('issuer') != hub['authorization_server']:
        raise ConfigError('Hub authorization issuer does not match this profile')
    for name in ('authorization_endpoint', 'token_endpoint', 'registration_endpoint'):
        require_https(discovery.get(name, ''), name)
    if 'client_secret_post' not in discovery.get('token_endpoint_auth_methods_supported', ['client_secret_basic']):
        raise ConfigError('Hub must support client_secret_post for this OAuth binding')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Reserve the destination before registering. Concurrent attempts cannot
    # create multiple clients. A failed request leaves a marker for inspection.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write('{}\n')
        output.flush()
        os.fsync(output.fileno())
        registration = request_json(discovery['registration_endpoint'], {
            'client_name': config['target']['prefix'] + ' Hub gateway',
            'redirect_uris': [callback],
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'],
            'token_endpoint_auth_method': 'client_secret_post',
        })
        if not all(isinstance(registration.get(name), str) and registration[name] for name in ('client_id', 'client_secret')):
            raise ConfigError('Hub registration returned no confidential client (response suppressed)')
        credential = {key: registration[key] for key in ('client_id', 'client_secret')}
        credential.update({key: discovery[key] for key in ('authorization_endpoint', 'token_endpoint')})
        credential['redirect_uri'] = callback
        output.seek(0)
        json.dump(credential, output, indent=2)
        output.write('\n')
        output.truncate()
        output.flush()
        os.fsync(output.fileno())
    return dict(result, action='client registered; presenter consent remains in Tanzu Hub')
