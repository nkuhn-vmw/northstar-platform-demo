"""Private atomic journal, keyed by complete deployment target."""
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
import fcntl


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class State:
    def __init__(self, root, target):
        self.directory = Path(root) / digest(target)[:24]
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / 'state.json'
        self.target = target
        self.data = None

    @contextmanager
    def locked(self):
        with (self.directory / 'lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('another lifecycle command holds this target lock') from None
            self.data = json.loads(self.path.read_text()) if self.path.exists() else {'target': self.target, 'owner': str(uuid.uuid4()), 'resources': {}}
            if self.data['target'] != self.target:
                raise RuntimeError('state target mismatch')
            self.save()
            try:
                yield self
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def save(self):
        self.write('state.json', self.data)

    def write(self, name, value):
        destination = self.directory / name
        fd, temporary = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as file:
                json.dump(value, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination

    def record(self, key, kind, resource, **fields):
        self.data['resources'][key] = {'kind': kind, 'guid': resource['guid'], 'name': resource.get('name', key), **fields}
        self.save()
