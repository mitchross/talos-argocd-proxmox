#!/usr/bin/env python3
"""Save one authenticated Wyze Web View service cookie to the existing 1Password item."""

import argparse
import json
import subprocess
import sys


def run(arguments, data=None):
    result = subprocess.run(arguments, input=data, capture_output=True, text=True, timeout=90)
    if result.returncode:
        # CLI errors can include input. Do not repeat them alongside authentication data.
        raise RuntimeError(arguments[0] + " command failed")
    return json.loads(result.stdout)


def save(session, account):
    browser = ["agent-browser", "--session", session]
    current = run([*browser, "get", "url", "--json"])["data"]["url"]
    if not current.startswith("https://my.wyze.com/"):
        raise RuntimeError("Select the authenticated Wyze Web View tab first")
    opened = False
    try:
        run([*browser, "tab", "new", "https://services.wyze.com/favicon.ico", "--json"])
        opened = True
        cookies = run([*browser, "cookies", "--json"])["data"]["cookies"]
        matches = [
            c for c in cookies
            if c["domain"] == "services.wyze.com" and c["name"] == "session" and c["path"] == "/"
        ]
        if len(matches) != 1:
            raise RuntimeError("Complete a fresh official Web View login first")
        value = matches[0]["value"]
        item = run(["op", "item", "get", "wyze-bridge", "--account", account, "--format=json"])
        if item["vault"]["name"] != "homelab-prod":
            raise RuntimeError("The Wyze item must be in homelab-prod")
        if item.get("passkeys") or any(f.get("type") == "PASSKEY" for f in item.get("fields", [])):
            raise RuntimeError("JSON editing cannot preserve a passkey; use another enrollment method")
        previous = {f["id"]: f.get("value") for f in item["fields"]}
        existing = next((f for f in item["fields"] if f.get("label") == "WEB_SESSION"), None)
        if existing is None:
            existing = {"id": "wyze-web-session", "label": "WEB_SESSION"}
            item["fields"].append(existing)
        existing.update(type="CONCEALED", value=value)
        updated = run(
            ["op", "item", "edit", item["id"], "--vault", item["vault"]["id"],
             "--account", account, "--format=json"],
            json.dumps(item),
        )
        saved = next(f for f in updated["fields"] if f.get("label") == "WEB_SESSION")
        if saved["value"] != value:
            raise RuntimeError("1Password did not retain the session field")
        fields = {f["id"]: f.get("value") for f in updated["fields"]}
        if any(fields.get(key) != old for key, old in previous.items() if key != existing["id"]):
            raise RuntimeError("1Password changed another field during enrollment")
        print("Saved concealed WEB_SESSION in homelab-prod/wyze-bridge.")
    finally:
        if opened:
            subprocess.run([*browser, "tab", "close"], capture_output=True, text=True, timeout=30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="agent-browser session logged in to my.wyze.com")
    parser.add_argument("--account", default="my.1password.com")
    arguments = parser.parse_args()
    try:
        save(arguments.session, arguments.account)
    except (RuntimeError, KeyError, subprocess.TimeoutExpired):
        print("Session enrollment failed. Check the Web View login and 1Password CLI authorization.", file=sys.stderr)
        sys.exit(1)
