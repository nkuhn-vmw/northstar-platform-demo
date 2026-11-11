import copy
import shutil
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from northstar_kit.cf import CF, CFError
from northstar_kit.config import ROOT, target_for
from northstar_kit.lifecycle import Lifecycle, OWNER
from northstar_kit.state import State
from fake_cf import FakeCF
from test_config import profile


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = profile(self.tmp.name)
        # Behavioral orchestration tests need no downloads or prepared binaries.
        from northstar_kit.render import APP_PATHS
        asset_root = Path(self.tmp.name) / 'assets'
        for app, relative in APP_PATHS.items():
            asset = asset_root / relative
            if app in ('agent', 'reviewer', 'security', 'router'):
                asset.mkdir(parents=True)
                shutil.copytree(ROOT / 'apps/agent', asset, dirs_exist_ok=True, ignore=shutil.ignore_patterns('bin'))
            else:
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text('fixture-binary')
        proxy = asset_root / 'apps/agent/bin/oauth2-proxy'
        proxy.parent.mkdir(parents=True, exist_ok=True)
        proxy.write_text('fixture-proxy')
        root_patch = patch('northstar_kit.lifecycle.ROOT', asset_root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        assets_patch = patch('northstar_kit.lifecycle.assets', return_value=[asset_root])
        assets_patch.start()
        self.addCleanup(assets_patch.stop)
        integrity_patch = patch('northstar_kit.lifecycle.verify_prepared_assets')
        self.integrity = integrity_patch.start()
        self.addCleanup(integrity_patch.stop)
        self.cf = FakeCF(self.config)
        self.state = State(Path(self.tmp.name) / 'state', self.config['target'])
        self.lock = self.state.locked()
        self.lock.__enter__()
        self.addCleanup(self.lock.__exit__, None, None, None)

    def lifecycle(self, phase=4):
        return Lifecycle(self.config, phase, 'cumulative', self.cf, self.state, probe=lambda url, **kwargs: 401 if kwargs.get('method') == 'POST' else 200 if url.endswith('/health') else 302)

    def test_preflight_rejects_invalid_artifacts_before_remote_mutation(self):
        self.integrity.side_effect = CFError('prepared artifact verification failed')
        with self.assertRaisesRegex(CFError, 'artifact verification failed'):
            self.lifecycle().deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_native_stack_and_buildpack_are_checked_before_provisioning(self):
        self.cf.missing_stack = True
        with self.assertRaisesRegex(CFError, 'required stack missing'):
            self.lifecycle().deploy()
        self.assertEqual(self.cf.mutations, [])
        self.cf.missing_stack = False
        self.cf.buildpack_stack = 'incompatible-stack'
        with self.assertRaisesRegex(CFError, 'incompatible with stack'):
            self.lifecycle().deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_native_memory_and_credential_store_bind_without_publisher_adapter(self):
        self.config['buildpacks']['agent'] = 'agent_buildpack'
        self.config['services']['memory'] = {'offering': 'agent-memory', 'plan': 'memory'}
        self.config['services']['credential_store'] = {'offering': 'credential-store', 'plan': 'shared'}
        self.cf = FakeCF(self.config)
        self.lifecycle(3).deploy()
        resources = self.state.data['resources']
        native_memory = self.cf.inventory['service_instances'][resources['memory']['guid']]
        self.assertEqual(native_memory['tags'], ['tanzu-agent-memory'])
        store = self.cf.inventory['service_instances'][resources['credential-store']['guid']]
        self.assertEqual(store['tags'], ['credential-store'])
        bindings = self.cf.list('service_credential_bindings', app_guids=resources['agent']['guid'])
        service_guids = {b['relationships']['service_instance']['data']['guid'] for b in bindings}
        self.assertIn(resources['credential-store']['guid'], service_guids)
        self.assertIn(resources['memory']['guid'], service_guids)
        env = self.cf.manifests[resources['agent']['name']]['applications'][0]['env']
        self.assertEqual(env['TANZU_AGENT_MEMORY_SERVICE_TAG'], 'tanzu-agent-memory')
        self.assertEqual(env['TANZU_AGENT_MEMORY_IDENTITY_MODE'], 'user')

    def test_platform11_package_stages_only_native_assets_and_reconciles_idempotently(self):
        self.lifecycle(1).deploy()
        stage = self.state.directory / 'agent-stage'
        self.assertEqual({p.name for p in stage.iterdir()}, {'AGENTS.md', 'Procfile', 'runtime', 'bin'})
        self.assertEqual({p.name for p in (stage / 'bin').iterdir()}, {'oauth2-proxy'})
        self.assertTrue(os.access(stage / 'runtime/launch-agent.sh', os.X_OK))
        self.lifecycle(4).deploy()
        self.assertEqual({p.name for p in (stage / 'branding').iterdir()}, {'style.css', 'logo.svg', 'favicon.svg'})
        manifest = json.loads((self.state.directory / 'agent-manifest.json').read_text())['applications'][0]
        self.assertEqual(manifest['stack'], 'tanzucflinuxfs1')
        self.assertEqual(manifest['env']['SSO_SCOPES'], 'openid,roles')
        self.assertEqual(manifest['env']['TANZU_AGENT_AUTH_OAUTH_SCOPES'], 'openid')
        self.assertEqual(manifest['env']['TANZU_AGENT_MEMORY_IDENTITY_MODE'], 'user')
        self.assertNotIn('TANZU_AGENT_BRANDING_PATH', manifest['env'])
        self.assertEqual(self.cf.inventory['apps'][self.state.data['resources']['agent']['guid']]['metadata']['labels']['ai.tanzu.com/type'], 'agent')
        mutations = len(self.cf.mutations)
        self.lifecycle(4).deploy()
        self.assertEqual(len(self.cf.mutations), mutations)

    def test_hub_oauth_route_uses_internal_relay_and_private_client(self):
        import shutil
        from northstar_kit import lifecycle
        self.config['agent_package'] = 'platform-11'
        self.config['services']['memory'] = {'offering': 'agent-memory', 'plan': 'memory'}
        self.config['services']['credential_store'] = {'offering': 'credential-store', 'plan': 'shared'}
        self.config['integrations']['hub'] = True
        self.config['hub']['auth_mode'] = 'gateway-oauth'
        path = Path(self.config['credentials']['hub_oauth'])
        credential = json.loads(path.read_text())
        credential.update(authorization_endpoint='https://hub.foundation.test/authorize', token_endpoint='https://hub.foundation.test/token')
        credential['redirect_uri'] = 'https://discovered.gateway.test/demo-hub-relay/auth/callback'
        path.write_text(json.dumps(credential))
        self.cf = FakeCF(self.config)
        # Exactly seven managed services fit; the Hub OAuth UPS consumes no quota.
        self.cf.org_quota['services']['total_service_instances'] = 7
        from northstar_kit.config import ConfigError
        with self.assertRaisesRegex(ConfigError, 'phase 3 or later'):
            self.lifecycle(2).deploy()
        self.lifecycle(4).deploy()
        resources = self.state.data['resources']
        descriptor = self.cf.inventory['service_instances'][resources['hub-descriptor']['guid']]
        self.assertEqual(descriptor['credentials']['url'], 'https://discovered.gateway.test/demo-hub-relay/mcp')
        oauth = self.cf.inventory['service_instances'][resources['hub-oauth']['guid']]
        self.assertEqual(oauth['type'], 'user-provided')
        self.assertEqual(oauth['credentials']['extra_token_params'], {'resource': self.config['hub']['mcp_url']})
        gateway = self.cf.inventory['service_instances'][resources['gateway']['guid']]
        self.assertEqual(gateway['parameters']['mcp-servers'], [])
        bindings = self.cf.list('service_credential_bindings', app_guids=resources['hub-relay']['guid'])
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]['parameters']['auth'], {'service-instance': {'type': 'OAUTH', 'name': 'demo-hub-oauth'}})
        self.assertEqual(bindings[0]['relationships']['service_instance']['data']['guid'], resources['gateway']['guid'])
        report = self.lifecycle(4).validate()
        self.assertFalse([c for c in report['checks'] if c['status'] == 'fail'], report)
        from northstar_kit.render import routes
        self.assertEqual(routes(self.config, 'demo-hub-relay', 'hub-relay'), [('demo-hub-relay', self.config['routes']['internal_domain'])])
        mutations = len(self.cf.mutations)
        self.lifecycle(4).deploy()
        self.assertEqual(len(self.cf.mutations), mutations)
        credential['redirect_uri'] = 'https://wrong.gateway.test/callback'
        path.write_text(json.dumps(credential))
        with self.assertRaisesRegex(CFError, 'callback does not match'):
            self.lifecycle(4).deploy()
        self.assertEqual(len(self.cf.mutations), mutations)

    def test_existing_compatible_agent_cannot_switch_to_native_package(self):
        self.lifecycle(1).deploy()
        app = self.cf.inventory['apps'][self.state.data['resources']['agent']['guid']]
        app['metadata']['labels']['northstar-kit-package'] = 'compatible'
        mutations = len(self.cf.mutations)
        with self.assertRaisesRegex(CFError, 'cannot switch an existing agent package'):
            self.lifecycle(1).deploy()
        self.assertEqual(len(self.cf.mutations), mutations)



    def test_guide_binds_only_sso_and_stages_no_credentials(self):
        self.lifecycle(4).deploy()
        resources = self.state.data['resources']
        bindings = self.cf.list('service_credential_bindings', app_guids=resources['guide']['guid'])
        self.assertEqual([b['relationships']['service_instance']['data']['guid'] for b in bindings], [resources['sso']['guid']])
        self.assertEqual({p.name for p in (self.state.directory / 'guide-stage').iterdir()}, {'demo-guide-server', 'oauth2-proxy'})

    def test_complete_deploy_is_idempotent_and_gateway_ordered(self):
        self.lifecycle().deploy()
        first = copy.deepcopy(self.cf.inventory)
        mutations = len(self.cf.mutations)
        self.lifecycle().deploy()
        self.assertEqual(first, self.cf.inventory)
        self.assertEqual(mutations, len(self.cf.mutations))
        self.assertEqual(len(self.cf.policies), 0)
        market_started = self.cf.events.index(('start', 'demo-market'))
        descriptor_created = self.cf.events.index(('create', 'service_instances', 'demo-market-descriptor'))
        self.assertLess(market_started, descriptor_created)
        descriptor = next(s for s in first['service_instances'].values() if s['name'] == 'demo-market-descriptor')
        self.assertEqual(descriptor['credentials']['url'], 'https://discovered.gateway.test/demo-market/mcp')

    def test_wrong_target_rejected_before_mutation(self):
        for key in ('api', 'org', 'space'):
            previous = self.cf.current[key]
            self.cf.current[key] = 'wrong'
            with self.assertRaises(CFError):
                self.lifecycle(1).deploy()
            self.cf.current[key] = previous
        self.assertEqual(self.cf.mutations, [])

    def test_missing_plan_and_org_restricted_access(self):
        self.cf.missing_plan = 'memory'
        with self.assertRaises(CFError):
            self.lifecycle().deploy()
        self.assertEqual(self.cf.mutations, [])
        self.cf.missing_plan = None
        self.cf.visibility = {'type': 'organization', 'organizations': [{'guid': 'another-org'}]}
        with self.assertRaises(CFError):
            self.lifecycle(1).deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_name_collision_is_preflight_failure(self):
        self.cf.inventory['apps']['unowned'] = {'name': 'demo-market', 'guid': 'unowned', 'relationships': {'space': {'data': {'guid': 'space-guid'}}}}
        with self.assertRaisesRegex(CFError, 'unowned'):
            self.lifecycle(2).deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_interrupted_create_recovers_by_atomic_owner_label(self):
        self.cf.fail_after_create = 'demo-model'
        with self.assertRaises(CFError):
            self.lifecycle(1).deploy()
        self.assertNotIn('model', self.state.data['resources'])
        self.lifecycle(1).deploy()
        self.assertEqual(len([s for s in self.cf.inventory['service_instances'].values() if s['name'] == 'demo-model']), 1)
        self.assertEqual(len(self.cf.inventory['apps']), 1)

    def test_partial_broker_failure_does_not_start_consumer(self):
        self.cf.broker_failure = 'demo-gateway'
        with self.assertRaises(CFError):
            self.lifecycle(2).deploy()
        self.assertNotIn(('start', 'demo-agent'), self.cf.events)
        self.assertIn('gateway', self.state.data['resources'])
        self.cf.broker_failure = None
        self.lifecycle(2).deploy()
        self.assertIn(('start', 'demo-agent'), self.cf.events)

    def test_cleanup_preserves_services_and_never_deletes_unowned(self):
        lifecycle = self.lifecycle(2)
        lifecycle.deploy()
        services = copy.deepcopy(self.cf.inventory['service_instances'])
        self.cf.inventory['apps']['unowned'] = {'name': 'someone-elses-app', 'guid': 'unowned', 'relationships': {'space': {'data': {'guid': 'space-guid'}}}}
        preview = lifecycle.cleanup_preview()
        self.assertNotIn('unowned', [r['guid'] for r in preview['resources']])
        lifecycle.cleanup()
        self.assertEqual(services, self.cf.inventory['service_instances'])
        self.assertNotIn('unowned', self.cf.deleted_guids)
        self.assertEqual(set(self.cf.inventory['apps']), {'unowned'})
        lifecycle.cleanup(delete_data=True)
        self.assertEqual(self.cf.inventory['service_instances'], {})

    def test_cleanup_refuses_replaced_guid_or_unowned_attachment(self):
        lifecycle = self.lifecycle(1)
        lifecycle.deploy()
        guid = self.state.data['resources']['agent']['guid']
        self.cf.inventory['apps'][guid]['metadata']['labels'][OWNER] = 'another-installation'
        mutations = len(self.cf.mutations)
        with self.assertRaises(CFError):
            lifecycle.cleanup()
        self.assertEqual(mutations, len(self.cf.mutations))

    def test_phase_space_standalone_and_default_context_untouched(self):
        target = target_for(self.config, 3, 'phase-spaces')
        state = State(Path(self.tmp.name) / 'state', target)
        with state.locked():
            lifecycle = Lifecycle(self.config, 3, 'phase-spaces', self.cf, state, probe=lambda url: 200)
            lifecycle.deploy()
            self.assertTrue(all(a['name'].startswith('demo-p3-') for a in self.cf.inventory['apps'].values()))
            self.assertIn('memory', state.data['resources'])
            self.assertEqual(self.cf.target_switches, ['demo-space-phase3'])

    def test_cumulative_upgrade_refreshes_consumer_without_duplicate_bindings(self):
        self.lifecycle(1).deploy()
        first_guid = self.state.data['resources']['agent']['guid']
        self.lifecycle(3).deploy()
        self.assertEqual(first_guid, self.state.data['resources']['agent']['guid'])
        bound = self.cf.list('service_credential_bindings', app_guids=first_guid)
        self.assertEqual(len(bound), len({b['relationships']['service_instance']['data']['guid'] for b in bound}))
        self.assertEqual(self.cf.manifests['demo-agent']['applications'][0]['env']['TANZU_AGENT_MEMORY_NATIVE_TOOLS'], 'true')

    def test_validation_honestly_retains_manual_evidence(self):
        self.lifecycle().deploy()
        result = self.lifecycle().validate()
        self.assertFalse(result['live_acceptance_complete'])
        checks = {c['check']: c['status'] for c in result['checks']}
        self.assertEqual(checks['mcp-tool-invocation'], 'manual-required')
        self.assertEqual(checks['memory-save-read'], 'manual-required')
        self.assertEqual(checks['anonymous-agent-api-denied'], 'pass')

    def test_reset_preserves_service_guids(self):
        lifecycle = self.lifecycle(1)
        lifecycle.deploy()
        before = set(self.cf.inventory['service_instances'])
        app = self.state.data['resources']['agent']['guid']
        lifecycle.reset()
        self.assertEqual(before, set(self.cf.inventory['service_instances']))
        self.assertNotEqual(app, self.state.data['resources']['agent']['guid'])

    def test_transport_redacts_and_uses_private_payload_file(self):
        sentinel = 'sensitive-sentinel-do-not-print'
        cf = CF()
        seen = []
        def fake_run(args, **kwargs):
            seen.append(args)
            self.assertNotIn(sentinel, ' '.join(args))
            payload = Path(args[args.index('-d') + 1][1:])
            self.assertEqual(payload.stat().st_mode & 0o777, 0o600)
            self.assertIn(sentinel, payload.read_text())
            return subprocess.CompletedProcess(args, 1, stdout=sentinel, stderr=sentinel)
        with patch('subprocess.run', side_effect=fake_run):
            with self.assertRaises(CFError) as caught:
                cf.api('/v3/service_instances', 'POST', {'secret': sentinel})
        self.assertNotIn(sentinel, str(caught.exception))
        self.assertFalse(Path(seen[0][seen[0].index('-d') + 1][1:]).exists())

    def test_http_and_async_errors_cannot_leak(self):
        cf = CF()
        with patch.object(cf, 'run', return_value='HTTP/1.1 422 Unprocessable Entity\r\n\r\n{"errors":[{"detail":"secret"}]}'):
            with self.assertRaises(CFError) as caught:
                cf.api('/v3/apps', 'POST', {})
            self.assertNotIn('secret', str(caught.exception))
        responses = ['HTTP/1.1 202 Accepted\r\nLocation: https://api.test/v3/jobs/job-guid\r\n\r\n', 'HTTP/1.1 200 OK\r\n\r\n{"state":"COMPLETE"}']
        with patch.object(cf, 'run', side_effect=responses) as run:
            self.assertEqual(cf.api('/v3/service_instances', 'POST', {}), {})
            self.assertIn('/v3/jobs/job-guid', run.call_args.args[0])

    def test_secret_rotation_rebinds_even_after_service_update_interruption(self):
        self.config['integrations']['hub'] = True
        self.lifecycle().deploy()
        app_guid = self.state.data['resources']['hub-relay']['guid']
        gateway_guid = self.state.data['resources']['gateway']['guid']
        old_binding = self.cf.list('service_credential_bindings', app_guids=app_guid, service_instance_guids=gateway_guid)[0]['guid']
        secret = Path(self.config['credentials']['hub_oauth'])
        data = json.loads(secret.read_text())
        data['client_secret'] = 'rotated-sensitive-synthetic-token'
        secret.write_text(json.dumps(data))
        update = self.lifecycle()
        update.preflight()
        update.ensure_service(update.by_id['gateway'])
        update.ensure_service(update.by_id['hub-oauth'])
        self.lifecycle().deploy()
        new_binding = self.cf.list('service_credential_bindings', app_guids=app_guid, service_instance_guids=gateway_guid)[0]['guid']
        self.assertNotEqual(old_binding, new_binding)
        for file in self.state.directory.rglob('*.json'):
            self.assertNotIn(data['client_secret'], file.read_text())

    def test_cleanup_vetoes_unowned_binding_before_deleting_anything(self):
        lifecycle = self.lifecycle(1)
        lifecycle.deploy()
        binding = next(iter(self.cf.inventory['service_credential_bindings'].values()))
        binding['metadata']['labels'][OWNER] = 'someone-else'
        mutations = len(self.cf.mutations)
        with self.assertRaises(CFError):
            lifecycle.cleanup(delete_data=True)
        self.assertEqual(mutations, len(self.cf.mutations))

    def test_downgrade_requires_explicit_reset(self):
        self.lifecycle(3).deploy()
        mutations = len(self.cf.mutations)
        with self.assertRaisesRegex(CFError, 'downgrade'):
            self.lifecycle(1).deploy()
        self.assertEqual(mutations, len(self.cf.mutations))

    def test_real_cf_home_is_copied_privately_and_not_modified(self):
        original = Path(self.tmp.name) / 'cf-home'
        (original / '.cf').mkdir(parents=True)
        config = original / '.cf/config.json'
        original_contents = json.dumps({'Target': 'https://api.foundation.test', 'AccessToken': 'private-token'})
        config.write_text(original_contents)
        cf = CF(home=original)
        with cf.isolated():
            copied = Path(cf.home) / '.cf/config.json'
            self.assertNotEqual(copied, config)
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
            copied.write_text('{}')
        self.assertEqual(config.read_text(), original_contents)

    def test_sso_change_rebinds_after_new_environment(self):
        self.lifecycle(1).deploy()
        app_guid = self.state.data['resources']['agent']['guid']
        sso_guid = self.state.data['resources']['sso']['guid']
        before = self.cf.list('service_credential_bindings', app_guids=app_guid, service_instance_guids=sso_guid)[0]['guid']
        self.config['sso']['agent_scopes'] = 'openid'
        self.config['sso']['allowed_emails'] = ['another@corp.test']
        self.config['sso']['allow_unverified_email'] = True
        self.lifecycle(1).deploy()
        self.assertEqual(self.cf.list('service_credential_bindings', app_guids=app_guid, service_instance_guids=sso_guid)[0]['guid'], before)
        self.config['sso']['identity_provider'] = 'second-corp'
        self.lifecycle(1).deploy()
        after = self.cf.list('service_credential_bindings', app_guids=app_guid, service_instance_guids=sso_guid)[0]['guid']
        self.assertNotEqual(before, after)
        self.assertEqual(self.cf.manifests['demo-agent']['applications'][0]['env']['SSO_IDENTITY_PROVIDERS'], 'second-corp')

    def test_specific_guid_get_and_delete_wait_only_accept_explicit_404(self):
        from northstar_kit.cf import CFHTTPError
        cf = CF(timeout=1)
        for kind in ('apps', 'routes', 'service_instances', 'service_credential_bindings'):
            with self.subTest(kind=kind):
                responses = ['HTTP/1.1 200 OK\r\n\r\n{"guid":"owned-guid"}', 'HTTP/1.1 404 Not Found\r\n\r\n{"errors":[{"detail":"private"}]}']
                with patch.object(cf, 'run', side_effect=responses) as run, patch('northstar_kit.cf.time.sleep'):
                    cf.wait_absent(kind, 'owned-guid')
                    self.assertTrue(all(call.args[0][1] == '/v3/' + kind + '/owned-guid' for call in run.call_args_list))
        for status in (403, 500):
            with patch.object(cf, 'run', return_value=f'HTTP/1.1 {status} Failure\r\n\r\n{{}}'):
                with self.assertRaises(CFHTTPError) as caught:
                    cf.get('routes', 'guid')
                self.assertEqual(caught.exception.status, status)
        for kind in ('routes', 'service_instances'):
            with self.assertRaises(CFHTTPError):
                self.cf.list(kind, guids='unsupported')
            with self.assertRaises(CFHTTPError):
                self.cf.list(kind, invented_filter='unsupported')

    def test_cleanup_recovers_each_unjournaled_creation_without_redeploy(self):
        for kind in ('service_instances', 'apps', 'routes', 'service_credential_bindings'):
            with self.subTest(kind=kind):
                self.cf = FakeCF(self.config)
                self.state.data['resources'] = {}
                self.state.data.pop('phase', None)
                self.state.save()
                self.cf.fail_after_create_kind = kind
                with self.assertRaisesRegex(CFError, 'interrupted create'):
                    self.lifecycle(1).deploy()
                remote_guids = {guid for items in self.cf.inventory.values() for guid in items}
                journal_guids = {r['guid'] for r in self.state.data['resources'].values()}
                self.assertTrue(remote_guids - journal_guids)
                mutations = len(self.cf.mutations)
                preview = self.lifecycle(1).cleanup_preview(True)
                self.assertEqual(mutations, len(self.cf.mutations), 'preview must not mutate CF')
                self.assertEqual({r['guid'] for r in preview['resources']}, remote_guids)
                self.lifecycle(1).cleanup(True)
                self.assertTrue(all(not items for items in self.cf.inventory.values()))

    def test_recovered_services_are_preserved_by_default_and_scoped_to_identity(self):
        self.cf.fail_after_create = 'demo-model'
        with self.assertRaises(CFError):
            self.lifecycle(1).deploy()
        owned = next(iter(self.cf.inventory['service_instances'].values()))
        another_owner = copy.deepcopy(owned)
        another_owner.update(guid='another-owner', name='demo-other')
        another_owner['metadata']['labels'][OWNER] = 'different-owner'
        self.cf.inventory['service_instances']['another-owner'] = another_owner
        another_space = copy.deepcopy(owned)
        another_space.update(guid='another-space', name='demo-outside')
        another_space['relationships']['space']['data']['guid'] = 'different-space'
        self.cf.inventory['service_instances']['another-space'] = another_space
        preview = self.lifecycle(1).cleanup_preview()
        self.assertEqual(preview['preserved_services'], ['demo-model'])
        self.lifecycle(1).cleanup()
        self.assertEqual(set(self.cf.inventory['service_instances']), {owned['guid'], 'another-owner', 'another-space'})
        self.lifecycle(1).cleanup(True)
        self.assertEqual(set(self.cf.inventory['service_instances']), {'another-owner', 'another-space'})

    def test_cleanup_recovery_rejects_replaced_space_identity(self):
        self.cf.fail_after_create = 'demo-model'
        with self.assertRaises(CFError):
            self.lifecycle(1).deploy()
        self.cf.current['space_guid'] = 'replacement-space'
        mutations = len(self.cf.mutations)
        with self.assertRaisesRegex(CFError, 'GUID changed'):
            self.lifecycle(1).cleanup(True)
        self.assertEqual(mutations, len(self.cf.mutations))

    def test_changed_deploy_vetoes_unowned_and_shared_attached_routes(self):
        self.lifecycle(1).deploy()
        app_guid = self.state.data['resources']['agent']['guid']
        self.config['models']['interactive'] = 'updated-model'
        for shared in (False, True):
            with self.subTest(shared=shared):
                route = {'guid': 'extra-route', 'host': 'extra', 'url': 'extra.apps.foundation.test', 'metadata': {'labels': {OWNER: self.state.data['owner'] if shared else 'another-owner'}}, 'relationships': {'space': {'data': {'guid': 'space-guid'}}, 'domain': {'data': {'guid': 'apps.foundation.test'}}}, 'destinations': [{'app': {'guid': app_guid}}]}
                if shared:
                    route['destinations'].append({'app': {'guid': 'other-app'}})
                self.cf.inventory['routes']['extra-route'] = route
                before = copy.deepcopy(self.cf.inventory)
                mutations = len(self.cf.mutations)
                with self.assertRaisesRegex(CFError, 'route attached'):
                    self.lifecycle(1).deploy()
                self.assertEqual(before, self.cf.inventory)
                self.assertEqual(mutations, len(self.cf.mutations))
                del self.cf.inventory['routes']['extra-route']

    def test_fake_push_models_no_route_unmapping(self):
        self.lifecycle(1).deploy()
        app_guid = self.state.data['resources']['agent']['guid']
        self.assertTrue(self.cf.list(f'apps/{app_guid}/routes'))
        push = next(call for call in self.cf.mutations if call[0] == 'push')
        self.cf.run(list(push))
        self.assertEqual(self.cf.list(f'apps/{app_guid}/routes'), [])

    def test_optional_removal_rejected_before_mutation_including_interrupted_create(self):
        self.config['integrations']['hub'] = True
        self.lifecycle().deploy()
        self.config['integrations']['hub'] = False
        before = copy.deepcopy(self.cf.inventory)
        mutations = len(self.cf.mutations)
        for action in (self.lifecycle().deploy, self.lifecycle().validate):
            with self.assertRaisesRegex(CFError, 'cannot disable existing integration'):
                action()
        self.assertEqual(before, self.cf.inventory)
        self.assertEqual(mutations, len(self.cf.mutations))
        self.config['integrations']['hub'] = True
        self.lifecycle().cleanup(True)
        self.cf.fail_after_create = 'demo-hub-relay'
        with self.assertRaises(CFError):
            self.lifecycle().deploy()
        self.config['integrations']['hub'] = False
        mutations = len(self.cf.mutations)
        with self.assertRaisesRegex(CFError, 'cannot disable'):
            self.lifecycle().deploy()
        self.assertEqual(mutations, len(self.cf.mutations))

    def test_quota_rejects_org_and_space_shortfalls_before_mutation(self):
        fields = [('apps', 'total_memory_in_mb'), ('apps', 'total_instances'),
                  ('apps', 'per_process_memory_in_mb'), ('routes', 'total_routes'),
                  ('services', 'total_service_instances')]
        for quota in (self.cf.org_quota, self.cf.space_quota):
            for section, field in fields:
                quota[section][field] = 0
                with self.assertRaisesRegex(CFError, 'quota insufficient'):
                    self.lifecycle().deploy()
                self.assertEqual(self.cf.mutations, [])
                quota[section][field] = None
        self.cf.extra_usage['organizations']['memory_in_mb'] = 1000
        self.cf.org_quota['apps']['total_memory_in_mb'] = 1500
        with self.assertRaisesRegex(CFError, 'used 1000, incremental 1024, limit 1500'):
            self.lifecycle(1).deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_quota_incremental_redeploy_upgrade_and_restart(self):
        self.lifecycle(1).deploy()
        self.cf.org_quota['apps']['total_memory_in_mb'] = 1024
        self.cf.org_quota['routes']['total_routes'] = 1
        self.cf.org_quota['services']['total_service_instances'] = 2
        result = self.lifecycle(1).preflight()
        check = next(c for c in result['checks'] if c['check'] == 'quota:org')
        self.assertEqual(check['incremental_demand'], dict(memory_in_mb=0, started_instances=0, routes=0, service_instances=0))
        self.lifecycle(1).deploy()
        mutations = len(self.cf.mutations)
        with self.assertRaisesRegex(CFError, 'quota insufficient'):
            self.lifecycle(4).deploy()
        self.assertEqual(mutations, len(self.cf.mutations))
        app = self.cf.inventory['apps'][self.state.data['resources']['agent']['guid']]
        app['state'] = 'STOPPED'
        self.cf.extra_usage['organizations']['memory_in_mb'] = 1
        with self.assertRaisesRegex(CFError, 'incremental 1024'):
            self.lifecycle(1).deploy()
        self.assertEqual(mutations, len(self.cf.mutations))

    def test_quota_absent_space_limit_and_missing_contract_fail_closed(self):
        self.cf.space_quota = None
        result = self.lifecycle().preflight()
        check = next(c for c in result['checks'] if c['check'] == 'quota:space')
        self.assertIsNone(check['quota_guid'])
        self.assertEqual(check['incremental_demand']['memory_in_mb'], 2 * 1024 + 256)
        del self.cf.org_quota['services']['total_service_instances']
        with self.assertRaisesRegex(CFError, 'complete CAPI'):
            self.lifecycle().deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_phase_space_quota_uses_selected_target_and_full_closure(self):
        state = State(Path(self.tmp.name) / 'phase-state', target_for(self.config, 4, 'phase-spaces'))
        with state.locked():
            self.cf.space_quota['apps']['total_memory_in_mb'] = 2048
            lifecycle = Lifecycle(self.config, 4, 'phase-spaces', self.cf, state, probe=lambda url: 200)
            with self.assertRaisesRegex(CFError, 'space quota insufficient'):
                lifecycle.deploy()
        self.assertIn('/v3/spaces/demo-space-phase4/usage_summary', self.cf.quota_reads)
        self.assertEqual(self.cf.mutations, [])


    def test_quota_paid_plan_permission_and_usage_access_fail_closed(self):
        original = self.cf.list
        def paid_plans(kind, **query):
            result = original(kind, **query)
            if kind == 'service_plans':
                for item in result:
                    item['free'] = False
            return result
        self.cf.list = paid_plans
        self.cf.space_quota['services']['paid_services_allowed'] = False
        with self.assertRaisesRegex(CFError, 'disallows required paid'):
            self.lifecycle(1).deploy()
        self.assertEqual(self.cf.mutations, [])
        self.cf.space_quota['services']['paid_services_allowed'] = True
        from northstar_kit.cf import CFHTTPError
        original_api = self.cf.api
        def inaccessible(path, method='GET', data=None):
            if path.endswith('/usage_summary'):
                raise CFHTTPError(403)
            return original_api(path, method, data)
        self.cf.api = inaccessible
        with self.assertRaisesRegex(CFError, 'quota preflight failed before provisioning'):
            self.lifecycle(1).deploy()
        self.assertEqual(self.cf.mutations, [])

    def test_phase_space_optional_removal_uses_current_phase_prefix(self):
        self.config['integrations']['hub'] = True
        secret = Path(self.config['credentials']['hub_oauth'])
        data = json.loads(secret.read_text())
        data['redirect_uri'] = 'https://discovered.gateway.test/demo-p3-hub-relay/auth/callback'
        secret.write_text(json.dumps(data))
        state = State(Path(self.tmp.name) / 'phase-state', target_for(self.config, 3, 'phase-spaces'))
        with state.locked():
            lifecycle = Lifecycle(self.config, 3, 'phase-spaces', self.cf, state, probe=lambda url: 200)
            lifecycle.deploy()
            self.config['integrations']['hub'] = False
            mutations = len(self.cf.mutations)
            with self.assertRaisesRegex(CFError, 'cannot disable existing integration hub'):
                Lifecycle(self.config, 3, 'phase-spaces', self.cf, state).deploy()
            self.assertEqual(mutations, len(self.cf.mutations))
