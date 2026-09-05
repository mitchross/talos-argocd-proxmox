"""Bootstrap Mink credentials with operator access to 1Password and SurfSense Postgres."""

import hashlib
import json
import re
import secrets
import subprocess
import sys
import urllib.request


def run(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed; sensitive command output suppressed")
    return result.stdout


def sql(statement):
    return run(["kubectl", "-n", "surfsense", "exec", "-i", "deploy/surfsense-postgres",
                "--", "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", "surfsense",
                "-d", "surfsense"], statement)


def main():
    item_args = ["op", "item", "get", "surfsense", "--vault", "homelab-prod", "--format", "json"]
    item = json.loads(run(item_args))
    fields = {f["label"]: f for f in item["fields"]}
    github = fields.get("mink_github_token", {}).get("value") or run(["gh", "auth", "token"]).strip()
    request = urllib.request.Request(
        "https://api.github.com/repos/mitchross/mink-data/contents/wiki?ref=main",
        headers={"Authorization": f"Bearer {github}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if not isinstance(json.load(response), list):
            raise RuntimeError("GitHub wiki directory verification failed")
    owner = sql('SELECT w.id FROM workspaces w JOIN "user" u ON w.user_id=u.id '
                'WHERE w.id=1 AND w.api_access_enabled AND u.is_active;').strip()
    if owner != "1":
        raise RuntimeError("Workspace 1 must have an active owner and API access enabled")

    token = fields.get("mink_api_token", {}).get("value") or f"ss_pat_{secrets.token_urlsafe(32)}"
    if not re.fullmatch(r"ss_pat_[A-Za-z0-9_-]{43}", token):
        raise RuntimeError("Stored SurfSense token has an unexpected format")
    max_days = run(["kubectl", "-n", "surfsense", "exec", "deploy/surfsense", "-c", "api",
                    "--", "python", "-c", "import os; print(os.getenv('PAT_MAX_EXPIRY_DAYS', ''))"]).strip()
    expiry = f"now() + interval '{int(max_days)} days'" if max_days else "NULL"
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Save the recoverable plaintext before registering only its hash in SurfSense.
    for label, value in (("mink_github_token", github), ("mink_api_token", token)):
        if label in fields:
            fields[label].update(type="CONCEALED", value=value)
        else:
            item["fields"].append({"id": label, "label": label, "type": "CONCEALED", "value": value})
    run(["op", "item", "edit", item["id"], "--vault", "homelab-prod", "--format", "json"], json.dumps(item))
    saved = {f["label"]: f for f in json.loads(run(item_args))["fields"]}
    for label, value in (("mink_github_token", github), ("mink_api_token", token)):
        if saved[label]["value"] != value or saved[label]["type"] != "CONCEALED":
            raise RuntimeError("1Password read-back verification failed")

    # Operator bootstrap for 0.0.39: preserve existing PATs and its SHA-256 token format.
    sql(f"""INSERT INTO personal_access_tokens
        (user_id, token_hash, token_prefix, label, expires_at, created_at)
        SELECT user_id, '{token_hash}', '{token[:16]}', 'Mink Git sync', {expiry}, now()
        FROM workspaces WHERE id=1
        ON CONFLICT (token_hash) DO NOTHING;
    """)
    valid = sql(f"""SELECT p.id FROM personal_access_tokens p JOIN workspaces w ON p.user_id=w.user_id
        WHERE w.id=1 AND p.token_hash='{token_hash}' AND (p.expires_at IS NULL OR p.expires_at>now());
    """).strip()
    if not valid.isdigit():
        raise RuntimeError("Stored SurfSense token is expired or belongs to another account")
    print(f"Both concealed 1Password fields verified; SurfSense PAT ID {valid} registered")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.exit(f"Credential bootstrap failed: {type(error).__name__}; inspect access without printing secrets")
