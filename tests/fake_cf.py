"""Stateful CF double: validates ordering and models remote ownership/inventory."""
import copy
import json
from pathlib import Path
from northstar_kit.cf import CF, CFError, CFHTTPError


class FakeCF(CF):
    def __init__(self, config):
        self.timeout = 1
        self.config = config
        self.current = dict(config['target'], org_guid='org-guid', space_guid='space-guid')
        self.inventory = {k: {} for k in ('apps', 'service_instances', 'service_credential_bindings', 'routes')}
        self.mutations, self.events, self.policies, self.deleted_guids = [], [], set(), []
        self.counter = 0
        self.fail_after_create = None
        self.fail_after_create_kind = None
        self.broker_failure = None
        self.missing_plan = None
        self.visibility = {'type': 'public'}
        self.manifests = {}
        self.target_switches = []
        self.quota_reads = []
        self.org_quota = {'guid': 'org-quota', 'apps': {'total_memory_in_mb': None, 'total_instances': None, 'per_process_memory_in_mb': None}, 'routes': {'total_routes': None}, 'services': {'total_service_instances': None, 'paid_services_allowed': True}}
        self.space_quota = copy.deepcopy(self.org_quota)
        self.space_quota['guid'] = 'space-quota'
        self.extra_usage = {scope: dict(memory_in_mb=0, started_instances=0, routes=0, service_instances=0) for scope in ('organizations', 'spaces')}


    def target_metadata(self):
        return copy.deepcopy(self.current)

    def list(self, kind, **query):
        if kind.startswith('apps/') and kind.endswith('/processes'):
            assert not query
            app = self.inventory['apps'][kind.split('/')[1]]
            spec = self.manifests[app['name']]['applications'][0]
            memory = spec['memory']
            return [{'guid': 'process-' + app['guid'], 'type': 'web', 'instances': spec['instances'], 'memory_in_mb': int(memory[:-1]) * (1024 if memory.endswith('G') else 1)}]
        if kind.startswith('apps/') and kind.endswith('/routes'):
            assert not query, 'unsupported fake app-routes query'
            guid = kind.split('/')[1]
            return [copy.deepcopy(r) for r in self.inventory['routes'].values() if any(d['app']['guid'] == guid for d in r['destinations'])]
        supported = {
            'organization_quotas': {'organization_guids'}, 'space_quotas': {'space_guids'},
            'apps': {'names', 'guids', 'space_guids', 'label_selector'},
            'service_instances': {'names', 'space_guids', 'label_selector'},
            'routes': {'hosts', 'space_guids', 'domain_guids', 'label_selector'},
            'service_credential_bindings': {'app_guids', 'service_instance_guids', 'label_selector'},
            'service_offerings': {'names'}, 'service_plans': {'names', 'service_offering_guids'},
            'buildpacks': set(), 'domains': {'names'}, 'spaces': {'names', 'organization_guids'},
        }
        unsupported = set(query) - supported[kind]
        if unsupported:
            raise CFHTTPError(400)
        if kind in ('organization_quotas', 'space_quotas'):
            self.quota_reads.append((kind, query))
            quota = self.org_quota if kind == 'organization_quotas' else self.space_quota
            return [copy.deepcopy(quota)] if quota else []
        if kind == 'service_offerings':
            return [{'guid': 'offering-' + query['names'], 'name': query['names']}]
        if kind == 'service_plans':
            if query['names'] == self.missing_plan:
                return []
            return [{'guid': 'plan-' + query['names'], 'name': query['names'], 'free': True}]
        if kind == 'buildpacks':
            return [{'name': v, 'enabled': True, 'state': 'READY'} for v in self.config['buildpacks'].values()]
        if kind == 'domains':
            return [{'guid': query['names'], 'name': query['names']}]
        if kind == 'spaces':
            return [{'guid': query['names'], 'name': query['names']}]
        result = []
        for value in self.inventory[kind].values():
            matches = True
            for key, wanted in query.items():
                if key == 'label_selector':
                    label, expected = wanted.split('=', 1)
                    actual = value.get('metadata', {}).get('labels', {}).get(label)
                    wanted = expected
                elif key in ('names', 'guids', 'hosts'):
                    actual = value.get({'names': 'name', 'guids': 'guid', 'hosts': 'host'}[key])
                else:
                    relation = key[:-6] if key.endswith('_guids') else key
                    actual = value.get('relationships', {}).get(relation, {}).get('data', {}).get('guid')
                matches = matches and actual == wanted
            if matches:
                result.append(copy.deepcopy(value))
        return result

    def api(self, path, method='GET', data=None):
        parts = path.strip('/').split('/')
        kind = parts[1]
        if kind in ('organizations', 'spaces') and parts[3:] == ['usage_summary']:
            assert method == 'GET'
            self.quota_reads.append(path)
            usage = copy.deepcopy(self.extra_usage[kind])
            for app in self.inventory['apps'].values():
                if app.get('state') == 'STARTED':
                    for process in self.list('apps/' + app['guid'] + '/processes'):
                        usage['memory_in_mb'] += process['memory_in_mb'] * process['instances']
                        usage['started_instances'] += process['instances']
            usage['routes'] += len(self.inventory['routes'])
            usage['service_instances'] += sum(s['type'] == 'managed' for s in self.inventory['service_instances'].values())
            return {'usage_summary': usage}
        if kind == 'service_plans':
            return copy.deepcopy(self.visibility)
        if len(parts) == 4 and parts[3] == 'destinations':
            route = self.inventory['routes'][parts[2]]
            if method == 'POST':
                self.mutations.append((method, path))
                route['destinations'].extend(copy.deepcopy(data['destinations']))
            return {'destinations': copy.deepcopy(route['destinations'])}
        if method == 'GET':
            if parts[2] not in self.inventory[kind]:
                raise CFHTTPError(404)
            return copy.deepcopy(self.inventory[kind][parts[2]])
        self.mutations.append((method, path))
        if method == 'POST':
            self.counter += 1
            value = copy.deepcopy(data)
            value['guid'] = 'resource-' + str(self.counter)
            value.setdefault('last_operation', {'state': 'succeeded'})
            if kind == 'apps':
                value['state'] = 'STOPPED'
            if kind == 'routes':
                value['destinations'] = []
                value['url'] = value['host'] + '.' + value['relationships']['domain']['data']['guid']
            if kind == 'service_instances' and value['name'].endswith('-gateway'):
                value['dashboard_url'] = 'https://discovered.gateway.test'
            if kind == 'service_credential_bindings':
                app = self.inventory['apps'][data['relationships']['app']['data']['guid']]
                if self.inventory['service_instances'][data['relationships']['service_instance']['data']['guid']]['name'].endswith('-sso'):
                    assert self.manifests[app['name']]['applications'][0]['env']['SSO_REDIRECT_URIS']
            self.inventory[kind][value['guid']] = value
            self.events.append(('create', kind, value.get('name')))
            if (self.fail_after_create and value.get('name') == self.fail_after_create) or kind == self.fail_after_create_kind:
                self.fail_after_create = None
                self.fail_after_create_kind = None
                raise CFError('simulated interrupted create after server commit')
            return copy.deepcopy(value)
        if method == 'PATCH':
            self.inventory[kind][parts[2]].update(copy.deepcopy(data))
            return copy.deepcopy(self.inventory[kind][parts[2]])
        if method == 'DELETE':
            guid = parts[2]
            self.deleted_guids.append(guid)
            del self.inventory[kind][guid]
            return {}
        raise AssertionError((path, method))

    def wait_service(self, guid):
        item = self.inventory['service_instances'][guid]
        if item['name'] == self.broker_failure:
            raise CFError('broker operation failed (details suppressed)')
        return copy.deepcopy(item)

    def wait_binding(self, guid):
        return copy.deepcopy(self.inventory['service_credential_bindings'][guid])

    def wait_app(self, guid):
        assert self.inventory['apps'][guid]['state'] == 'STARTED'

    def run(self, args, sensitive=False):
        command = args[0]
        if command == 'target':
            self.current['space'] = args[2]
            self.current['space_guid'] = args[2]
            self.target_switches.append(args[2])
        elif command == 'network-policies':
            return '\n'.join(f'{s} {d} tcp {p}' for s, d, p in sorted(self.policies))
        elif command in ('add-network-policy', 'remove-network-policy'):
            self.mutations.append(tuple(args))
            policy = (args[1], args[2], int(args[-1]))
            if command == 'add-network-policy':
                self.policies.add(policy)
            else:
                self.policies.discard(policy)
        elif command == 'push':
            self.mutations.append(tuple(args))
            self.manifests[args[1]] = json.loads(Path(args[args.index('-f') + 1]).read_text())
            self.events.append(('push', args[1]))
            app = next(a for a in self.inventory['apps'].values() if a['name'] == args[1])
            if self.manifests[args[1]]['applications'][0].get('no-route'):
                for route in self.inventory['routes'].values():
                    route['destinations'] = [d for d in route['destinations'] if d['app']['guid'] != app['guid']]
            if args[1].endswith('github-mcp'):
                assert sorted(p.name for p in Path(args[args.index('-p') + 1]).iterdir()) == ['github-mcp-server']
        elif command in ('start', 'restage'):
            self.mutations.append(tuple(args))
            app = next(a for a in self.inventory['apps'].values() if a['name'] == args[1])
            bound = [b for b in self.inventory['service_credential_bindings'].values() if b['relationships']['app']['data']['guid'] == app['guid']]
            assert bound, 'application started before service bindings'
            app['state'] = 'STARTED'
            self.events.append(('start', args[1]))
        else:
            raise AssertionError(args)
        return ''
