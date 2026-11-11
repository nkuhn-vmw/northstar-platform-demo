import json
import tempfile
import unittest
from northstar_kit.config import ROOT, target_for
from northstar_kit.topology import resolve, omitted_scenes
from northstar_kit.lifecycle import plan
from test_config import profile


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = profile(self.tmp.name)

    def test_unique_and_dependency_order_for_every_phase(self):
        raw = json.loads((ROOT / 'deploy/topology.json').read_text())
        self.assertEqual(len(raw), len({r['id'] for r in raw}))
        for phase in range(1, 5):
            records = resolve(self.config, phase)
            ids = [r['id'] for r in records]
            self.assertEqual(len(ids), len(set(ids)))
            for record in records:
                for dependency in record['depends_on']:
                    self.assertLess(ids.index(dependency), ids.index(record['id']))
        ids = [r['id'] for r in resolve(self.config, 2)]
        self.assertLess(ids.index('market'), ids.index('market-descriptor'))
        self.assertLess(ids.index('market-descriptor'), ids.index('agent'))

    def test_phase_closure_independent_space_and_names(self):
        for phase in range(1, 5):
            cumulative = resolve(self.config, phase)
            isolated = resolve(self.config, phase, 'phase-spaces')
            self.assertEqual([r['id'] for r in cumulative], [r['id'] for r in isolated])
            self.assertTrue(all(r['name'].startswith(f'demo-p{phase}-') for r in isolated))
            self.assertEqual(target_for(self.config, phase, 'phase-spaces')['space'], f'demo-space-phase{phase}')

    def test_reduced_profile_is_explicit(self):
        self.config['integrations'] = {key: False for key in self.config['integrations']}
        ids = [r['id'] for r in resolve(self.config, 2)]
        self.assertIn('market', ids)
        self.assertNotIn('credhub-mcp', ids)
        self.assertEqual(len(omitted_scenes(self.config, 2)), 1)

    def test_render_has_sso_before_binding_and_no_secret_values(self):
        output = plan(self.config, 4)
        env = output['manifests']['agent']['applications'][0]['env']
        self.assertEqual(env['SSO_IDENTITY_PROVIDERS'], 'corp')
        self.assertIn('/**', env['SSO_REDIRECT_URIS'])
        self.assertFalse(any('-s-s-s' in str(v) for v in output.values()))

    def test_market_platform_metadata_reports_cloud_foundry_in_both_space_modes(self):
        for mode in ('cumulative', 'phase-spaces'):
            for phase in range(2, 5):
                with self.subTest(mode=mode, phase=phase):
                    manifests = plan(self.config, phase, mode)['manifests']
                    market = manifests['market']['applications'][0]
                    self.assertEqual(market['env']['NORTHSTAR_DEPLOYMENT_MODE'], 'cloud-foundry')
                    self.assertEqual(market['env']['SPRING_PROFILES_ACTIVE'], 'cloud')
                    self.assertFalse(any(key.startswith('VCAP_') for key in market['env']))
                    for app, manifest in manifests.items():
                        if app != 'market':
                            self.assertNotIn('NORTHSTAR_DEPLOYMENT_MODE', manifest['applications'][0]['env'])

    def test_guide_uses_resolved_target_and_only_sso_dependency(self):
        for mode in ('cumulative', 'phase-spaces'):
            output = plan(self.config, 4, mode)
            guide = output['manifests']['guide']['applications'][0]
            self.assertEqual(guide['env']['GUIDE_SPACE'], output['target']['space'])
            self.assertEqual(guide['env']['GUIDE_BASE_URL'], 'https://' + guide['name'] + '.' + self.config['routes']['domain'])
            self.assertIn('/demo' + ('-p4' if mode == 'phase-spaces' else '') + '-market/mcp', guide['env']['GUIDE_MARKET_MCP_URL'])
