# Points Intercept's CARTO tiles at the keyed host and pushes CARTO_API_KEY into its settings.
import json
import os
import pathlib
import time
import urllib.request

# CARTO answers 403 when a key is sent to the old fastly host (smittix/intercept still ships it).
OLD_HOST = "cartodb-basemaps-{s}.global.ssl.fastly.net"
NEW_HOST = "{s}.basemaps.cartocdn.com"
for path in pathlib.Path("/app/static/js").rglob("*.js"):
    text = path.read_text(encoding="utf-8")
    if OLD_HOST in text:
        path.write_text(text.replace(OLD_HOST, NEW_HOST), encoding="utf-8")
        print(f"fix-carto-tiles: rewrote {path}")

key = os.environ.get("CARTO_API_KEY", "").strip()
if not key:
    raise SystemExit(0)

body = json.dumps({"key": "offline.carto_key", "value": key}).encode()
for _ in range(60):
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:5050/offline/settings",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        break
    except Exception:
        time.sleep(2)
