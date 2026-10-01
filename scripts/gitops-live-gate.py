#!/usr/bin/env python3
"""Read-only prerequisite gate for this repo's root/ApplicationSet topology.

The reviewed JSON plan supplies exact safety fields and pre-migration resource
UIDs. This is a point-in-time observation, never permission to merge or delete.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = 'https://github.com/mitchross/talos-argocd-proxmox.git'
ROOT_PATH = 'infrastructure/controllers/argocd/apps'
KINDS = {'Namespace': 'namespaces', 'PersistentVolumeClaim': 'persistentvolumeclaims',
         'PersistentVolume': 'persistentvolumes', 'StatefulSet': 'statefulsets.apps'}
MISSING = object()


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f'{args[0]} query failed: {result.stderr.strip()[:500]}')
    return result.stdout.strip()


def pointer(obj, path):
    if not path.startswith('/'):
        raise ValueError(f'Expected RFC 6901 JSON pointer, got {path}')
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        try:
            obj = obj[int(part)] if isinstance(obj, list) else obj[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return MISSING
    return obj


def validate_plan(plan):
    for field in ('context', 'server', 'application_sets', 'applications', 'resources'):
        if field not in plan:
            raise ValueError(f'Plan requires {field}')
    if not plan['context'] or not plan['server'] or not plan['application_sets'] or not plan['applications']:
        raise ValueError('Explicit cluster identity and nonempty affected controller/application scope required')
    names = set()
    for item in plan['application_sets']:
        if item['name'] not in ('infrastructure', 'monitoring', 'my-apps', 'database'):
            raise ValueError('Only the repository\'s four ApplicationSets are supported')
        if not item.get('fields'):
            raise ValueError('Each ApplicationSet requires exact prerequisite field expectations')
        names.add(item['name'])
    for item in plan['applications']:
        if item['owner_appset'] not in names:
            raise ValueError('Application owner must be an affected ApplicationSet')
        if item.get('resources_finalizer') not in ('absent', 'present'):
            raise ValueError('Explicit resources_finalizer expectation required')
        for field in ('/spec/source/path', '/spec/destination/namespace'):
            if field not in item.get('fields', {}):
                raise ValueError(f'Application requires expected {field}')
    for item in plan['resources']:
        if item['kind'] not in KINDS or not item.get('uid'):
            raise ValueError('Persistent resource kind and pre-migration UID required')
        if item['kind'] in ('PersistentVolumeClaim', 'StatefulSet') and not item.get('namespace'):
            raise ValueError('Namespaced resource requires explicit namespace')
        if item['kind'] == 'PersistentVolumeClaim' and '/spec/volumeName' not in item.get('fields', {}):
            raise ValueError('PVC requires expected PV binding /spec/volumeName')


class Gate:
    def __init__(self, get, revision_ok, commit):
        self.get, self.revision_ok, self.commit = get, revision_ok, commit
        self.findings = []
        self.observations = []

    def require(self, ok, target, check, expected, actual):
        self.observations.append({'target': target, 'check': check, 'expected': expected, 'actual': actual})
        if not ok:
            self.findings.append({'level': 'BLOCK', 'target': target, 'check': check,
                                  'expected': expected, 'actual': actual})

    def fetch(self, kind, name, namespace):
        obj = self.get(kind, name, namespace)
        target = f'{kind}/{namespace}/{name}'
        self.require(obj.get('metadata', {}).get('name') == name, target, 'object identity', name,
                     obj.get('metadata', {}).get('name'))
        self.require(not obj.get('metadata', {}).get('deletionTimestamp'), target, 'not terminating', None,
                     obj.get('metadata', {}).get('deletionTimestamp'))
        return obj, target

    def fields(self, obj, target, fields):
        for field, expected in fields.items():
            actual = pointer(obj, field)
            self.require(actual is not MISSING and actual == expected, target, field, expected,
                         '<missing>' if actual is MISSING else actual)

    def healthy(self, obj, target, allowed_health=('Healthy',)):
        if not allowed_health:
            raise ValueError('Acceptable health list cannot be empty')
        status = obj.get('status', {})
        self.require(status.get('sync', {}).get('status') == 'Synced', target, 'sync', 'Synced', status.get('sync', {}).get('status'))
        health = status.get('health', {}).get('status')
        self.require(health in allowed_health, target, 'health', list(allowed_health), health)
        phase = status.get('operationState', {}).get('phase')
        self.require(phase not in ('Failed', 'Error', 'Running', 'Terminating'), target, 'no failed/in-progress operation',
                     'Succeeded or no operation', phase)
        revision = status.get('sync', {}).get('revision')
        self.require(bool(revision) and self.revision_ok(revision), target, 'comparison revision', self.commit, revision)

    def inspect(self, plan):
        validate_plan(plan)
        root, target = self.fetch('applications.argoproj.io', 'root', 'argocd')
        self.fields(root, target, {'/spec/source/repoURL': REPO, '/spec/source/path': ROOT_PATH,
                                  '/spec/source/targetRevision': 'main'})
        self.healthy(root, target)
        operation = root.get('status', {}).get('operationState', {})
        revision = operation.get('syncResult', {}).get('revision')
        self.require(operation.get('phase') == 'Succeeded', target, 'successful operation', 'Succeeded', operation.get('phase'))
        self.require(bool(revision) and self.revision_ok(revision), target, 'successful operation revision', self.commit, revision)
        self.require(root.get('status', {}).get('sync', {}).get('revision') == revision, target,
                     'operation/comparison agreement', revision, root.get('status', {}).get('sync', {}).get('revision'))
        self.require(bool(operation.get('finishedAt')), target, 'operation finished', 'finishedAt present', operation.get('finishedAt'))
        sets = {}
        for item in plan['application_sets']:
            obj, target = self.fetch('applicationsets.argoproj.io', item['name'], 'argocd')
            self.fields(obj, target, item['fields'])
            self.require(bool(obj.get('metadata', {}).get('uid')), target, 'controller UID', 'present', obj.get('metadata', {}).get('uid'))
            sets[item['name']] = obj
        for item in plan['applications']:
            obj, target = self.fetch('applications.argoproj.io', item['name'], 'argocd')
            self.fields(obj, target, {**item['fields'], '/spec/source/repoURL': REPO, '/spec/source/targetRevision': 'main'})
            self.healthy(obj, target, item.get('acceptable_health', ['Healthy']))
            owner = sets[item['owner_appset']]
            refs = obj.get('metadata', {}).get('ownerReferences', [])
            expected = {'name': item['owner_appset'], 'uid': owner['metadata'].get('uid'), 'kind': 'ApplicationSet', 'controller': True}
            self.require(any(all(ref.get(k) == v for k, v in expected.items()) for ref in refs),
                         target, 'controller ownership', expected, refs)
            finalizers = obj.get('metadata', {}).get('finalizers', [])
            has_finalizer = any(f.startswith('resources-finalizer.argocd.argoproj.io') for f in finalizers)
            expected_finalizer = item['resources_finalizer'] == 'present'
            self.require(has_finalizer == expected_finalizer, target, 'resources finalizer', item['resources_finalizer'], finalizers)
            preserved = owner.get('spec', {}).get('syncPolicy', {}).get('preserveResourcesOnDeletion', False)
            self.require(has_finalizer != bool(preserved), target, 'preservation/finalizer consistency',
                         'absent' if preserved else 'present', finalizers)
        for item in plan['resources']:
            obj, target = self.fetch(KINDS[item['kind']], item['name'], item.get('namespace', ''))
            self.require(obj.get('metadata', {}).get('uid') == item['uid'], target, 'surviving UID', item['uid'], obj.get('metadata', {}).get('uid'))
            self.fields(obj, target, item.get('fields', {}))
            if item['kind'] == 'PersistentVolumeClaim':
                self.require(obj.get('status', {}).get('phase') == 'Bound', target, 'PVC bound', 'Bound', obj.get('status', {}).get('phase'))
        return not self.findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--commit', required=True, help='Full merged prerequisite SHA, usually the PR merge commit')
    parser.add_argument('--pr', type=int, help='Additionally prove this specific PR is merged at --commit')
    parser.add_argument('--allow-descendant', action='store_true', help='Allow a later merged operation that contains the prerequisite and still satisfies all fields')
    parser.add_argument('--format', choices=['json', 'text'], default='text')
    args = parser.parse_args()
    start = datetime.now(timezone.utc)
    report = {'status': 'BLOCK', 'prerequisite': args.commit, 'observed_at': start.isoformat(),
              'findings': [], 'observations': []}
    gate = None
    try:
        if not re.fullmatch('[0-9a-f]{40}', args.commit):
            raise ValueError('--commit must be a full 40-character SHA')
        plan = json.loads(args.plan.read_text()); validate_plan(plan)
        report.update(context=plan['context'], server=plan['server'])
        command('git', 'fetch', 'origin', 'main')
        command('git', 'merge-base', '--is-ancestor', args.commit, 'origin/main')
        report['merged_on_main'] = True
        if args.pr is not None:
            pr = json.loads(command('gh', 'pr', 'view', str(args.pr), '--repo', 'mitchross/talos-argocd-proxmox',
                                    '--json', 'state,mergeCommit,baseRefName'))
            if pr['state'] != 'MERGED' or pr['baseRefName'] != 'main' or pr['mergeCommit']['oid'] != args.commit:
                raise ValueError('PR is not merged into main at the supplied prerequisite SHA')
            report['merged_pr'] = args.pr
        def revision_ok(revision):
            if revision == args.commit:
                return True
            if not args.allow_descendant or not re.fullmatch('[0-9a-f]{40}', revision):
                return False
            try:
                command('git', 'merge-base', '--is-ancestor', args.commit, revision)
                command('git', 'merge-base', '--is-ancestor', revision, 'origin/main')
                return True
            except ValueError:
                return False
        actual_server = command('kubectl', '--context', plan['context'], 'config', 'view', '--minify',
                                '-o', 'jsonpath={.clusters[0].cluster.server}')
        if actual_server != plan['server']:
            raise ValueError('Kubernetes context resolves to a different server than the reviewed plan')
        def get(kind, name, namespace):
            argv = ['kubectl', '--context', plan['context'], 'get', kind, name, '-o', 'json', '--request-timeout=10s']
            if namespace:
                argv += ['-n', namespace]
            return json.loads(command(*argv))
        gate = Gate(get, revision_ok, args.commit)
        if gate.inspect(plan):
            report['status'] = 'PASS'
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        report['findings'].append({'level': 'BLOCK', 'target': 'gate', 'check': 'observation failed', 'reason': str(exc)[:1000]})
    if gate:
        report['findings'] += gate.findings
        report['observations'] = gate.observations
    finished = datetime.now(timezone.utc)
    report['completed_at'] = finished.isoformat()
    report['valid_until'] = datetime.fromtimestamp(finished.timestamp() + 300, timezone.utc).isoformat()
    if (finished - start).total_seconds() > 300:
        report['status'] = 'BLOCK'
        report['findings'].append({'level': 'BLOCK', 'target': 'gate', 'check': 'snapshot exceeded five-minute observation window'})
    if args.format == 'json':
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['status']}: prerequisite {args.commit} (snapshot only; no merge authorization)")
        for finding in report['findings']:
            print(json.dumps(finding, sort_keys=True))
        print(f"Observed {report['observed_at']}; rerun after five minutes or any relevant change.")
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
