"""Portable source/package checks, adapted from the original kit verifier."""
import json
from pathlib import Path
import re
import runpy
import subprocess
from urllib.parse import unquote, urlsplit


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_files(root):
    if (root / '.git').exists():
        output = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root)
        return sorted({Path(p.decode()) for p in output.split(b'\0') if p})
    # Source archives are also supported; never walk ignored build/state trees.
    excluded = {'.git', '.artifacts', '.credentials', '.state', '.gradle', 'build', '__pycache__', '.pytest_cache', 'node_modules'}
    result = []
    import os
    for parent, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in excluded and not (d == 'bin' and Path(parent) == root / 'apps/agent')]
        for name in files:
            if name.endswith(('.local.json', '.pyc')) or name == '.DS_Store' or name.startswith('.env'):
                continue
            result.append((Path(parent) / name).relative_to(root))
    return sorted(result)


def check_links(root, files):
    count = 0
    for relative in files:
        if relative.suffix != '.md':
            continue
        text = re.sub(r'(?ms)^```.*?^```[^\n]*', '', (root / relative).read_text())
        for match in re.finditer(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', text):
            link = match.group(1).strip('<>')
            parts = urlsplit(link)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            target = (root / relative.parent / unquote(parts.path)).resolve()
            require(target.is_relative_to(root), f'Link escapes repository: {relative}: {link}')
            require(target.exists(), f'Broken local link: {relative}: {link}')
            count += 1
    print(f'PASS: {count} local Markdown file links (network links not fetched)')


def check_inventory(root):
    from northstar_kit.config import load_config
    from northstar_kit.lifecycle import plan
    raw = json.loads((root / 'deploy/topology.json').read_text())
    config = load_config(root / 'profiles/platform-11.example.json')
    for hub in (False, True):
        config['integrations']['hub'] = hub
        for phase in range(1, 5):
            normal = plan(config, phase)
            isolated = plan(config, phase, 'phase-spaces')
            expected = {r['id'] for r in raw if r['phase'] <= phase and (not r.get('integration') or config['integrations'][r['integration']])}
            if phase >= 2 and hub:
                expected.update(('hub-oauth', 'hub-relay'))
            if phase >= 3:
                expected.add('credential-store')
            require({r['id'] for r in normal['components']} == expected, f'phase {phase} closure mismatch')
            require([r['id'] for r in normal['components']] == [r['id'] for r in isolated['components']], 'isolated closure mismatch')
            require(set(normal['manifests']) == {r['id'] for r in normal['components'] if r['kind'] == 'app'}, 'missing app manifests')
            require(all(r['name'].startswith(config['target']['prefix'] + f'-p{phase}-') for r in isolated['components']), 'isolated names mismatch')
            require(not normal['live_verified'] and not isolated['live_verified'], 'offline plan claims live proof')
    print('PASS: native phase/mode plans with optional Hub (early Hub deployment remains gated)')


def audit(root):
    root = root.resolve()
    files = source_files(root)
    prepare = runpy.run_path(str(root / 'bin/prepare'))
    manifest = json.loads((root / 'provenance/dependencies.json').read_text())
    for dependency in manifest['dependencies']:
        source = dependency['source']
        if dependency['kind'] in ('source-build', 'go-build'):
            require(prepare['source_tree_sha256'](root / source['path']) == source['tree_sha256'], f'source recipe mismatch: {source["path"]}')
        else:
            require(re.fullmatch(r'[a-f0-9]{64}', source['archive_sha256']) is not None, 'unpinned archive')
        require(source.get('license') in ('Apache-2.0', 'MIT'), 'missing source license')
        require((root / source['license_file']).is_file(), 'missing license text')
    print(f'PASS: all {len(manifest["dependencies"])} dependency source/archive pins and license references')
    check_links(root, files)
    check_inventory(root)
    for relative in files:
        path = root / relative
        require(not path.is_symlink(), f'symlink in release: {relative}')
        require(not any(part in {'.credentials', '.state', '.artifacts', 'node_modules', '__pycache__'} for part in relative.parts), f'private/generated file tracked: {relative}')
        data = path.read_bytes()
        if b'\0' in data:
            continue
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            continue
        if relative.suffix == '.json':
            json.loads(text)
        if relative.suffix == '.sh' or re.match(r'^#!(?:/usr/bin/env |/bin/)(?:ba)?sh(?:\s|$)', text):
            subprocess.run(['bash', '-n', str(path)], check=True)
        if relative.suffix == '.py' or (relative.parts[0] == 'bin' and 'python' in text.splitlines()[0]):
            compile(text, str(relative), 'exec')
        require(not re.search(r'/(?:Users|home)/(?!vcap(?:/|\b))[A-Za-z0-9_.-]+/', text), f'workstation path: {relative}')
    if (root / '.git').exists():
        subprocess.run(['git', 'diff', '--check'], cwd=root, check=True)
    print(f'PASS: {len(files)} source files; syntax, package boundaries and workstation paths')
