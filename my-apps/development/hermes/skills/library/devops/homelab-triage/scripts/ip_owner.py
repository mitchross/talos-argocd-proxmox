#!/usr/bin/env python3
"""Look up network owner for IPs via ip-api.com batch (100 per call, ~15 calls/min).

Usage: ip_owner.py <ips.txt> <cache.json>
ips.txt: one IP per line. cache.json is read if present and rewritten with new results,
so reruns only look up IPs not seen before. Prints a count by kind
(datacenter / proxy / mobile / residential).
"""
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

FIELDS = "query,status,countryCode,as,org,isp,hosting,proxy,mobile"


def kind(d):
    if d.get("hosting"):
        return "datacenter"
    if d.get("proxy"):
        return "proxy"
    if d.get("mobile"):
        return "mobile"
    return "residential" if d.get("status") == "success" else "unknown"


def main():
    ips = [l.strip() for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
    cache_path = Path(sys.argv[2])
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = sorted({ip for ip in ips if ip not in cache})
    for i in range(0, len(todo), 100):
        req = urllib.request.Request(
            f"http://ip-api.com/batch?fields={FIELDS}",
            data=json.dumps(todo[i:i + 100]).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            for d in json.load(r):
                cache[d["query"]] = d
        cache_path.write_text(json.dumps(cache))
        if i + 100 < len(todo):
            time.sleep(4.2)  # free tier: 15 batch calls per minute
    print(dict(Counter(kind(cache.get(ip, {})) for ip in set(ips))))


if __name__ == "__main__":
    main()
