"""CF transport. No shell or literal credential JSON in argv."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode


class CFError(RuntimeError):
    pass


class CFHTTPError(CFError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'CF API HTTP {status} (response suppressed)')


class CF:
    def __init__(self, home=None, timeout=600):
        self.home = home
        self.timeout = timeout

    @contextmanager
    def isolated(self):
        # CF_HOME contains .cf/config.json. Copy authentication, never retarget
        # the user's original CLI context or export tokens into the state journal.
        original = Path(self.home or os.environ.get('CF_HOME', str(Path.home())))
        with tempfile.TemporaryDirectory(prefix='northstar-cf-') as temp:
            target = Path(temp) / '.cf'
            target.mkdir(mode=0o700)
            source = original / '.cf/config.json'
            if not source.is_file():
                raise CFError('CF login/config missing; log in with cf CLI first')
            shutil.copyfile(source, target / 'config.json')
            os.chmod(target / 'config.json', 0o600)
            previous, self.home = self.home, temp
            try:
                yield self
            finally:
                self.home = previous

    def run(self, args: list[str]) -> str:
        env = dict(os.environ)
        if self.home:
            env['CF_HOME'] = str(self.home)
        try:
            result = subprocess.run(['cf', *args], env=env, text=True, capture_output=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise CFError(f'CF {args[0]} unavailable or timed out (output suppressed)') from None
        if result.returncode:
            # Suppress all response bodies: even read failures can contain broker credentials.
            raise CFError(f'CF {args[0]} failed with exit {result.returncode} (output suppressed)')
        return result.stdout

    def api(self, path, method='GET', data=None):
        args = ['curl', path, '-X', method, '-i']
        with tempfile.TemporaryDirectory(prefix='northstar-payload-') as temp:
            if data is not None:
                payload = Path(temp) / 'request.json'
                fd = os.open(payload, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as file:
                    json.dump(data, file)
                args += ['-d', '@' + str(payload)]
            output = self.run(args)
        headers = ''
        if output.startswith('HTTP/'):
            pieces = re.split(r'\r?\n\r?\n', output, maxsplit=1)
            headers, output = pieces[0], pieces[1] if len(pieces) > 1 else ''
            status = int(headers.split()[1])
            if status >= 400:
                raise CFHTTPError(status)
        try:
            result = json.loads(output) if output.strip() else {}
        except ValueError:
            raise CFError('CF API returned invalid JSON (output suppressed)') from None
        if result.get('errors'):
            raise CFError('CF API rejected request (response suppressed)')
        location = re.search(r'^Location:\s*(\S+)', headers, re.I | re.M)
        if location and '/v3/jobs/' in location.group(1):
            job_path = '/v3/jobs/' + location.group(1).split('/v3/jobs/', 1)[1]
            deadline = time.monotonic() + self.timeout
            while True:
                job = self.api(job_path)
                if job.get('state') == 'COMPLETE':
                    break
                if job.get('state') == 'FAILED':
                    raise CFError('asynchronous CF job failed (details suppressed)')
                if time.monotonic() >= deadline:
                    raise CFError('asynchronous CF job timed out; rerun to resume')
                time.sleep(2)
        return result

    def get(self, kind, guid):
        """Retrieve one GUID; only an explicit HTTP 404 means it is absent."""
        try:
            return self.api('/v3/' + kind + '/' + guid)
        except CFHTTPError as error:
            if error.status == 404:
                return None
            raise

    def list(self, kind, **query):
        path = '/v3/' + kind + '?' + urlencode({**query, 'per_page': 5000})
        result = []
        while path:
            page = self.api(path)
            result.extend(page.get('resources', []))
            next_page = page.get('pagination', {}).get('next')
            path = next_page.get('href') if next_page else None
            if path and path.startswith('http'):
                from urllib.parse import urlsplit
                parsed = urlsplit(path)
                path = parsed.path + '?' + parsed.query
        return result

    def wait_service(self, guid):
        deadline = time.monotonic() + self.timeout
        while True:
            resource = self.api('/v3/service_instances/' + guid)
            operation = resource.get('last_operation', {})
            status = operation.get('state', 'succeeded')
            if status == 'succeeded':
                return resource
            if status == 'failed':
                raise CFError('broker operation failed (details suppressed)')
            if time.monotonic() >= deadline:
                raise CFError('broker operation timed out; rerun to resume')
            time.sleep(2)

    def wait_app(self, guid):
        deadline = time.monotonic() + self.timeout
        while True:
            processes = self.list(f'apps/{guid}/processes')
            web = [p for p in processes if p['type'] == 'web']
            observed = 'no web process'
            if web:
                stats = self.api('/v3/processes/' + web[0]['guid'] + '/stats').get('resources', [])
                # Only expose known state labels, never broker-supplied details.
                known = {'RUNNING', 'STARTING', 'DOWN', 'CRASHED', 'FAILED'}
                states = sorted({s.get('state') if s.get('state') in known else 'UNKNOWN' for s in stats})
                observed = ', '.join(states) if states else 'no web instance statistics'
                if stats and all(s.get('state') == 'RUNNING' for s in stats):
                    return
            if time.monotonic() >= deadline:
                raise CFError(f'app health timed out (last observed: {observed}); inspect cf logs <app-name> --recent before retrying')
            time.sleep(2)

    def target_metadata(self):
        try:
            local = json.loads((Path(self.home or os.environ.get('CF_HOME', str(Path.home()))) / '.cf/config.json').read_text())
            if local.get('SSLDisabled'):
                raise CFError('CF TLS verification is disabled; configure a trusted CA and log in without skip-SSL')
            org_guid = local['OrganizationFields']['GUID']
            space_guid = local['SpaceFields']['GUID']
            org = self.api('/v3/organizations/' + org_guid)
            space = self.api('/v3/spaces/' + space_guid)
            if space['relationships']['organization']['data']['guid'] != org_guid:
                raise CFError('CF target metadata is inconsistent')
            return {'api': local['Target'].rstrip('/'), 'org': org['name'], 'space': space['name'], 'org_guid': org_guid, 'space_guid': space_guid}
        except (KeyError, OSError, ValueError):
            raise CFError('cannot resolve authenticated CF target identity') from None

    def wait_binding(self, guid):
        deadline = time.monotonic() + self.timeout
        while True:
            result = self.api('/v3/service_credential_bindings/' + guid)
            status = result.get('last_operation', {}).get('state', 'succeeded')
            if status == 'succeeded':
                return result
            if status == 'failed':
                raise CFError('broker binding failed (details suppressed)')
            if time.monotonic() >= deadline:
                raise CFError('broker binding timed out')
            time.sleep(2)

    def wait_absent(self, kind, guid):
        deadline = time.monotonic() + self.timeout
        while self.get(kind, guid) is not None:
            if time.monotonic() >= deadline:
                raise CFError('deletion timed out; rerun to resume')
            time.sleep(2)
