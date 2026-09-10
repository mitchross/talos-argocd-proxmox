"""Retire deal-scout's unused inactive versions; let TWC delete their Deployments."""

import json
import os
import re
import time
from urllib.parse import quote

from maintenance import Kubernetes, temporal


ANNOTATION = 'sunset.vanillax.dev/inactive-retirement'
NAMESPACE = 'deal-scout'
NAME = 'deal-scout'
DEPLOYMENT_NAME = f'{NAMESPACE}/{NAME}'
WORKER_PATH = f'/apis/temporal.io/v1alpha1/namespaces/{NAMESPACE}/workerdeployments/{NAME}'
DEPLOYMENTS_PATH = f'/apis/apps/v1/namespaces/{NAMESPACE}/deployments'


def duration(value):
    if value == '0':
        return 0
    parts = re.findall(r'(\d+(?:\.\d+)?)(ns|us|µs|μs|ms|s|m|h)', value)
    if not parts or ''.join(number + unit for number, unit in parts) != value:
        raise ValueError(f'unsupported sunset duration: {value!r}')
    units = {'ns': 1e-9, 'us': 1e-6, 'µs': 1e-6, 'μs': 1e-6,
             'ms': .001, 's': 1, 'm': 60, 'h': 3600}
    return sum(float(number) * units[unit] for number, unit in parts)


def eligible(worker, deployment):
    if not worker or not deployment:
        return False
    meta, status = worker['metadata'], worker.get('status', {})
    dm = deployment['metadata']
    build = dm.get('labels', {}).get('temporal.io/build-id')
    if meta.get('deletionTimestamp') or dm.get('deletionTimestamp') or not build:
        return False
    if not any(c.get('type') == 'Ready' and c.get('status') == 'True'
               and c.get('observedGeneration') == meta['generation']
               for c in status.get('conditions', [])):
        return False
    if worker['spec']['workerOptions']['temporalNamespace'] != os.environ['TEMPORAL_NAMESPACE']:
        return False
    if build in (status.get('targetVersion', {}).get('buildID'),
                 (status.get('currentVersion') or {}).get('buildID')):
        return False
    if not any(o.get('kind') == 'WorkerDeployment' and o.get('name') == NAME
               and o.get('apiVersion') == 'temporal.io/v1alpha1'
               and o.get('controller') is True and o.get('uid') == meta['uid']
               for o in dm.get('ownerReferences', [])):
        return False
    ds = deployment.get('status', {})
    if (deployment['spec'].get('replicas') != 0
            or ds.get('replicas', 0) != 0 or ds.get('terminatingReplicas', 0) != 0
            or ds.get('observedGeneration') != dm['generation']):
        return False
    return any(v.get('buildID') == build and v.get('status') == 'Inactive'
               and v.get('deployment', {}).get('uid') == dm['uid']
               for v in status.get('deprecatedVersions', []))


def server_unused(worker, build, cli):
    server = cli('worker', 'deployment', 'describe', '--name', DEPLOYMENT_NAME)
    if server['name'] != DEPLOYMENT_NAME:
        raise ValueError('unexpected Temporal deployment')
    identity = server.get('managerIdentity', '')
    if (not identity.startswith('temporal-worker-controller/temporal-worker-controller/')
            or identity != worker['status'].get('managerIdentity')):
        raise ValueError('controller manager identity is not synchronized')
    routing = server['routingConfig']
    if build in (routing['currentVersionBuildID'], routing['rampingVersionBuildID']):
        return False
    summaries = [v for v in server['versionSummaries'] if v['BuildID'] == build]
    if len(summaries) != 1 or summaries[0]['drainageStatus'] != 'unspecified':
        return False
    # Use the same visibility filter as Temporal Server v1.31.2 drainage checks.
    version = f'{DEPLOYMENT_NAME}:{build}'.replace("'", "''")
    result = cli('workflow', 'count', '--query',
                 f"TemporalWorkerDeploymentVersion = '{version}' AND "
                 "TemporalWorkflowVersioningBehavior = 'Pinned' AND ExecutionStatus = 'Running'")
    # The pinned CLI omits its zero-valued count, emitting {} for zero matches.
    count = result.get('count', 0) if isinstance(result, dict) else None
    if isinstance(count, bool) or not isinstance(count, (int, str)) or not str(count).isdigit():
        raise ValueError('invalid workflow count')
    if set(result) - {'count', 'groups'} or result.get('groups'):
        raise ValueError('unexpected workflow count response')
    return int(count) == 0


def mark(api, deployment, value, dry_run):
    if dry_run:
        print(f"dry-run: retirement annotation for {deployment['metadata']['name']}: {value}")
        return
    meta = deployment['metadata']
    api.request(f"{DEPLOYMENTS_PATH}/{quote(meta['name'], safe='')}", 'PATCH', {
        'metadata': {'uid': meta['uid'], 'resourceVersion': meta['resourceVersion'],
                     'annotations': {ANNOTATION: value}},
    })


def reconcile(api, cli, now, dry_run=False):
    worker = api.request(WORKER_PATH)
    if worker is None:
        print('WorkerDeployment absent; nothing to retire')
        return
    deployments = api.request(DEPLOYMENTS_PATH + '?labelSelector=temporal.io%2Fdeployment-name%3Ddeal-scout')['items']
    failures = []
    for deployment in deployments:
        try:
            reconcile_version(api, cli, worker, deployment, now, dry_run)
        except Exception as error:
            print(f"retirement failed for {deployment['metadata']['name']}: {error}")
            failures.append(error)
    if failures:
        raise failures[0]


def reconcile_version(api, cli, worker, deployment, now, dry_run):
    meta = deployment['metadata']
    stamp = meta.get('annotations', {}).get(ANNOTATION)
    if not eligible(worker, deployment):
        if stamp:
            mark(api, deployment, None, dry_run)
        return
    build = meta['labels']['temporal.io/build-id']
    if not server_unused(worker, build, cli):
        if stamp:
            mark(api, deployment, None, dry_run)
        print(f'preserving {build}: routing, drainage or pinned workflows')
        return
    generation = worker['metadata']['generation']
    key = [worker['metadata']['uid'], generation, meta['uid'], meta['generation']]
    try:
        saved = json.loads(stamp) if stamp else {}
        since = float(saved['since']) if saved.get('key') == key else now
        if not 0 <= since <= now:
            since = now
    except (ValueError, TypeError, KeyError, AttributeError):
        since = now
    if since == now:
        mark(api, deployment, json.dumps({'key': key, 'since': now}), dry_run)
        print(f'observing inactive retirement for {build}')
        return
    policy = worker['spec'].get('sunset', {})
    delay = duration(policy.get('scaledownDelay', '1h')) + duration(policy.get('deleteDelay', '24h'))
    if now - since < max(delay, 600):
        print(f'preserving {build}: retirement delay has not elapsed')
        return
    fresh_worker = api.request(WORKER_PATH)
    fresh_deployment = api.request(f"{DEPLOYMENTS_PATH}/{quote(meta['name'], safe='')}")
    if (not eligible(fresh_worker, fresh_deployment)
            or fresh_worker['metadata']['uid'] != key[0]
            or fresh_worker['metadata']['generation'] != generation
            or fresh_deployment['metadata']['uid'] != meta['uid']
            or fresh_deployment['metadata']['generation'] != meta['generation']
            or fresh_deployment['metadata'].get('annotations', {}).get(ANNOTATION) != stamp):
        print(f'preserving {build}: Kubernetes state changed')
        return
    if not server_unused(fresh_worker, build, cli):
        mark(api, fresh_deployment, None, dry_run)
        return
    if dry_run:
        print(f'dry-run: would delete Temporal version {build}')
        return
    # No --skip-drainage: the server also rejects current/ramping and active pollers.
    cli('--identity', fresh_worker['status']['managerIdentity'], 'worker', 'deployment',
        'delete-version', '--deployment-name', DEPLOYMENT_NAME, '--build-id', build)
    print(f'deleted Temporal version {build}; controller will reap its Deployment')


if __name__ == '__main__':
    reconcile(Kubernetes(), temporal, time.time(), os.environ.get('DRY_RUN', 'true') != 'false')
