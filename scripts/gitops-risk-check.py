#!/usr/bin/env python3
"""V1 read-only GitOps transition review. Requires PyYAML, kustomize and Helm.

Checks committed trees, not live state. It supports this repo's Git directory
ApplicationSets and simple path Go templates; unsupported generators fail closed.
"""
import argparse
import copy
import fnmatch
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

import yaml

ENTRY = 'infrastructure/controllers/argocd/apps'
SEED = 'infrastructure/controllers/argocd/root.yaml'
PERSISTENT = {'PersistentVolumeClaim', 'PersistentVolume', 'StatefulSet', 'Namespace'}


def run(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise ValueError(f'{args[0]} failed: {result.stderr.strip()[:800]}')
    return result.stdout


def render(root, path):
    return [obj for obj in yaml.safe_load_all(run('kustomize', 'build', '--enable-helm',
            str(root / path))) if isinstance(obj, dict)]


def controllers(root):
    seed = yaml.safe_load((root / SEED).read_text())
    if seed['spec']['source']['path'] != ENTRY:
        raise ValueError('Root source changed; update the supported entrypoint contract')
    objs = render(root, ENTRY)
    return {obj['metadata']['name']: obj for obj in objs if obj['kind'] == 'ApplicationSet'}, [
        obj for obj in objs if obj['kind'] == 'Application'] + [seed]


def directories(root):
    # Include intermediate directories: the real generator does not require a kustomization.
    return {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()
            and not any(part.startswith('.') for part in p.relative_to(root).parts)}


def matches(path, pattern):
    # Go path.Match semantics: '*' cannot cross '/'; Python fnmatch on whole paths can.
    parts, globs = path.split('/'), pattern.split('/')
    return len(parts) == len(globs) and all(fnmatch.fnmatchcase(p, g) for p, g in zip(parts, globs))


def expand(value, path):
    if isinstance(value, list):
        return [expand(v, path) for v in value]
    if isinstance(value, dict):
        return {k: expand(v, path) for k, v in value.items()}
    if not isinstance(value, str):
        return value
    base = path.split('/')[-1]
    for field, replacement in [('path', path), ('basename', base),
                                ('basenameNormalized', re.sub('[^a-zA-Z0-9.-]', '-', base))]:
        value = re.sub(r'{{\s*\.path\.' + field + r'\s*}}', lambda _: replacement, value)
    value = re.sub(r'{{\s*index \.path\.segments (\d+)\s*}}',
                   lambda m: path.split('/')[int(m[1])], value)
    if '{{' in value:
        raise ValueError(f'Unsupported Go template: {value}')
    return value


def inventory(sets, standalone, dirs):
    apps = {}
    def add(obj, owner):
        name = obj['metadata']['name']
        if name in apps:
            raise ValueError(f'Duplicate Application identity {name}')
        apps[name] = {'owner': owner, 'object': obj}
    for obj in standalone:
        add(obj, 'root')
    for name, obj in sets.items():
        spec = obj['spec']
        if spec.get('goTemplate') is not True:
            raise ValueError(f'{name}: only strict Go path templates are supported')
        paths = set()
        for generator in spec['generators']:
            if set(generator) != {'git'} or 'directories' not in generator['git']:
                raise ValueError(f'{name}: unsupported generator')
            git = generator['git']
            if git.get('revision') != 'main' or git.get('repoURL') != 'https://github.com/mitchross/talos-argocd-proxmox.git':
                raise ValueError(f'{name}: generator revision/repository requires independent analysis')
            rules = git['directories']
            included = {p for p in dirs if any(matches(p, rule['path']) for rule in rules if not rule.get('exclude'))}
            excluded = {p for p in dirs if any(matches(p, rule['path']) for rule in rules if rule.get('exclude'))}
            paths |= included - excluded
        for path in sorted(paths):
            app = expand(copy.deepcopy(spec['template']), path)
            add(app, name)
    return apps


def identity(app):
    obj = app['object']; spec = obj['spec']
    return {'owner': app['owner'], 'project': spec.get('project'),
            'destination': spec.get('destination'), 'source': spec.get('source'),
            'finalizers': obj['metadata'].get('finalizers', [])}


def dependency_dirs(root, path, seen=None):
    seen = seen or set()
    if path in seen:
        return seen
    seen.add(path)
    config = root / path / 'kustomization.yaml'
    if not config.exists():
        return seen
    doc = yaml.safe_load(config.read_text())
    for key in ('resources', 'components', 'bases'):
        for value in doc.get(key, []):
            if '://' in value:
                raise ValueError(f'{path}: remote Kustomize dependency unsupported')
            candidate = (root / path / value).resolve()
            candidate.relative_to(root.resolve())  # Reject repo escapes.
            if candidate.is_dir():
                dependency_dirs(root, candidate.relative_to(root).as_posix(), seen)
    return seen


def resource_key(obj):
    meta = obj.get('metadata', {})
    return '/'.join([obj['apiVersion'].split('/')[0] if '/' in obj['apiVersion'] else '',
                     obj['kind'], meta.get('namespace', ''), meta['name']])


def inspect(oldroot, newroot, changed):
    findings = []
    def finding(level, code, target, before, after, reason):
        findings.append(dict(level=level, code=code, target=target, old=before, new=after, reason=reason))
    oldsets, oldstand = controllers(oldroot); newsets, newstand = controllers(newroot)
    olddirs, newdirs = directories(oldroot), directories(newroot)
    oo = inventory(oldsets, oldstand, olddirs)
    on = inventory(oldsets, oldstand, newdirs)
    no = inventory(newsets, newstand, olddirs)
    nn = inventory(newsets, newstand, newdirs)
    states = {'OLD generator + NEW tree': on, 'NEW generator + OLD tree': no, 'NEW generator + NEW tree': nn}
    for label, apps in states.items():
        for name, old in oo.items():
            new = apps.get(name)
            if new is None:
                finding('BLOCK', 'application-disappears', name, identity(old), {'state': label, 'application': None},
                        'Generator/tree transition removes a previously discovered Application; preservation must be verified live.')
            elif {k: v for k, v in identity(old).items() if k != 'source'} != {k: v for k, v in identity(new).items() if k != 'source'}:
                finding('BLOCK', 'application-ownership', name, identity(old), {'state': label, **identity(new)},
                        'Application owner, destination, project or explicit finalizers change.')
            if new:
                candidate = new['object']['spec'].get('source', {}).get('path')
                if candidate and candidate not in (olddirs if label == 'NEW generator + OLD tree' else newdirs):
                    finding('WARN', 'missing-next-source-directory', name, candidate, label,
                            'Controller source points to a directory absent in this transition tree.')
            oldpath = old['object']['spec'].get('source', {}).get('path')
            if oldpath and oldpath not in (newdirs if label != 'NEW generator + OLD tree' else olddirs):
                finding('WARN', 'missing-source-directory', name, oldpath, label,
                        'An Application source path disappears before its controller updates.')
    for name in sorted(oldsets.keys() | newsets.keys()):
        a, b = oldsets.get(name, {}), newsets.get(name, {})
        for field in ('generators', 'syncPolicy', 'template'):
            av, bv = a.get('spec', {}).get(field), b.get('spec', {}).get(field)
            if av != bv:
                level = 'BLOCK' if field == 'syncPolicy' and av and av.get('preserveResourcesOnDeletion') and not (bv or {}).get('preserveResourcesOnDeletion') else 'WARN'
                finding(level, 'appset-' + field, name, av, bv,
                        'ApplicationSet configuration changes; prerequisite fields must be verified live before a dependent phase.')
        if a.get('metadata', {}).get('finalizers') != b.get('metadata', {}).get('finalizers'):
            finding('BLOCK', 'appset-finalizers', name, a.get('metadata'), b.get('metadata'), 'ApplicationSet deletion behavior changes.')
    rendered = [{}, {}]
    for name in sorted(oo.keys() | nn.keys()):
        a, b = oo.get(name), nn.get(name)
        paths = [x['object']['spec'].get('source', {}).get('path') if x else None for x in (a, b)]
        if a and b:
            ap, bp = a['object']['spec'].get('syncPolicy', {}), b['object']['spec'].get('syncPolicy', {})
            if ap != bp:
                escalated = (not ap.get('automated', {}).get('prune') and bp.get('automated', {}).get('prune')) or any(
                    option in ('Force=true', 'Replace=true') for option in bp.get('syncOptions', []) if option not in ap.get('syncOptions', []))
                finding('BLOCK' if escalated else 'WARN', 'application-sync-policy', name, ap, bp,
                        'Application sync/prune behavior changes; review deletion/recreation effects.')
        source_changed = a is None or b is None or identity(a) != identity(b)
        deps = set()
        for root, path in zip((oldroot, newroot), paths):
            if path and (root / path).is_dir():
                deps |= dependency_dirs(root, path)
        affected = source_changed or any(f == d or f.startswith(d + '/') for f in changed for d in deps)
        if not affected:
            continue
        if paths[0] != paths[1] and paths[0]:
            finding('WARN', 'application-path', name, paths[0], paths[1],
                    'Source directory moved/renamed; the live controller may lag Git even when final discovery is stable.')
        for index, (root, path, app) in enumerate(zip((oldroot, newroot), paths, (a, b))):
            if not app:
                continue
            if not path:
                finding('BLOCK', 'unsupported-render', name, None, app['object']['spec'].get('source'),
                        'Changed chart-only/multi-source Application requires separate rendered comparison.')
                continue
            for obj in render(root, path):
                if obj.get('kind') in ('PersistentVolumeClaim', 'StatefulSet'):
                    obj.setdefault('metadata', {}).setdefault('namespace', app['object']['spec'].get('destination', {}).get('namespace', ''))
                if not obj.get('metadata', {}).get('name'):
                    raise ValueError(f'{name}: rendered object lacks a comparable metadata.name')
                key = resource_key(obj)
                if obj.get('kind') in PERSISTENT or obj.get('metadata', {}).get('finalizers'):
                    if key in rendered[index] and rendered[index][key][0] != name:
                        finding('BLOCK', 'shared-resource', key, rendered[index][key][0], name, 'Multiple Applications claim this persistent resource.')
                rendered[index][key] = (name, obj)
    for key, (owner, obj) in rendered[0].items():
        next_resource = rendered[1].get(key)
        if obj['kind'] not in PERSISTENT and not obj.get('metadata', {}).get('finalizers') and not (
                next_resource and next_resource[1].get('metadata', {}).get('finalizers')):
            continue
        if next_resource is None:
            finding('BLOCK', 'persistent-resource-disappears', key, {'owner': owner, 'spec': obj.get('spec')}, None,
                    'Persistent object disappears or is renamed; pruning/recreation may destroy data.')
            continue
        newowner, newobj = next_resource
        if owner != newowner:
            finding('BLOCK', 'resource-owner-transfer', key, owner, newowner, 'Argo ownership transfer can prune or conflict.')
        a, b = obj.get('spec', {}), newobj.get('spec', {})
        fields = ['storageClassName', 'volumeName', 'claimRef', 'persistentVolumeReclaimPolicy'] if obj['kind'] in ('PersistentVolumeClaim', 'PersistentVolume') else ['volumeClaimTemplates'] if obj['kind'] == 'StatefulSet' else []
        for field in fields:
            if a.get(field) != b.get(field):
                finding('BLOCK', 'persistent-spec-' + field, key, a.get(field), b.get(field), 'Persistent identity/backend or claim template changes require migration review.')
        oldfinal, newfinal = obj['metadata'].get('finalizers', []), newobj['metadata'].get('finalizers', [])
        if oldfinal != newfinal:
            finding('BLOCK', 'resource-finalizers', key, oldfinal, newfinal, 'Persistent resource deletion behavior changes.')
    return findings, {name: len(apps) for name, apps in {'OLD/OLD': oo, 'OLD/NEW': on, 'NEW/OLD': no, 'NEW/NEW': nn}.items()}


def snapshot(repo, revision, destination):
    result = subprocess.run(['git', 'archive', revision], cwd=repo, capture_output=True, timeout=30, check=True)
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        archive.extractall(destination, filter='data')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='origin/main')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--no-fetch', action='store_true', help='For offline fixtures/CI with an explicitly refreshed base')
    parser.add_argument('--format', choices=['json', 'text'], default='text')
    args = parser.parse_args()
    report = {'status': 'BLOCK', 'findings': []}
    try:
        repo = Path(run('git', 'rev-parse', '--show-toplevel').strip())
        if not args.no_fetch:
            run('git', 'fetch', 'origin', 'main', cwd=repo)
        base = run('git', 'rev-parse', '--verify', args.base + '^{commit}', cwd=repo).strip()
        head = run('git', 'rev-parse', '--verify', args.head + '^{commit}', cwd=repo).strip()
        report.update(base=base, head=head)
        if args.base == 'origin/main':
            run('git', 'merge-base', '--is-ancestor', base, head, cwd=repo)
        changed = run('git', 'diff', '--name-only', base, head, cwd=repo).splitlines()
        with tempfile.TemporaryDirectory(prefix='gitops-risk-') as tmp:
            old, new = Path(tmp) / 'old', Path(tmp) / 'new'
            snapshot(repo, base, old); snapshot(repo, head, new)
            findings, counts = inspect(old, new, changed)
        report.update(findings=findings, application_counts=counts)
        report['status'] = 'BLOCK' if any(f['level'] == 'BLOCK' for f in findings) else 'WARN' if findings else 'PASS'
    except (ValueError, OSError, KeyError, IndexError, TypeError, yaml.YAMLError, subprocess.SubprocessError) as exc:
        report['findings'].append(dict(level='BLOCK', code='check-failed', target='checker', old=None,
                                       new=None, reason=str(exc)[:1000]))
    if args.format == 'json':
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['status']}: {report.get('base', '?')[:12]} -> {report.get('head', '?')[:12]}")
        for finding in report['findings']:
            print(f"{finding['level']} {finding['code']} {finding['target']}: {finding['reason']}")
            print('  old=' + json.dumps(finding['old'], sort_keys=True))
            print('  new=' + json.dumps(finding['new'], sort_keys=True))
    return 1 if report['status'] == 'BLOCK' else 0


if __name__ == '__main__':
    sys.exit(main())
