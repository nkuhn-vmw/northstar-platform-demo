"""Credential-free manifests for the native Platform 11 example."""
from .config import ROOT

APP_PATHS = {'guide': '.artifacts/demo-guide-server', 'agent': 'apps/agent',
             'market': 'apps/market/build/libs/northstar-market.jar',
             'hub-relay': '.artifacts/hub-mcp-relay'}


def app_path(config, app):
    return APP_PATHS[app]


def routes(config, name, app):
    if app == 'hub-relay':
        return [(name, config['routes']['internal_domain'])]
    if app == 'market':
        return [(name, config['routes']['internal_domain']), (name, config['routes']['domain'])]
    return [(name, config['routes']['domain'])]


def manifest(config, record, phase, names, gateway_url=None, target=None):
    target = target or config['target']
    app, name = record['app'], record['name']
    public_url = 'https://' + name + '.' + config['routes']['domain']
    kind = 'java' if app == 'market' else 'agent' if app == 'agent' else 'binary'
    env = {}
    spec = {'name': name, 'instances': 1, 'memory': '1G', 'disk_quota': '2G',
            'buildpacks': [config['buildpacks'][kind]], 'no-route': True,
            'health-check-type': 'http', 'health-check-http-endpoint': '/health', 'env': env}
    if app == 'market':
        spec['health-check-http-endpoint'] = '/actuator/health'
        env.update({'JBP_CONFIG_OPEN_JDK_JRE': '{jre: {version: 21.+}}',
                    'SPRING_PROFILES_ACTIVE': 'cloud', 'SERVER_ADDRESS': '0.0.0.0',
                    'NORTHSTAR_DEPLOYMENT_MODE': 'cloud-foundry'})
    elif app == 'agent':
        spec['stack'] = 'tanzucflinuxfs1'
        env.update({
            'TANZU_AGENT_DISPLAY_NAME': config['customer']['display_name'] if phase >= 4 else 'Northstar Agent',
            'TANZU_AGENT_DESCRIPTION': config['customer']['description'] if phase >= 4 else 'Northstar agent demonstration',
            'TANZU_AGENT_USER_WORKSPACE_PATH': '/home/vcap/app',
            'TANZU_AGENT_BASE_URL': public_url, 'TANZU_AGENT_DEFAULT_MODEL': config['models']['interactive'],
            'TANZU_AGENT_ALLOW_TOKEN_ENDPOINT': 'false', 'TANZU_AGENT_ENABLE_ADMIN_UI': 'false',
            'TANZU_AGENT_ENABLE_DEBUG_UI': 'false', 'TANZU_AGENT_DEBUG': 'false',
            'TANZU_AGENT_MCP_SERVICE_TAG': 'mcp-server', 'TANZU_AGENT_MCP_SSL_VERIFY': 'true',
            'TANZU_AGENT_MEMORY_NATIVE_TOOLS': str(phase >= 3).lower(),
            'TANZU_AGENT_MEMORY_PROXY_ENABLED': str(phase >= 3).lower(),
            'TANZU_AGENT_MEMORY_IDENTITY_MODE': 'user', 'TANZU_AGENT_MEMORY_SERVICE_TAG': 'tanzu-agent-memory',
            'TANZU_AGENT_ENABLE_MEMORY_PANEL': str(phase >= 3).lower(),
            'TANZU_AGENT_FILESYSTEM_ACCESS': 'off', 'TANZU_AGENT_SHELL_ACCESS_ENABLED': 'false',
            'TANZU_AGENT_TOOL_PERMISSION_MODE': 'deny', 'TANZU_AGENT_WEB_SEARCH_ENABLED': 'false',
            'TANZU_AGENT_FILE_UPLOAD_ENABLED': 'false', 'TANZU_AGENT_KNOWN_CREDENTIAL_KEYS': '[]',
            'TANZU_AGENT_SSO_SERVICE_LABEL': 'p-identity',
            'TANZU_AGENT_AUTH_OAUTH_SCOPES': config['sso']['agent_scopes'].replace(',', ' '),
            'TANZU_AGENT_AUTH_ENFORCE_API': 'true', 'TANZU_AGENT_AUTH_A2A_PROTECTED': 'true',
        })
        if phase >= 4:
            for i, suggestion in enumerate(config['customer']['welcome_suggestions'], 1):
                env[f'TANZU_AGENT_WELCOME_SUGGESTION_{i}'] = suggestion
    elif app == 'guide':
        spec.update({'command': './demo-guide-server', 'memory': '256M'})
        gateway = gateway_url or 'https://GATEWAY-DISCOVERED-AT-DEPLOY'
        env.update({
            'GUIDE_BASE_URL': public_url, 'GUIDE_ORG': target['org'], 'GUIDE_SPACE': target['space'],
            'GUIDE_DEPLOY_DOC_URL': config['guide']['documentation_url'],
            'GUIDE_CREDENTIAL_STORE': 'true', 'GUIDE_NATIVE_MEMORY': 'true',
            'GUIDE_AGENT_URL': 'https://' + names['agent'] + '.' + config['routes']['domain'],
            'GUIDE_MARKET_URL': 'https://' + names['market'] + '.' + config['routes']['domain'],
            'GUIDE_MARKET_MCP_URL': gateway + '/' + names['market'] + '/mcp',
            'GUIDE_HUB_MCP_URL': gateway + '/' + names.get('hub-relay', target['prefix'] + '-hub-relay') + '/mcp',
            'GUIDE_GATEWAY_URL': gateway, 'GUIDE_HUB_URL': config['hub']['mcp_url'],
            'GUIDE_HUB': str(config['integrations']['hub']).lower(),
        })
    elif app == 'hub-relay':
        spec.update({'command': './hub-mcp-relay', 'memory': '128M'})
        env['HUB_MCP_URL'] = config['hub']['mcp_url']
    if app in ('agent', 'guide'):
        env.update({'APP_ALLOWED_EMAILS': ','.join(config['sso']['allowed_emails']),
                    'SSO_SCOPES': config['sso']['scopes'],
                    'SSO_ALLOW_UNVERIFIED_EMAIL': str(config['sso']['allow_unverified_email']).lower(),
                    'SSO_AUTO_APPROVED_SCOPES': config['sso']['scopes'],
                    'SSO_IDENTITY_PROVIDERS': config['sso']['identity_provider'],
                    'SSO_REDIRECT_URIS': public_url + ('/**' if app == 'agent' else '/oauth2/callback')})
    return {'applications': [spec]}


def assets(records, config, phase):
    paths = {ROOT / app_path(config, r['app']) for r in records if r['kind'] == 'app'}
    paths.add(ROOT / 'apps/agent/bin/oauth2-proxy')
    if phase >= 4:
        paths.update(ROOT / 'apps/agent/branding' / name for name in ('style.css', 'logo.svg', 'favicon.svg'))
    return sorted(paths)
