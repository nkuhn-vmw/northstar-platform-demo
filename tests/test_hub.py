import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from northstar_kit.config import ConfigError, read_secret
from northstar_kit.hub import callback_url, register
from test_config import profile


class HubRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = profile(self.tmp.name)
        self.path = Path(self.config['credentials']['hub_oauth'])
        self.path.unlink()
        self.gateway = 'https://gateway.foundation.test'
        self.resource = {'resource': self.config['hub']['mcp_url'], 'authorization_servers': [self.config['hub']['authorization_server']]}
        self.discovery = {'issuer': self.config['hub']['authorization_server'], 'authorization_endpoint': 'https://login.foundation.test/authorize', 'token_endpoint': 'https://login.foundation.test/token', 'registration_endpoint': 'https://login.foundation.test/register', 'token_endpoint_auth_methods_supported': ['client_secret_post']}

    def test_register_private_client_and_keep_on_retry(self):
        with patch('northstar_kit.hub.request_json', side_effect=[self.resource, self.discovery, {'client_id': 'private-id', 'client_secret': 'private-secret'}]) as request:
            result = register(self.config, self.gateway, apply=True)
            self.assertEqual(request.call_args.args[1]['redirect_uris'], [callback_url(self.config, self.gateway)])
            self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(self.path.read_text())['client_secret'], 'private-secret')
            self.assertNotIn('private-secret', json.dumps(result))
            register(self.config, self.gateway, apply=True)
            self.assertEqual(request.call_count, 3)
        with self.assertRaises(ConfigError):
            register(self.config, 'https://another.foundation.test', apply=True)

    def test_wrong_resource_never_registers_or_creates_file(self):
        with patch('northstar_kit.hub.request_json', return_value=dict(self.resource, resource='https://another.test/mcp')) as request:
            with self.assertRaises(ConfigError):
                register(self.config, self.gateway, apply=True)
            self.assertEqual(request.call_count, 1)
            self.assertFalse(self.path.exists())

    def test_uncertain_registration_blocks_automatic_duplicate(self):
        with patch('northstar_kit.hub.request_json', side_effect=[self.resource, self.discovery, ConfigError('network failed')]) as request:
            with self.assertRaises(ConfigError):
                register(self.config, self.gateway, apply=True)
            with self.assertRaises(ConfigError):
                register(self.config, self.gateway, apply=True)
            self.assertEqual(request.call_count, 3)
            self.assertEqual(json.loads(self.path.read_text()), {})

    def test_operator_client_file_requires_https_endpoints(self):
        with patch('northstar_kit.hub.request_json', side_effect=[self.resource, self.discovery, {'client_id': 'private-id', 'client_secret': 'private-secret'}]):
            register(self.config, self.gateway, apply=True)
        credential = json.loads(self.path.read_text())
        credential['token_endpoint'] = 'http://login.foundation.test/token'
        self.path.write_text(json.dumps(credential))
        with self.assertRaises(ConfigError):
            read_secret(self.config, 'hub_oauth')

    def test_phase_space_callback_matches_lifecycle_target(self):
        result = register(self.config, self.gateway, phase=3, mode='phase-spaces')
        self.assertEqual(result['callback'], self.gateway + '/demo-p3-hub-relay/auth/callback')
