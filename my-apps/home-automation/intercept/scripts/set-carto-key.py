# Pushes CARTO_API_KEY into Intercept's settings so CARTO tiles render without the watermark.
import json
import os
import time
import urllib.request

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
