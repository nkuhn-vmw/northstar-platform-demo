"""Native phase closure for one dedicated installation."""
import json
from .config import ROOT, target_for


def resolve(config: dict, phase: int, mode: str = 'cumulative') -> list[dict]:
    if phase not in range(1, 5):
        raise ValueError('phase must be 1..4')
    prefix = target_for(config, phase, mode)['prefix']
    records = json.loads((ROOT / 'deploy/topology.json').read_text())
    selected = {r['id']: r for r in records if r['phase'] <= phase and
                (not r.get('integration') or config['integrations'][r['integration']])}
    if 'hub-descriptor' in selected:
        selected['hub-oauth'] = {'id': 'hub-oauth', 'kind': 'credential', 'phase': 2,
                                 'depends_on': ['gateway'], 'integration': 'hub',
                                 'secret': 'hub_oauth', 'user_provided': True,
                                 'bind_to_apps': False}
        selected['hub-relay'] = {'id': 'hub-relay', 'kind': 'app', 'phase': 2,
                                'depends_on': ['hub-oauth', 'gateway'],
                                'integration': 'hub', 'app': 'hub-relay'}
        selected['hub-descriptor']['backend'] = 'hub-relay'
        selected['hub-descriptor']['depends_on'].append('hub-relay')
    if phase >= 3:
        selected['credential-store'] = {'id': 'credential-store', 'kind': 'service',
                                        'phase': 3, 'depends_on': [],
                                        'service': 'credential_store'}
    selected['agent']['depends_on'] += [key for key in selected if
        key.endswith('-descriptor') or key in ('memory', 'credential-store')]
    ordered, visiting = [], set()

    def visit(key):
        if any(r['id'] == key for r in ordered):
            return
        if key in visiting or key not in selected:
            raise ValueError(f'invalid dependency {key}')
        visiting.add(key)
        for dependency in selected[key]['depends_on']:
            visit(dependency)
        record = selected[key]
        record['name'] = f'{prefix}-{key}'
        ordered.append(record)
        visiting.remove(key)

    for key in selected:
        visit(key)
    return ordered


def omitted_scenes(config, phase):
    return ['hub: tool scene omitted by explicit integration flag'] if phase >= 2 and not config['integrations']['hub'] else []
