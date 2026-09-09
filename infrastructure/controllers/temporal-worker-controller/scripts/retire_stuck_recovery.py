"""Idempotently retire the identified old Job after its CronJob is repaired."""

from maintenance import Kubernetes


NAMESPACE = 'temporal-worker-controller'
NAME = 'temporal-worker-controller-identity-recovery'
JOB = NAME + '-29814005'
UID = 'bb04f361-8e7c-4ef4-8541-fd29193da863'
BASE = f'/apis/batch/v1/namespaces/{NAMESPACE}'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def retire(api):
    job = api.request(f'{BASE}/jobs/{JOB}')
    if job is None:
        print('identified stuck Job already absent')
        return
    cron = api.request(f'{BASE}/cronjobs/{NAME}')
    template = cron['spec']['jobTemplate']['spec']
    container = template['template']['spec']['containers'][0]
    require(template['activeDeadlineSeconds'] == 240, 'CronJob deadline not repaired')
    require(container['resources']['requests']['memory'] == '768Mi', 'CronJob request not repaired')
    require(container['resources']['limits']['memory'] == '1Gi', 'CronJob limit not repaired')
    old = job['spec']['template']['spec']
    require(job['metadata']['uid'] == UID, 'Job UID differs from incident')
    require(any(o.get('kind') == 'CronJob' and o.get('name') == NAME
               and o.get('controller') is True and o.get('uid') == cron['metadata']['uid']
               for o in job['metadata']['ownerReferences']), 'unexpected Job owner')
    require(old['containers'][0]['resources']['limits']['memory'] == '128Mi', 'unexpected old limit')
    require('activeDeadlineSeconds' not in job['spec'], 'unexpected old deadline')
    old_cm = next(v['configMap']['name'] for v in old['volumes'] if v['name'] == 'recovery-script')
    new_cm = next(v['configMap']['name'] for v in template['template']['spec']['volumes']
                  if v['name'] == 'recovery-script')
    require(new_cm != old_cm, 'CronJob still references the old script')
    api.request(f'{BASE}/jobs/{JOB}', 'DELETE', {
        'apiVersion': 'v1', 'kind': 'DeleteOptions', 'propagationPolicy': 'Foreground',
        'preconditions': {'uid': UID, 'resourceVersion': job['metadata']['resourceVersion']},
    })
    print('retired identified stuck recovery Job; next schedule uses repaired template')


if __name__ == '__main__':
    retire(Kubernetes())
