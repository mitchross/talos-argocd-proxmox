#!/usr/bin/env python3
"""Generate a 'what is broken now' Grafana dashboard JSON (Prometheus uid 'prometheus').

Usage: python3 status-dashboard.py <out.json>
Edit TILES / TABLES below. Validate every expr against /api/v1/query before committing.
"""
import json, sys

DS = {"type": "prometheus", "uid": "prometheus"}
UID, TITLE = "homelab-now", "Homelab now"
AF = 'alertname!~"Watchdog|InfoInhibitor"'
ARGO = 'argocd_app_info{health_status!="Healthy"} or argocd_app_info{sync_status!="Synced"}'
PODS = 'kube_pod_status_phase{phase=~"Pending|Failed|Unknown"} == 1'

# (title, count expr, description)
TILES = [
    ("Alerts firing", f'count(ALERTS{{alertstate="firing",{AF}}}) or vector(0)', "Firing alerts."),
    ("Argo apps not OK", f"count({ARGO}) or vector(0)", "Not Synced and Healthy."),
    ("Pods not running", f"count({PODS}) or vector(0)", "Pending, Failed or Unknown."),
]
# (title, expr, columns to keep in order, {label: header}, value header or None, value unit, width)
TABLES = [
    ("Alerts firing now",
     f'(ALERTS_FOR_STATE{{{AF}}} * 1000) and ignoring(alertstate) ALERTS{{alertstate="firing",{AF}}}',
     ["alertname", "severity", "namespace", "pod"],
     {"alertname": "Alert", "severity": "Severity", "namespace": "Namespace", "pod": "Pod"},
     "Firing since", "dateTimeFromNow", 24),
    ("Argo CD apps not OK", ARGO, ["name", "sync_status", "health_status"],
     {"name": "App", "sync_status": "Sync", "health_status": "Health"}, None, None, 12),
    ("Pods not running", PODS, ["namespace", "pod", "phase"],
     {"namespace": "Namespace", "pod": "Pod", "phase": "Phase"}, None, None, 12),
]

panels, nid = [], iter(range(1, 1000))
w = 24 // max(len(TILES), 1)
for i, (title, expr, desc) in enumerate(TILES):
    panels.append({
        "id": next(nid), "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": 4, "w": w, "x": i * w, "y": 0},
        "targets": [{"refId": "A", "datasource": DS, "expr": expr, "instant": True, "range": False}],
        "fieldConfig": {"defaults": {"decimals": 0, "noValue": "0", "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None},
                                                          {"color": "red", "value": 1}]}}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    })
x = y = 0
y = 4
for title, expr, cols, names, vname, vunit, width in TABLES:
    if x + width > 24:
        x, y = 0, y + 9
    keep = cols + (["Value"] if vname else [])
    rename = dict(names, **({"Value": vname} if vname else {}))
    p = {
        "id": next(nid), "type": "table", "title": title, "datasource": DS,
        "gridPos": {"h": 9, "w": width, "x": x, "y": y},
        "targets": [{"refId": "A", "datasource": DS, "expr": expr, "instant": True,
                     "range": False, "format": "table"}],
        # filter first: label sets vary per series, so whitelist columns before renaming
        "transformations": [
            {"id": "filterFieldsByName", "options": {"include": {"names": keep}}},
            {"id": "organize", "options": {"indexByName": {k: i for i, k in enumerate(keep)},
                                            "renameByName": rename}}],
        "fieldConfig": {"defaults": {"noValue": "All clear", "custom": {"align": "left"}},
                        "overrides": []},
        "options": {"showHeader": True, "cellHeight": "sm"},
    }
    if vunit:
        p["fieldConfig"]["overrides"].append({"matcher": {"id": "byName", "options": vname},
                                              "properties": [{"id": "unit", "value": vunit}]})
    panels.append(p)
    x += width

dash = {"id": None, "uid": UID, "title": TITLE, "tags": ["start-here"], "editable": False,
        "schemaVersion": 42, "refresh": "1m", "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"hidden": True}, "templating": {"list": []}, "panels": panels}
with open(sys.argv[1], "w") as f:
    json.dump(dash, f, indent=2)
    f.write("\n")
print("wrote", sys.argv[1], len(panels), "panels")
