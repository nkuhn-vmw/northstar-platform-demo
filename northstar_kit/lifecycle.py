"""Read-only gates, owned CF reconciliation, and evidence-level validation."""
import hashlib
import json
import runpy
import shutil
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from .cf import CFError
from .config import ROOT, ConfigError, placeholder, read_secret, require_https, target_for, validate_live
from .render import APP_PATHS, app_path, assets, manifest, routes
from .state import digest
from .topology import omitted_scenes, resolve

OWNER = 'northstar-kit-owner'


def verify_prepared_assets(root):
    checker = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'bin/prepare'))
    try:
        checker['check_all'](root, checker['_load_dependencies'](root), require_toolchains=False)
    except (checker['PrepareError'], OSError, ValueError) as error:
        raise CFError('prepared artifact verification failed: ' + str(error) + '; run bin/prepare') from None


def http_status(url, method='GET', data=None, headers=None):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, data=data, method=method, headers=headers or {}), timeout=15) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (OSError, ValueError):
        raise CFError('HTTPS probe failed; verify DNS and trusted TLS certificates') from None


def plan(config, phase, mode='cumulative'):
    records = resolve(config, phase, mode)
    names = {r['id']: r['name'] for r in records}
    return {'target': target_for(config, phase, mode), 'phase': phase, 'mode': mode, 'live_verified': False, 'notice': 'Offline plan: example values and GATEWAY-DISCOVERED-AT-DEPLOY require live preflight resolution.', 'omitted_scenes': omitted_scenes(config, phase), 'components': records, 'manifests': {r['id']: manifest(config, r, phase, names, target=target_for(config, phase, mode)) for r in records if r['kind'] == 'app'}}


class Lifecycle:
    def __init__(self, config, phase, mode, cf, state, probe=http_status):
        self.config, self.phase, self.mode, self.cf, self.state, self.probe = config, phase, mode, cf, state, probe
        self.target = target_for(config, phase, mode)
        self.records = resolve(config, phase, mode)
        self.by_id = {r['id']: r for r in self.records}
        self.names = {r['id']: r['name'] for r in self.records}
        self.plans, self.domains, self.changed_services = {}, {}, set()
        self.paid_plans = set()
        self.gateway_url = None

    def verify_target(self):
        current = self.cf.target_metadata()
        if current['api'].rstrip('/') != self.target['api'].rstrip('/') or current['org'] != self.target['org']:
            raise CFError('CF API/org target mismatch; no remote mutations performed')
        if self.mode == 'phase-spaces' and current['space'] == self.config['target']['space']:
            matches = self.cf.list('spaces', names=self.target['space'], organization_guids=current['org_guid'])
            if len(matches) != 1:
                raise CFError('selected phase space must already exist; create it explicitly with cf CLI')
            self.cf.run(['target', '-s', self.target['space']])
            current = self.cf.target_metadata()
        if current['space'] != self.target['space']:
            raise CFError('CF space target mismatch; no remote mutations performed')
        identity = {k: current[k] for k in ('org_guid', 'space_guid')}
        if self.state.data.get('identity', identity) != identity:
            raise CFError('target GUID changed since journal creation; refusing replacement target')
        self.identity = identity
        return current

    def owned(self, kind, item, key=None):
        if item.get('metadata', {}).get('labels', {}).get(OWNER) != self.state.data['owner']:
            raise CFError(f'unowned {kind} collision: {item.get("name", item["guid"])}')
        recorded = self.state.data['resources'].get(key) if key else None
        if recorded and recorded['guid'] != item['guid']:
            raise CFError(f'recorded GUID mismatch for {key}')
        return item

    def lookup(self, kind, record):
        items = self.cf.list(kind, names=record['name'], space_guids=self.identity['space_guid'])
        if len(items) > 1:
            raise CFError('ambiguous named resource')
        return self.owned(kind, items[0], record['id']) if items else None

    def check_agent_package(self, app, record):
        if record['app'] == 'agent':
            installed = app.get('metadata', {}).get('labels', {}).get('northstar-kit-package', 'compatible')
            if installed != self.config.get('agent_package', 'compatible'):
                raise CFError('cannot switch an existing agent package; use a new installation prefix')

    def check_app_routes(self, app):
        # no-route in a pushed manifest removes ALL existing mappings, so inspect
        # attached routes even when they are not part of the desired route set.
        for route in self.cf.list(f'apps/{app["guid"]}/routes'):
            self.owned('route attached to app', route)
            destinations = self.cf.api('/v3/routes/' + route['guid'] + '/destinations').get('destinations', [])
            if any(d['app']['guid'] != app['guid'] for d in destinations):
                raise CFError('shared route attached to app; refusing mapping removal')

    def preflight(self):
        self.verify_target()
        self.check_integration_removal()
        validate_live(self.config, self.phase)
        checks = [{'check': 'target', 'status': 'pass', 'detail': self.target}]
        missing = [str(p.relative_to(ROOT)) for p in assets(self.records, self.config, self.phase) if not p.exists()]
        if missing:
            raise CFError('missing prepared assets: ' + ', '.join(missing) + '; run bin/prepare')
        verify_prepared_assets(ROOT)
        checks.append({'check': 'local-assets', 'status': 'pass'})
        needed = {r.get('service', 'credentials') for r in self.records if not r.get('user_provided') and (r['kind'] in ('service', 'credential') or r.get('secret'))}
        for key in sorted(needed):
            spec = self.config['services'][key]
            if any(placeholder(v) for v in spec.values()):
                raise ConfigError('unresolved offering/plan: ' + key)
            offering = self.cf.list('service_offerings', names=spec['offering'])
            if len(offering) != 1:
                raise CFError(f'offering missing or ambiguous: {spec["offering"]}')
            plans = self.cf.list('service_plans', names=spec['plan'], service_offering_guids=offering[0]['guid'])
            if len(plans) != 1:
                raise CFError(f'plan missing or ambiguous: {key}')
            selected = plans[0]
            visibility = self.cf.api('/v3/service_plans/' + selected['guid'] + '/visibility')
            visible = visibility['type'] == 'public' or (visibility['type'] == 'organization' and self.identity['org_guid'] in [o['guid'] for o in visibility.get('organizations', [])])
            if not visible or selected.get('available') is False:
                raise CFError(f'plan {key} is unavailable to the chosen org; ask an operator for access')
            self.plans[key] = selected['guid']
            if selected.get('free') is not True:
                self.paid_plans.add(key)
            checks.append({'check': 'plan-access:' + key, 'status': 'pass'})
        buildpacks = self.cf.list('buildpacks')
        for record in self.records:
            if record['kind'] == 'app':
                spec = manifest(self.config, record, self.phase, self.names)['applications'][0]
                buildpack, stack = spec['buildpacks'][0], spec.get('stack')
                if stack and not self.cf.list('stacks', names=stack):
                    raise CFError('required stack missing: ' + stack)
                if not any(b['name'] == buildpack and b.get('enabled', True) and b.get('state', 'READY') == 'READY'
                           and (not stack or b.get('stack') in (None, stack)) for b in buildpacks):
                    raise CFError('buildpack missing/disabled or incompatible with stack: ' + buildpack)
        for domain in set(self.config['routes'].values()):
            found = self.cf.list('domains', names=domain)
            if len(found) != 1:
                raise CFError('route domain missing or ambiguous: ' + domain)
            self.domains[domain] = found[0]['guid']
        # Resolve every collision before the first mutation, including future routes.
        for record in self.records:
            if record['kind'] in ('service', 'credential', 'descriptor', 'app'):
                self.lookup('apps' if record['kind'] == 'app' else 'service_instances', record)
            if record['kind'] == 'app':
                app = self.lookup('apps', record)
                if app:
                    self.check_agent_package(app, record)
                    self.check_app_routes(app)
                    for binding in self.cf.list('service_credential_bindings', app_guids=app['guid']):
                        self.owned('binding attached to app', binding)
                for host, domain in routes(self.config, record['name'], record['app']):
                    for route in self.cf.list('routes', hosts=host, domain_guids=self.domains[domain]):
                        self.owned('route', route)
        if 'hub-oauth' in self.by_id:
            gateway = self.lookup('service_instances', self.by_id['gateway'])
            if gateway and gateway.get('dashboard_url'):
                from .hub import callback_url
                expected = callback_url(dict(self.config, target=self.target), gateway['dashboard_url'])
                if read_secret(self.config, 'hub_oauth')['redirect_uri'] != expected:
                    raise CFError('Hub OAuth client callback does not match this gateway and prefix')
        checks.extend(self.check_quotas())
        self.probe(self.target['api'] + '/v3/info')
        self.probe('https://northstar-tls-check.' + self.config['routes']['domain'])
        if self.phase >= 2 and self.config['integrations']['hub']:
            for key in ('mcp_url', 'resource_metadata_url', 'authorization_server'):
                self.probe(self.config['hub'][key])
        checks.append({'check': 'tls', 'status': 'pass'})
        return {'checks': checks, 'omitted_scenes': omitted_scenes(self.config, self.phase)}

    def check_integration_removal(self):
        if 'hub-relay' in self.state.data['resources'] and self.config['hub'].get('auth_mode') != 'gateway-oauth':
            raise CFError('cannot switch an installed Hub OAuth route back to passthrough; clean up with the original profile or use a new prefix')
        # Include remotely committed but unjournaled creations from interruptions.
        complete = resolve(dict(self.config, integrations={k: True for k in self.config['integrations']}), 4, self.mode)
        for record in complete:
            record['name'] = self.target['prefix'] + '-' + record['id']
            flag = record.get('integration')
            if flag and not self.config['integrations'][flag]:
                kind = 'apps' if record['kind'] == 'app' else 'service_instances'
                if self.cf.list(kind, names=record['name'], space_guids=self.identity['space_guid']):
                    raise CFError('cannot disable existing integration ' + flag +
                                  '; use a new prefix to preserve data, or the original profile for cleanup --delete-data (deletes ALL owned service data, including memory and Credential Store grants); see docs/reset.md')

    def check_quotas(self):
        """CAPI 3.212 usage summaries, including managed services (not UPS)."""
        demand = dict(memory_in_mb=0, started_instances=0, routes=0, service_instances=0)
        max_memory, paid = 0, False
        for record in self.records:
            if record['kind'] == 'app':
                spec = manifest(self.config, record, self.phase, self.names)['applications'][0]
                value = spec['memory']
                memory = int(value[:-1]) * (1024 if value.endswith('G') else 1)
                instances = spec['instances']
                max_memory = max(max_memory, memory)
                app = self.lookup('apps', record)
                current_memory, current_instances = 0, 0
                if app and app.get('state') == 'STARTED':
                    for process in self.cf.list('apps/' + app['guid'] + '/processes'):
                        if process['type'] == 'web':
                            current_instances += process['instances']
                            current_memory += process['memory_in_mb'] * process['instances']
                # Do not spend capacity expected from a later scale-down in this run.
                demand['memory_in_mb'] += max(0, memory * instances - current_memory)
                demand['started_instances'] += max(0, instances - current_instances)
                for host, domain in routes(self.config, record['name'], record['app']):
                    if not self.cf.list('routes', hosts=host, domain_guids=self.domains[domain]):
                        demand['routes'] += 1
            elif record['kind'] in ('service', 'credential', 'descriptor'):
                managed = not record.get('user_provided') and (record['kind'] != 'descriptor' or bool(record.get('secret')))
                if managed and not self.lookup('service_instances', record):
                    demand['service_instances'] += 1
                    paid = paid or record.get('service', 'credentials') in self.paid_plans
        checks = []
        try:
            org = self.cf.list('organization_quotas', organization_guids=self.identity['org_guid'])
            space = self.cf.list('space_quotas', space_guids=self.identity['space_guid'])
            if len(org) != 1 or len(space) > 1:
                raise CFError('cannot resolve exactly one org quota and at most one space quota')
            for scope, kind, guid, quotas in [('org', 'organizations', self.identity['org_guid'], org),
                                             ('space', 'spaces', self.identity['space_guid'], space)]:
                usage = self.cf.api('/v3/' + kind + '/' + guid + '/usage_summary')['usage_summary']
                for key in demand:
                    if type(usage[key]) is not int or usage[key] < 0:
                        raise ValueError('invalid usage')
                for quota in quotas:
                    fields = [('apps', 'total_memory_in_mb', 'memory_in_mb'),
                              ('apps', 'total_instances', 'started_instances'),
                              ('routes', 'total_routes', 'routes'),
                              ('services', 'total_service_instances', 'service_instances')]
                    for section, field, metric in fields:
                        limit = quota[section][field]
                        if limit is not None and (type(limit) is not int or limit < 0):
                            raise ValueError('invalid limit')
                        if limit is not None and usage[metric] + demand[metric] > limit:
                            raise CFError(f'{scope} quota insufficient for {metric}: used {usage[metric]}, incremental {demand[metric]}, limit {limit}')
                    limit = quota['apps']['per_process_memory_in_mb']
                    if limit is not None and (type(limit) is not int or limit < 0):
                        raise ValueError('invalid process limit')
                    if limit is not None and max_memory > limit:
                        raise CFError(scope + ' quota insufficient for per-process memory')
                    allowed = quota['services']['paid_services_allowed']
                    if type(allowed) is not bool:
                        raise ValueError('invalid paid service permission')
                    if paid and not allowed:
                        raise CFError(scope + ' quota disallows required paid service plans')
                checks.append({'check': 'quota:' + scope, 'status': 'pass',
                               'usage': usage, 'incremental_demand': dict(demand),
                               'quota_guid': quotas[0]['guid'] if quotas else None})
        except (KeyError, TypeError, ValueError):
            raise CFError('quota preflight needs complete CAPI quota and usage_summary fields; ask the operator to verify API support/access') from None
        except CFError as error:
            raise CFError('quota preflight failed before provisioning: ' + str(error)) from None
        checks.append({'check': 'broker-capacity', 'status': 'manual-required',
                       'detail': 'Operator must confirm broker backing capacity, gateway worker quota, model/GPU capacity, Agent Memory service capacity and staging headroom; CF quota summaries cannot establish these.'})
        return checks

    def metadata(self):
        return {'labels': {OWNER: self.state.data['owner']}}

    def service_body(self, record):
        kind = record['kind']
        body = {'name': record['name'], 'metadata': self.metadata(), 'relationships': {'space': {'data': {'guid': self.identity['space_guid']}}}, 'tags': []}
        params = {}
        service = record.get('service', 'credentials')
        if kind == 'descriptor':
            backend = record['backend']
            url = self.gateway_url + '/' + (self.names[backend] if backend != 'hub' else 'hub') + '/mcp'
            params = {'url': url}
            if record.get('auth_type'):
                params['auth_type'] = record['auth_type']
            if record.get('secret'):
                params.update(read_secret(self.config, record['secret']))
            body['tags'] = ['mcp-server']
            if not record.get('secret'):
                body.update({'type': 'user-provided', 'credentials': params})
                return body
        elif kind == 'credential':
            params = read_secret(self.config, record['secret'])
            if record['id'] == 'hub-oauth':
                from .hub import callback_url
                if params.pop('redirect_uri') != callback_url(dict(self.config, target=self.target), self.gateway_url):
                    raise CFError('Hub OAuth client callback does not match this gateway and prefix')
                params.update({'scopes': [], 'token_endpoint_auth_method': 'client_secret_post',
                               'forward_pkce': True,
                               'extra_authorize_params': {'resource': self.config['hub']['mcp_url']},
                               'extra_token_params': {'resource': self.config['hub']['mcp_url']}})
                body.update({'type': 'user-provided', 'credentials': params, 'tags': ['auth-adapter']})
                return body
        elif service == 'gateway':
            params = {'count': 1, 'memory': '1G', 'disk': '1G', 'mcp-servers': [], 'env': {}}
        if service == 'memory':
            body['tags'] = ['tanzu-agent-memory']
        if service == 'credential_store':
            body['tags'] = ['credential-store']
        body.update({'type': 'managed', 'parameters': params})
        body['relationships']['service_plan'] = {'data': {'guid': self.plans[service]}}
        return body

    def ensure_service(self, record):
        body = self.service_body(record)
        fingerprint = digest(body)
        item = self.lookup('service_instances', record)
        previous = self.state.data['resources'].get(record['id'], {})
        if item:
            if item['type'] != body['type'] or (body['type'] == 'managed' and item['relationships']['service_plan'] != body['relationships']['service_plan']):
                raise CFError('owned service has incompatible type/plan; select a new prefix')
            self.state.record(record['id'], 'service_instances', item, phase=record['phase'], **({'fingerprint': previous['fingerprint']} if 'fingerprint' in previous else {}))
            self.cf.wait_service(item['guid'])
            if previous.get('fingerprint') != fingerprint:
                self.cf.api('/v3/service_instances/' + item['guid'], 'PATCH', {k: body[k] for k in ('parameters', 'credentials', 'tags') if k in body})
                self.changed_services.add(record['id'])
        else:
            # Owner label is atomic with create; interrupted create can be recovered.
            item = self.cf.api('/v3/service_instances', 'POST', body)
            if not item.get('guid'):
                item = self.lookup('service_instances', record)
            if not item:
                raise CFError('service create pending without discoverable GUID; rerun')
            self.state.record(record['id'], 'service_instances', item, phase=record['phase'])
            self.changed_services.add(record['id'])
        self.cf.wait_service(item['guid'])
        self.state.record(record['id'], 'service_instances', item, phase=record['phase'], fingerprint=fingerprint)
        if record['id'] == 'gateway':
            item = self.cf.api('/v3/service_instances/' + item['guid'])
            self.gateway_url = (item.get('dashboard_url') or '').rstrip('/')
            require_https(self.gateway_url, 'gateway dashboard_url')

    def app_service_ids(self, record):
        return [key for key in record['depends_on']
                if self.by_id[key]['kind'] in ('service', 'credential', 'descriptor')
                and self.by_id[key].get('bind_to_apps', True)]

    def ensure_binding(self, app, service_id):
        service = self.state.data['resources'][service_id]
        key = app['name'] + ':' + service_id
        items = self.cf.list('service_credential_bindings', app_guids=app['guid'], service_instance_guids=service['guid'])
        if len(items) > 1:
            raise CFError('ambiguous service binding')
        binding_fingerprint = service.get('fingerprint')
        if service_id == 'sso':
            # agent_scopes configures the runtime, not the broker's registered
            # scopes. A runtime-only change must not rotate an existing client.
            broker_sso = {k: v for k, v in self.config['sso'].items() if k not in ('agent_scopes', 'allow_unverified_email', 'allowed_emails')}
            binding_fingerprint = digest([binding_fingerprint, broker_sso])
        gateway_hub = service_id == 'gateway' and app['name'] == self.names.get('hub-relay')
        if gateway_hub:
            binding_fingerprint = digest([binding_fingerprint, 'OAUTH', self.names['hub-oauth'],
                                          self.state.data['resources']['hub-oauth']['fingerprint']])
        changed = self.state.data['resources'].get(key, {}).get('service_fingerprint') != binding_fingerprint
        if service_id == 'sso' and changed:
            # Older journals included this runtime-only field. Normalize on
            # read without replacing a binding whose broker inputs still match.
            previous = self.state.data['resources'].get(key, {}).get('service_fingerprint')
            changed = previous not in {digest([service.get('fingerprint'), self.config['sso']]),
                                       digest([service.get('fingerprint'), dict(broker_sso, agent_scopes='')])}
        if items and changed:
            item = self.owned('binding', items[0], key)
            self.state.record(key, 'service_credential_bindings', item, app_guid=app['guid'], service_guid=service['guid'])
            self.cf.api('/v3/service_credential_bindings/' + item['guid'], 'DELETE')
            self.cf.wait_absent('service_credential_bindings', item['guid'])
            self.state.data['resources'].pop(key, None)
            self.state.save()
            items = []
        if items:
            item = self.owned('binding', items[0], key)
        else:
            body = {'type': 'app', 'metadata': self.metadata(), 'relationships': {'app': {'data': {'guid': app['guid']}}, 'service_instance': {'data': {'guid': service['guid']}}}}
            if gateway_hub:
                body['parameters'] = {'auth': {'service-instance': {'type': 'OAUTH', 'name': self.names['hub-oauth']}}}
            item = self.cf.api('/v3/service_credential_bindings', 'POST', body)
            if not item.get('guid'):
                items = self.cf.list('service_credential_bindings', app_guids=app['guid'], service_instance_guids=service['guid'])
                if len(items) != 1:
                    raise CFError('binding create pending; rerun')
                item = self.owned('binding', items[0])
            self.state.record(key, 'service_credential_bindings', item, app_guid=app['guid'], service_guid=service['guid'])
            changed = True
        self.cf.wait_binding(item['guid'])
        self.state.record(key, 'service_credential_bindings', item, app_guid=app['guid'], service_guid=service['guid'], service_fingerprint=binding_fingerprint)
        return changed

    def ensure_routes(self, app, record):
        for host, domain in routes(self.config, record['name'], record['app']):
            key = 'route:' + host + '.' + domain
            found = self.cf.list('routes', hosts=host, domain_guids=self.domains[domain])
            if found:
                if len(found) != 1:
                    raise CFError('ambiguous route')
                route = self.owned('route', found[0], key)
            else:
                route = self.cf.api('/v3/routes', 'POST', {'host': host, 'metadata': self.metadata(), 'relationships': {'space': {'data': {'guid': self.identity['space_guid']}}, 'domain': {'data': {'guid': self.domains[domain]}}}})
                self.state.record(key, 'routes', route, app_guid=app['guid'], phase=record['phase'])
            destinations = self.cf.api('/v3/routes/' + route['guid'] + '/destinations').get('destinations', [])
            if any(d['app']['guid'] != app['guid'] for d in destinations):
                raise CFError('owned route has another app destination; refusing modification')
            if not destinations:
                self.cf.api('/v3/routes/' + route['guid'] + '/destinations', 'POST', {'destinations': [{'app': {'guid': app['guid'], 'process': {'type': 'web'}}}]})
            self.state.record(key, 'routes', route, app_guid=app['guid'], phase=record['phase'])

    def ensure_app(self, record):
        app = self.lookup('apps', record)
        if app:
            self.check_agent_package(app, record)
        if not app:
            metadata = self.metadata()
            if record['app'] == 'agent':
                metadata['labels']['northstar-kit-package'] = self.config.get('agent_package', 'compatible')
                if self.config.get('agent_package') == 'platform-11':
                    metadata['labels']['ai.tanzu.com/type'] = 'agent'
            app = self.cf.api('/v3/apps', 'POST', {'name': record['name'], 'metadata': metadata, 'relationships': {'space': {'data': {'guid': self.identity['space_guid']}}}})
            self.state.record(record['id'], 'apps', app, phase=record['phase'])
        rendered = manifest(self.config, record, self.phase, self.names, self.gateway_url, self.target)
        if record['app'] == 'guide' and self.config.get('credential_store_ui_base') and 'credential-store' in self.by_id:
            store_guid = self.state.data['resources']['credential-store']['guid']
            rendered['applications'][0]['env']['GUIDE_STORE_URL'] = self.config['credential_store_ui_base'].rstrip('/') + '/' + store_guid
        source = ROOT / app_path(self.config, record['app'])
        if record['app'] == 'agent' and self.config.get('agent_package') == 'platform-11':
            # Build an explicit native package; never upload compatibility adapters
            # or the shared binary cache. Only the existing email gate is retained.
            stage = self.state.directory / 'agent-stage'
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir(mode=0o700)
            for name in ('AGENTS.md', 'Procfile'):
                shutil.copy2(source / name, stage / name)
            shutil.copytree(source / 'runtime', stage / 'runtime')
            (stage / 'bin').mkdir()
            shutil.copy2(ROOT / 'apps/agent/bin/oauth2-proxy', stage / 'bin/oauth2-proxy')
            if self.phase >= 4:
                skin = ROOT / 'apps/agent/branding'
                (stage / 'branding').mkdir()
                for name in ('style.css', 'logo.svg', 'favicon.svg'):
                    shutil.copy2(skin / name, stage / 'branding' / name)
            source = stage
            if app.get('metadata', {}).get('labels', {}).get('ai.tanzu.com/type') != 'agent':
                self.cf.api('/v3/apps/' + app['guid'], 'PATCH', {'metadata': {'labels': {**self.metadata()['labels'], 'ai.tanzu.com/type': 'agent'}}})
        # Binary app uploads contain only their executable and required SSO helper.
        if record['app'] in ('guide', 'hub-relay'):
            stage = self.state.directory / (record['app'] + '-stage')
            stage.mkdir(mode=0o700, exist_ok=True)
            shutil.copy2(source, stage / source.name)
            if record['app'] == 'guide':
                shutil.copy2(ROOT / 'apps/agent/bin/oauth2-proxy', stage / 'oauth2-proxy')
            source = stage
        source_hash = hashlib.sha256()
        for path in sorted(source.rglob('*')) if source.is_dir() else [source]:
            if path.is_file() and not any(part in ('.git', '__pycache__') for part in path.parts):
                source_hash.update(str(path.relative_to(source) if source.is_dir() else path.name).encode())
                source_hash.update(path.read_bytes())
                if record['app'] == 'agent' and self.config.get('agent_package') == 'platform-11':
                    source_hash.update(str(path.stat().st_mode & 0o111).encode())
        service_ids = self.app_service_ids(record)
        fingerprint = digest({'manifest': rendered, 'source': source_hash.hexdigest(), 'services': {key: self.state.data['resources'][key].get('fingerprint') for key in service_ids}})
        previous = self.state.data['resources'].get(record['id'], {})
        changed = previous.get('fingerprint') != fingerprint
        if changed:
            self.check_app_routes(app)  # Recheck immediately before cf push.
            manifest_path = self.state.write(record['id'] + '-manifest.json', rendered)
            self.cf.run(['push', record['name'], '-f', str(manifest_path), '-p', str(source), '--no-start'])
        self.ensure_routes(app, record)
        for key in service_ids:
            changed = self.ensure_binding(app, key) or changed
        if changed:
            # cf start stages the uploaded package only after broker bindings exist.
            self.cf.run(['restage' if app.get('state') == 'STARTED' else 'start', record['name']])
        elif app.get('state') != 'STARTED':
            self.cf.run(['start', record['name']])
        self.cf.wait_app(app['guid'])
        self.state.record(record['id'], 'apps', app, phase=record['phase'], fingerprint=fingerprint)

    def policy_present(self, source, destination, port):
        output = self.cf.run(['network-policies', '--source', source])
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 4 and fields[:4] == [source, destination, 'tcp', str(port)]:
                return True
        return False

    def ensure_policy(self, record):
        source, destination = self.names[record['source']], self.names[record['destination']]
        saved = self.state.data['resources'].get(record['id'])
        source_guid = self.state.data['resources'][record['source']]['guid']
        destination_guid = self.state.data['resources'][record['destination']]['guid']
        if saved and (saved['source_guid'] != source_guid or saved['destination_guid'] != destination_guid):
            raise CFError('policy endpoint GUID changed')
        if self.policy_present(source, destination, record['port']):
            if not saved:
                raise CFError('unowned network policy collision')
            return
        # Policy API has no metadata: record intent with owned endpoint GUIDs first.
        self.state.record(record['id'], 'policy', {'guid': record['id'], 'name': record['name']}, source=source, destination=destination, source_guid=source_guid, destination_guid=destination_guid, port=record['port'], phase=record['phase'])
        self.cf.run(['add-network-policy', source, destination, '--protocol', 'tcp', '--port', str(record['port'])])

    def deploy(self):
        self.preflight()
        if self.phase < self.state.data.get('phase', 0):
            raise CFError('cumulative downgrade requires reset; deploy only advances phases')
        self.state.data['identity'] = self.identity
        self.state.save()
        for record in self.records:
            if record['kind'] in ('service', 'credential', 'descriptor'):
                self.ensure_service(record)
            elif record['kind'] == 'app':
                self.ensure_app(record)
            elif record['kind'] == 'policy':
                self.ensure_policy(record)
        self.state.data['phase'] = max(self.phase, self.state.data.get('phase', 0))
        self.state.save()
        return {'status': 'deployed', 'phase': self.phase, 'omitted_scenes': omitted_scenes(self.config, self.phase)}

    def recover_owned_resources(self):
        """Recover creations committed remotely before their GUID was journaled."""
        if self.state.data.get('identity') != self.identity:
            # deploy persists identity before its first mutation. A fresh journal
            # cannot establish ownership of any previous installation.
            if self.state.data['resources']:
                raise CFError('recorded target identity is missing; cannot recover resources')
            return
        complete_config = dict(self.config, integrations={k: True for k in self.config['integrations']})
        complete = resolve(complete_config, 4)
        known = {self.target['prefix'] + '-' + r['id']: r for r in complete}
        recorded = {r['guid'] for r in self.state.data['resources'].values()}
        apps, services = {}, {}
        selector = OWNER + '=' + self.state.data['owner']
        for kind in ('apps', 'service_instances', 'routes'):
            for item in self.cf.list(kind, space_guids=self.identity['space_guid'], label_selector=selector):
                self.owned(kind, item)
                if item['relationships']['space']['data']['guid'] != self.identity['space_guid']:
                    raise CFError('recovery resource is outside the verified space')
                if kind == 'apps':
                    apps[item['guid']] = item
                elif kind == 'service_instances':
                    services[item['guid']] = item
                if item['guid'] in recorded:
                    continue
                component = known.get(item.get('name'), {})
                key = component.get('id', 'recovered:' + kind + ':' + item['guid'])
                if kind == 'routes':
                    key = 'route:' + item['url']
                self.owned(kind, item, key)
                self.state.record(key, kind, item, phase=component.get('phase', 0))
                recorded.add(item['guid'])
        service_keys = {r['guid']: key for key, r in self.state.data['resources'].items() if r['kind'] == 'service_instances'}
        for app_guid, app in apps.items():
            for item in self.cf.list('service_credential_bindings', app_guids=app_guid):
                if item.get('metadata', {}).get('labels', {}).get(OWNER) != self.state.data['owner']:
                    continue  # The attachment ownership gate below vetoes these.
                service_guid = item['relationships']['service_instance']['data']['guid']
                if service_guid not in services:
                    raise CFError('owned binding references a service outside the installation')
                if item['guid'] not in recorded:
                    key = app['name'] + ':' + service_keys[service_guid]
                    self.owned('binding', item, key)
                    self.state.record(key, 'service_credential_bindings', item, app_guid=app_guid, service_guid=service_guid)
                    recorded.add(item['guid'])

    def cleanup_preview(self, delete_data=False):
        self.verify_target()
        self.recover_owned_resources()
        # All recorded phases of this exact installation. Never use a name prefix
        # query as authority to delete; verify each recorded GUID and owner label.
        rows = []
        resources = self.state.data['resources']
        for key, saved in reversed(list(resources.items())):
            if saved['kind'] == 'service_instances' and not delete_data:
                continue
            if saved['kind'] == 'policy':
                for role in ('source', 'destination'):
                    item = self.cf.api('/v3/apps/' + saved[role + '_guid'])
                    self.owned('policy endpoint', item)
            else:
                found = self.cf.get(saved['kind'], saved['guid'])
                if found is None:
                    continue
                self.owned(saved['kind'], found, key)
                if saved['kind'] == 'apps':
                    self.check_app_routes(found)
                    # App deletion cascades its bindings, so veto unowned attachments.
                    for binding in self.cf.list('service_credential_bindings', app_guids=saved['guid']):
                        self.owned('binding attached to app', binding)
                if saved['kind'] == 'service_instances':
                    for binding in self.cf.list('service_credential_bindings', service_instance_guids=saved['guid']):
                        self.owned('binding attached to service', binding)
                if saved['kind'] == 'routes':
                    for destination in self.cf.api('/v3/routes/' + saved['guid'] + '/destinations').get('destinations', []):
                        self.owned('route destination', self.cf.api('/v3/apps/' + destination['app']['guid']))
            rows.append({'key': key, **saved})
        # Metadata records move when retried; use dependency kinds rather than dict
        # insertion order for cascading resources, then reverse topology within kind.
        rank = {'policy': 0, 'service_credential_bindings': 1, 'routes': 2, 'apps': 3, 'service_instances': 4}
        rows.sort(key=lambda r: (rank[r['kind']], -r.get('phase', 0)))
        return {'target': self.target, 'delete_data': delete_data, 'preserved_services': [r['name'] for r in resources.values() if r['kind'] == 'service_instances' and not delete_data], 'resources': rows}

    def cleanup(self, delete_data=False):
        preview = self.cleanup_preview(delete_data)
        for saved in preview['resources']:
            self.verify_target()
            if saved['kind'] == 'policy':
                if self.policy_present(saved['source'], saved['destination'], saved['port']):
                    self.cf.run(['remove-network-policy', saved['source'], saved['destination'], '--protocol', 'tcp', '--port', str(saved['port'])])
            else:
                found = self.cf.get(saved['kind'], saved['guid'])
                if found is not None:
                    self.owned(saved['kind'], found, saved['key'])
                    self.cf.api('/v3/' + saved['kind'] + '/' + saved['guid'], 'DELETE')
                    self.cf.wait_absent(saved['kind'], saved['guid'])
            self.state.data['resources'].pop(saved['key'], None)
            self.state.save()
        # Clear already-gone journal entries too, retaining consumer data by default.
        self.state.data['resources'] = {k: r for k, r in self.state.data['resources'].items() if r['kind'] == 'service_instances' and not delete_data}
        self.state.data['phase'] = 0
        self.state.save()
        return preview

    def reset(self, delete_data=False):
        self.preflight()  # Verify inputs before removing any app.
        self.cleanup(delete_data)
        return self.deploy()

    def validate(self):
        self.verify_target()
        self.check_integration_removal()
        checks = []
        def check(name, action):
            try:
                action()
                checks.append({'check': name, 'status': 'pass'})
            except (CFError, ConfigError) as error:
                checks.append({'check': name, 'status': 'fail', 'detail': str(error)})
        for record in self.records:
            if record['kind'] in ('service', 'credential', 'descriptor', 'app'):
                def inspect(record=record):
                    kind = 'apps' if record['kind'] == 'app' else 'service_instances'
                    item = self.lookup(kind, record)
                    if not item:
                        raise CFError('expected resource missing')
                    if kind == 'apps':
                        if item.get('state') != 'STARTED':
                            raise CFError('app is stopped')
                        self.cf.wait_app(item['guid'])
                        bindings = self.cf.list('service_credential_bindings', app_guids=item['guid'])
                        for key in self.app_service_ids(record):
                            wanted = self.state.data['resources'].get(key, {}).get('guid')
                            found = [b for b in bindings if b['relationships']['service_instance']['data']['guid'] == wanted]
                            if len(found) != 1:
                                raise CFError('expected binding missing: ' + key)
                            self.owned('binding', found[0])
                            self.cf.wait_binding(found[0]['guid'])
                    else:
                        self.cf.wait_service(item['guid'])
                check('resource:' + record['id'], inspect)
        def expect_status(url, accepted):
            status = self.probe(url)
            if status not in accepted:
                raise CFError(f'unexpected HTTP status {status}')
        public = 'https://' + self.names['agent'] + '.' + self.config['routes']['domain']
        check('agent-health', lambda: expect_status(public + '/health', {200}))
        check('anonymous-agent-api-denied', lambda: expect_status(public + '/api/chat', {302, 303, 307, 401, 403}))
        checks.append({'check': 'browser-sso-and-model', 'status': 'manual-required', 'detail': 'Prove allowed presenter login, denied identity, and a real model response in the browser.'})
        if self.phase >= 2:
            checks.append({'check': 'mcp-tool-invocation', 'status': 'manual-required', 'detail': 'Invoke each enabled tool and record returned evidence; catalog listing alone does not pass.'})
        if self.phase >= 3:
            checks.append({'check': 'memory-save-read', 'status': 'manual-required', 'detail': 'Save unique content, start a new conversation, retrieve it; bindings/proxy health alone do not pass.'})
        return {'checks': checks, 'omitted_scenes': omitted_scenes(self.config, self.phase), 'live_acceptance_complete': False}
