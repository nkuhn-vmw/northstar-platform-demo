"""Strict native profile parsing and phase-relevant input validation."""
import copy
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r'^[a-z][a-z0-9-]{0,39}$')
SECRETS = {'hub_oauth': ('client_id', 'client_secret', 'authorization_endpoint', 'token_endpoint', 'redirect_uri')}


class ConfigError(ValueError):
    pass


def placeholder(value):
    return isinstance(value, str) and (not value.strip() or any(x in value.lower() for x in ('example.', 'replace-', 'change-me', '<', '>')))


def _shape(value, template, path='config'):
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise ConfigError(f'{path} must be an object')
        extra, missing = set(value) - set(template), set(template) - set(value)
        if extra or missing:
            raise ConfigError(f'{path}: unknown keys {sorted(extra)}, missing keys {sorted(missing)}')
        for key in template:
            _shape(value[key], template[key], f'{path}.{key}')
    elif isinstance(template, list):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ConfigError(f'{path} must be an array of strings')
    elif type(value) is not type(template):
        raise ConfigError(f'{path} must be {type(template).__name__}')


def require_https(value, label):
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError(f'{label} requires an absolute HTTPS URL without credentials/query/fragment')


def load_config(path: Path) -> dict:
    template = json.loads((ROOT / 'profiles/platform-11.example.json').read_text())
    try:
        config = json.loads(Path(path).read_text())
    except (ValueError, OSError) as error:
        raise ConfigError('cannot read profile JSON') from error
    _shape(config, template)
    if config['version'] != 1:
        raise ConfigError('unsupported profile version')
    if config['agent_package'] != 'platform-11':
        raise ConfigError('this example requires the platform-11 agent package')
    if config['services']['memory']['offering'] != 'agent-memory':
        raise ConfigError('this example requires native agent-memory')
    if not all(config['services']['credential_store'].values()):
        raise ConfigError('native credential_store requires offering and plan')
    if config['hub']['auth_mode'] != 'gateway-oauth':
        raise ConfigError('Hub requires the supported gateway-oauth binding')
    for key in ('org', 'space'):
        if not config['target'][key] or any(c in config['target'][key] for c in '\n\r/?'):
            raise ConfigError(f'invalid target {key}')
    if not NAME.fullmatch(config['target']['prefix']):
        raise ConfigError('prefix must be a lowercase letter followed by at most 39 letters, digits or hyphens')
    require_https(config['target']['api'], 'target.api')
    for key in ('domain', 'internal_domain'):
        if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', config['routes'][key]):
            raise ConfigError(f'invalid routes.{key}')
    requested = config['sso']['agent_scopes'].split(',')
    scopes = config['sso']['scopes'].split(',')
    if any(not s or s.strip() != s for s in scopes + requested) or 'openid' not in requested or not set(requested) <= set(scopes):
        raise ConfigError('sso.agent_scopes must include openid and be a comma-separated subset of sso.scopes')
    emails = config['sso']['allowed_emails']
    if not emails or (emails != ['*'] and any(not re.fullmatch(r'[^\s*@,?]+@[^\s*@,?]+\.[^\s*@,?]+', v) for v in emails)):
        raise ConfigError('SSO allowlist requires exact email addresses or explicit ["*"]')
    if config['credential_store_ui_base']:
        require_https(config['credential_store_ui_base'], 'credential_store_ui_base')
    require_https(config['guide']['documentation_url'], 'guide.documentation_url')
    for key, value in config['credentials'].items():
        if value:
            config['credentials'][key] = str((Path(path).resolve().parent / value).resolve())
    if not 1 <= config['timeout_seconds'] <= 3600:
        raise ConfigError('timeout_seconds must be 1..3600')
    return config


def target_for(config, phase, mode):
    target = copy.deepcopy(config['target'])
    if mode == 'phase-spaces':
        target['space'] += f'-phase{phase}'
        target['prefix'] += f'-p{phase}'
    elif mode != 'cumulative':
        raise ConfigError('invalid mode')
    return target


def required_secrets(config, phase):
    return ['hub_oauth'] if phase >= 2 and config['integrations']['hub'] else []


def read_secret(config, key):
    path = Path(config['credentials'][key])
    try:
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise ConfigError(f'credential {key} must be a private file (chmod 600)')
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or set(data) != set(SECRETS[key]):
            raise ConfigError(f'credential {key} requires exactly fields: {", ".join(SECRETS[key])}')
        if any(not isinstance(v, str) or placeholder(v) for v in data.values()):
            raise ConfigError(f'credential {key} contains empty/example values')
        for field in ('authorization_endpoint', 'token_endpoint', 'redirect_uri'):
            require_https(data[field], 'Hub client ' + field)
        return data
    except (OSError, ValueError) as error:
        if isinstance(error, ConfigError):
            raise
        raise ConfigError(f'cannot read credential {key}') from None


def validate_live(config, phase):
    if phase not in range(1, 5):
        raise ConfigError('phase must be 1..4')
    if phase < 3 and config['integrations']['hub']:
        raise ConfigError('Hub gateway-oauth requires phase 3 or later for Credential Store; keep Hub disabled in earlier phases')
    relevant = [config['target'], config['routes']['domain'], config['sso'],
                config['models']['interactive'], config['buildpacks']['agent']]
    if phase >= 2 and config['integrations']['hub']:
        relevant.append(config['hub'])
        for key in ('mcp_url', 'resource_metadata_url', 'authorization_server'):
            require_https(config['hub'][key], f'hub.{key}')

    def walk(value):
        if isinstance(value, dict):
            return any(walk(v) for v in value.values())
        if isinstance(value, list):
            return not value or any(walk(v) for v in value)
        return placeholder(value)

    if any(walk(v) for v in relevant):
        raise ConfigError('phase-relevant profile contains unresolved example/empty values')
    for key in required_secrets(config, phase):
        read_secret(config, key)
