from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "apps" / "agent" / "runtime" / "launch-agent.sh"


class LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temporary.name)
        self.app = self.sandbox / "app"
        (self.app / "runtime").mkdir(parents=True)
        (self.app / "bin").mkdir()
        shutil.copyfile(LAUNCHER, self.app / "runtime" / "launch-agent.sh")
        self.fake_path = self.sandbox / "fake-path"
        self.fake_path.mkdir()
        self._write_executable("tanzu-agent", "#!/bin/sh\nexit 0\n")
        self._write_executable(
            "curl",
            """#!/bin/sh
case " $* " in
  *" /.well-known/openid-configuration "*) exit 2 ;;
esac
cat <<'EOF'
{"issuer":"https://id.example","authorization_endpoint":"https://id.example/login","token_endpoint":"https://id.example/token","jwks_uri":"https://id.example/keys"}
EOF
""",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_executable(self, name: str, content: str, *, app_bin: bool = False) -> Path:
        directory = self.app / "bin" if app_bin else self.fake_path
        path = directory / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def _environment(self, **overrides: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.fake_path}:{environment['PATH']}",
                "PORT": "8080",
                "TANZU_AGENT_BASE_URL": "https://agent.example.test",
                "TMPDIR": str(self.sandbox / "tmp"),
            }
        )
        (self.sandbox / "tmp").mkdir(exist_ok=True)
        environment.update(overrides)
        return environment

    def _run(self, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.app / "runtime" / "launch-agent.sh")],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            check=False,
        )

    @staticmethod
    def _process_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def _terminate_recorded_processes(self, *pid_files: Path) -> None:
        for pid_file in pid_files:
            if not pid_file.exists():
                continue
            pid = int(pid_file.read_text())
            if self._process_is_alive(pid):
                os.kill(pid, signal.SIGTERM)

    def test_rejects_every_invalid_entry_in_mixed_allowlist(self) -> None:
        identity = {
            "p-identity": [
                {
                    "name": "sso",
                    "credentials": {
                        "auth_domain": "https://id.example",
                        "client_id": "client",
                        "client_secret": "secret",
                    },
                }
            ]
        }
        invalid_allowlists = (
            "valid@example.com,*@example.com",
            "valid@example.com,*",
            "valid@example.com,not-an-email",
            "valid@example.com,,other@example.com",
        )

        for allowlist in invalid_allowlists:
            with self.subTest(allowlist=allowlist):
                result = self._run(
                    self._environment(
                        VCAP_SERVICES=json.dumps(identity),
                        APP_ALLOWED_EMAILS=allowlist,
                    )
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("APP_ALLOWED_EMAILS contains an invalid email", result.stderr)
                self.assertEqual(list((self.sandbox / "tmp").glob("agent-allowed-emails.*")), [])

    def test_native_memory_never_enters_publisher_adapter(self) -> None:
        # A native binding may retain an operator-added legacy tag during migration.
        # It lacks Publisher OAuth fields and must pass through untouched.
        services = {"agent-memory": [{
            "name": "native-memory", "label": "agent-memory",
            "tags": ["agent-memory", "tanzu-agent-memory"],
            "credentials": {"url": "https://memory.example", "store_id": "synthetic"},
        }]}
        result = self._run(self._environment(
            VCAP_SERVICES=json.dumps(services), APP_ALLOWED_EMAILS="valid@example.com"))
        self.assertIn("p-identity binding is required", result.stderr)
        self.assertNotIn("ams-gateway-adapter", result.stderr)
        self.assertEqual(list((self.sandbox / "tmp").glob("agent-ams-*")), [])



    def test_proxy_uses_configured_scopes_and_compatible_default(self) -> None:
        identity = {'p-identity': [{'credentials': {'auth_domain': 'https://id.example',
                     'client_id': 'client', 'client_secret': 'secret'}}]}
        args_file = self.sandbox / 'proxy-args'
        self._write_executable('oauth2-proxy', '#!/bin/sh\nprintf "%s\\n" "$@" >"$ARGS_FILE"\n', app_bin=True)
        self._write_executable('tanzu-agent', '#!/bin/sh\nexec sleep 60\n')
        for configured, expected in (('', 'openid roles'), ('openid profile email', 'openid profile email')):
            with self.subTest(scopes=configured):
                result = self._run(self._environment(VCAP_SERVICES=json.dumps(identity),
                    APP_ALLOWED_EMAILS='valid@example.com', ARGS_FILE=str(args_file),
                    TANZU_AGENT_AUTH_OAUTH_SCOPES=configured))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--insecure-oidc-allow-unverified-email=false', args_file.read_text())
                self.assertIn('--scope=' + expected, args_file.read_text().splitlines())

    def test_all_sso_users_retains_oidc_proxy(self):
        identity = {'p-identity': [{'name': 'sso', 'credentials': {
            'auth_domain': 'https://id.example', 'client_id': 'client', 'client_secret': 'secret'}}]}
        args_file = self.sandbox / 'proxy-args'
        self._write_executable('oauth2-proxy', '#!/bin/sh\nprintf "%s\\n" "$@" >"$ARGS_FILE"\n', app_bin=True)
        self._write_executable('tanzu-agent', '#!/bin/sh\nexec sleep 60\n')
        result = self._run(self._environment(VCAP_SERVICES=json.dumps(identity),
            APP_ALLOWED_EMAILS='*', ARGS_FILE=str(args_file)))
        self.assertEqual(result.returncode, 0, result.stderr)
        args = args_file.read_text().splitlines()
        self.assertIn('--email-domain=*', args)
        self.assertIn('--provider=oidc', args)
        self.assertIn('--oidc-issuer-url=https://id.example', args)
        self.assertFalse(any(a.startswith('--authenticated-emails-file=') for a in args))
        result = self._run(self._environment(VCAP_SERVICES='{}', APP_ALLOWED_EMAILS='*'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('p-identity binding is required', result.stderr)






if __name__ == "__main__":
    unittest.main()
