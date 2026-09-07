#!/usr/bin/env python3
"""Create missing Langfuse bootstrap credentials in the existing 1Password vault.

Requires an authenticated op CLI. Existing items are validated, never rotated.
Secret values are passed over stdin and never printed or written to disk.
"""
import json
import secrets
import subprocess
import uuid

VAULT = 'homelab-prod'
TITLE = 'langfuse'
PASSWORD_FIELDS = ('salt', 'encryption-key', 'nextauth-secret', 'postgres-password',
                   'clickhouse-password', 'redis-password', 'admin-password')
REQUIRED = {*PASSWORD_FIELDS, 'public-key', 'secret-key', 'admin-email'}


def op(*args, payload=None):
    result = subprocess.run(['op', *args, '--format=json'],
                            input=json.dumps(payload) if payload else None,
                            text=True, capture_output=True)
    if result.returncode:
        raise SystemExit('1Password operation failed. Unlock/sign in to op and check vault write access; no secret values were displayed.')
    return json.loads(result.stdout)


def main():
    items = [item for item in op('item', 'list', '--vault', VAULT) if item['title'] == TITLE]
    if len(items) > 1:
        raise SystemExit('Multiple langfuse items exist; resolve the duplicate titles before deployment.')
    if items:
        item = op('item', 'get', items[0]['id'], '--vault', VAULT)
        fields = {field.get('label'): field.get('value') for field in item.get('fields', [])}
        if missing := sorted(name for name in REQUIRED if not fields.get(name)):
            raise SystemExit('Existing item preserved; missing fields: ' + ', '.join(missing))
        print('Existing homelab-prod/langfuse credentials validated and preserved.')
        return
    identity = op('whoami')
    email = identity.get('email')
    if not email:
        raise SystemExit('The active 1Password account has no email; cannot seed the Langfuse owner.')
    fields = {name: secrets.token_hex(32) for name in PASSWORD_FIELDS}
    fields.update({'public-key': 'pk-lf-' + str(uuid.uuid4()),
                   'secret-key': 'sk-lf-' + str(uuid.uuid4()), 'admin-email': email})
    item = op('item', 'create', '--vault', VAULT, payload={
        'title': TITLE, 'category': 'LOGIN',
        'fields': [{'id': name, 'label': name, 'value': value,
                    'type': 'STRING' if name == 'admin-email' else 'CONCEALED'}
                   for name, value in fields.items()]})
    if not item.get('id'):
        raise SystemExit('1Password did not return an item ID; verify before retrying.')
    print('Created homelab-prod/langfuse. Credentials remain in 1Password; no values displayed.')


if __name__ == '__main__':
    main()
