import json
import os
import tempfile
import unittest
from pathlib import Path
from northstar_kit.config import ROOT, ConfigError, SECRETS, load_config, required_secrets, validate_live


def profile(directory):
    config = json.loads((ROOT / 'profiles/platform-11.example.json').read_text())
    config['target'] = dict(api='https://api.foundation.test', org='demo-org', space='demo-space', prefix='demo')
    config['routes']['domain'] = 'apps.foundation.test'
    config['sso'] = dict(allowed_emails=['operator@company.test'], identity_provider='corp', scopes='openid,roles', agent_scopes='openid', allow_unverified_email=False)
    config['services']['model']['plan'] = 'all-models'
    config['services']['sso']['plan'] = 'corp-sso'
    config['models'] = dict(interactive='model-a')
    config['hub'] = dict(mcp_url='https://hub.foundation.test/mcp', resource_metadata_url='https://hub.foundation.test/.well-known/oauth-protected-resource', authorization_server='https://login.foundation.test', auth_mode='gateway-oauth')
    path = Path(directory) / 'hub-oauth.json'
    path.write_text(json.dumps(dict(client_id='synthetic-id', client_secret='synthetic-secret', authorization_endpoint='https://login.foundation.test/authorize', token_endpoint='https://login.foundation.test/token', redirect_uri='https://discovered.gateway.test/demo-hub-relay/auth/callback')))
    os.chmod(path, 0o600)
    config['credentials']['hub_oauth'] = str(path)
    return config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = profile(self.tmp.name)
        self.path = Path(self.tmp.name) / 'profile.json'

    def load(self):
        self.path.write_text(json.dumps(self.config))
        return load_config(self.path)

    def test_example_can_plan_but_cannot_deploy(self):
        example = load_config(ROOT / 'profiles/platform-11.example.json')
        with self.assertRaises(ConfigError):
            validate_live(example, 1)
        validate_live(self.load(), 4)

    def test_unknown_legacy_keys_and_invalid_names_fail_closed(self):
        for prefix in ('-bad', '../bad', 'Bad', 'x' * 41):
            self.config['target']['prefix'] = prefix
            with self.assertRaises(ConfigError):
                self.load()
        self.config = profile(self.tmp.name)
        self.config['integrations']['github'] = True
        with self.assertRaises(ConfigError):
            self.load()

    def test_agent_scope_and_native_service_boundaries(self):
        for scopes in ('roles', 'openid,admin', 'openid,', 'openid, roles'):
            self.config['sso']['agent_scopes'] = scopes
            with self.assertRaises(ConfigError):
                self.load()
        for field, value in [('agent_package', 'compatible'), ('version', 2)]:
            self.config = profile(self.tmp.name)
            self.config[field] = value
            with self.assertRaises(ConfigError):
                self.load()
        self.config = profile(self.tmp.name)
        self.config['services']['memory']['offering'] = 'publisher-memory'
        with self.assertRaises(ConfigError):
            self.load()

    def test_credentials_are_private_and_only_needed_for_enabled_hub(self):
        self.config['credentials']['hub_oauth'] = 'hub-oauth.json'
        self.assertEqual(self.load()['credentials']['hub_oauth'], str((Path(self.tmp.name) / 'hub-oauth.json').resolve()))
        os.chmod(Path(self.tmp.name) / 'hub-oauth.json', 0o644)
        validate_live(self.load(), 4)
        self.config['integrations']['hub'] = True
        with self.assertRaisesRegex(ConfigError, 'private file'):
            validate_live(self.load(), 4)
        with self.assertRaisesRegex(ConfigError, 'phase 3 or later'):
            validate_live(self.load(), 2)

    def test_exact_email_allowlist_and_document_url(self):
        for emails in ([], ['*@company.test'], ['good@company.test', '*'], ['bad'], ['a?@company.test']):
            self.config['sso']['allowed_emails'] = emails
            with self.assertRaises(ConfigError):
                self.load()
        self.config['sso']['allowed_emails'] = ['*']
        self.load()
        self.config['guide']['documentation_url'] = 'javascript:alert(1)'
        with self.assertRaises(ConfigError):
            self.load()
