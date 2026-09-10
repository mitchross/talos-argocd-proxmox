"""Bounded Kubernetes/Temporal clients for the GitOps maintenance jobs."""

import json
import os
from pathlib import Path
import ssl
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class Kubernetes:
    def __init__(self):
        account = Path('/var/run/secrets/kubernetes.io/serviceaccount')
        self.token = (account / 'token').read_text().strip()
        self.context = ssl.create_default_context(cafile=str(account / 'ca.crt'))
        self.base = 'https://kubernetes.default.svc'

    def request(self, path, method='GET', body=None):
        headers = {'Authorization': f'Bearer {self.token}'}
        if body is not None:
            headers['Content-Type'] = (
                'application/merge-patch+json' if method == 'PATCH' else 'application/json'
            )
        request = Request(self.base + path, method=method, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, context=self.context, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and method in ('GET', 'DELETE'):
                return None
            raise


def temporal(*args):
    try:
        result = subprocess.run([
            '/tools/temporal', '--disable-config-file', '--disable-config-env',
            '--address', os.environ['TEMPORAL_ADDRESS'],
            '--namespace', os.environ['TEMPORAL_NAMESPACE'],
            '--command-timeout', '30s', '--output', 'json', *args,
        ], check=True, capture_output=True, text=True, timeout=35)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'Temporal command failed: {error.stderr.strip()}') from error
    # A successful delete emits no JSON; reads must always provide a JSON value.
    if 'delete-version' in args and not result.stdout.strip():
        return {}
    return json.loads(result.stdout)
