#!/usr/bin/env python3
"""Validate Hermes model routes, fallbacks and aux providers in a config.yaml.

Run with the Hermes venv: /opt/hermes/.venv/bin/python validate_routes.py <config.yaml>
Uses the advanced-delegation plugin's own validator (store.validate_route) and
resolves each provider/model the way Hermes does (resolve_provider_client).
Provider credentials come from the live HERMES_HOME; nothing is written.
"""
import importlib.util
import sys

sys.path.insert(0, "/opt/hermes")
import ruamel.yaml as ry  # noqa: E402
from agent.auxiliary_client import resolve_provider_client  # noqa: E402

STORE = "/opt/data/plugins/advanced-delegation/store.py"


def main(path):
    cfg = ry.YAML(typ="safe").load(open(path))
    spec = importlib.util.spec_from_file_location("ad_store", STORE)
    store = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(store)
    ok = True

    def resolves(provider, model):
        try:
            client = resolve_provider_client(provider, model)
            client = client[0] if isinstance(client, tuple) else client
            return client is not None
        except Exception as exc:  # report, keep going
            print(f"  resolve error {provider}/{model}: {exc}")
            return False

    mm = (cfg.get("delegation", {}).get("backends", {}).get("model_map", {}))
    routes = mm.get("options", [])
    names = {r["name"] for r in routes}
    if mm.get("default") and mm["default"] not in names:
        print(f"FAIL default {mm['default']!r} is not a route"); ok = False
    for r in routes:
        problems = store.validate_route(r, [o for o in routes if o is not r])
        if not resolves(r.get("provider"), r.get("model")):
            problems.append("provider/model does not resolve")
        for fb in r.get("fallback_providers") or []:
            if not resolves(fb["provider"], fb["model"]):
                problems.append(f"fallback {fb} does not resolve")
        print(f"route {r['name']}: {'OK' if not problems else problems}")
        ok &= not problems
    for fb in cfg.get("fallback_providers") or []:
        good = resolves(fb["provider"], fb["model"])
        print(f"chat fallback {fb['provider']}/{fb['model']}: {'OK' if good else 'FAIL'}")
        ok &= good
    for task, aux in (cfg.get("auxiliary") or {}).items():
        if aux.get("provider") and aux.get("model"):
            good = resolves(aux["provider"], aux["model"])
            print(f"aux {task}: {'OK' if good else 'FAIL'}")
            ok &= good
    enabled = (cfg.get("plugins") or {}).get("enabled") or []
    if cfg.get("delegation", {}).get("backend") == "model_map" and "advanced-delegation" not in enabled:
        print("FAIL backend model_map but advanced-delegation not in plugins.enabled"); ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1])
