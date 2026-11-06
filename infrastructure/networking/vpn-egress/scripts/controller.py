"""VPN egress controller: owns the CiliumEgressGatewayPolicy and serves the on/off UI.

ON and at least one healthy gateway: apply the policy with only the healthy gateways.
ON and no healthy gateway: delete the policy, so pods fall back to the home IP.
OFF: delete the policy.

Desired state lives in the ConfigMap vpn-egress-state, which this controller creates
on first start. Gateways report health in the ConfigMaps vpn-gateway-<ordinal>.
Neither the policy nor those ConfigMaps are in Git, so Argo CD never fights them.

Standard library only: it runs on the stock python image with this file in a ConfigMap.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = logging.getLogger("vpn-egress")

POLICY_API = "/apis/cilium.io/v2/ciliumegressgatewaypolicies"
STATUS_SELECTOR = "app.kubernetes.io/component=gateway-status"
TOGGLE_HEADER = "X-VPN-Toggle"
# Namespaces that must keep working when every tunnel is down, whatever the config says.
ALWAYS_EXEMPT = ("kube-system", "vpn-egress")


def _words(value: str) -> list[str]:
    return [w for w in value.replace(",", " ").split() if w]


class Config:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        env = dict(os.environ if env is None else env)
        self.namespace = env.get("POD_NAMESPACE", "vpn-egress")
        self.policy_name = env.get("POLICY_NAME", "vpn-egress")
        self.state_cm = env.get("STATE_CONFIGMAP", "vpn-egress-state")
        self.default_enabled = env.get("DEFAULT_ENABLED", "true").lower() == "true"
        self.include_namespaces = _words(env.get("INCLUDE_NAMESPACES", ""))
        exempt = _words(env.get("EXEMPT_NAMESPACES", ""))
        self.exempt_namespaces = sorted(set(exempt) | set(ALWAYS_EXEMPT))
        self.excluded_cidrs = _words(
            env.get("EXCLUDED_CIDRS", "10.0.0.0/8 100.64.0.0/10 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16")
        )
        self.interface = env.get("INTERFACE", "wg-proton")
        self.interval = float(env.get("INTERVAL", "10"))
        self.stale_seconds = float(env.get("STALE_SECONDS", "60"))
        # A recovered gateway must pass this many checks in a row before it rejoins.
        self.rise = int(env.get("RISE", "2"))
        self.port = int(env.get("PORT", "8080"))
        self.ui_file = env.get("UI_FILE", str(Path(__file__).with_name("index.html")))


class KubeError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status


class Kube:
    """Tiny in-cluster API client. Tests replace it with a fake that has the same request()."""

    def __init__(self) -> None:
        sa = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.base = f"https://{os.environ['KUBERNETES_SERVICE_HOST']}:{os.environ['KUBERNETES_SERVICE_PORT']}"
        self.token_file = sa / "token"
        self.ctx = ssl.create_default_context(cafile=str(sa / "ca.crt"))

    def request(self, method: str, path: str, body: dict | None = None, content_type: str = "application/json"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token_file.read_text().strip())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=10) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            raise KubeError(err.code, err.read().decode(errors="replace")[:300]) from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise KubeError(0, str(err)) from None
        return json.loads(raw) if raw else {}


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def node_schedulable_ready(node: dict | None) -> tuple[bool, str]:
    if not node:
        return False, "node not found"
    if node.get("spec", {}).get("unschedulable"):
        return False, "node cordoned"
    for cond in node.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready":
            return (cond.get("status") == "True"), ("node ready" if cond.get("status") == "True" else "node not ready")
    return False, "node has no Ready condition"


def gateway_view(name: str, data: dict | None, node: dict | None, now: float, stale_seconds: float, pod: dict | None = None) -> dict:
    """Turn one gateway's status ConfigMap and its Node into what the UI and metrics show."""
    data = data or {}
    updated = _num(data.get("updated"))
    handshake = _num(data.get("latestHandshake"))
    view = {
        "name": name,
        "node": (pod or {}).get("spec", {}).get("nodeName", ""),
        "podUID": (pod or {}).get("metadata", {}).get("uid", ""),
        "up": False,
        "reason": "",
        "exitIP": data.get("exitIP", ""),
        "endpoint": data.get("endpoint", ""),
        "message": data.get("message", ""),
        "handshakeAge": (now - handshake) if handshake > 0 else None,
        "rxBytes": int(_num(data.get("rxBytes"))),
        "txBytes": int(_num(data.get("txBytes"))),
        "ifindex": data.get("ifindex", "0"),
        "updated": updated,
        "statusAge": (now - updated) if updated > 0 else None,
        "rxRate": None,
        "txRate": None,
        "inPolicy": False,
    }
    node_ok, node_reason = node_schedulable_ready(node)
    pod_ready = pod and not pod.get("metadata", {}).get("deletionTimestamp") and any(
        c.get("type") == "Ready" and c.get("status") == "True"
        for c in pod.get("status", {}).get("conditions", [])
    )
    if not pod_ready:
        view["reason"] = "pod not ready or terminating"
    elif not data:
        view["reason"] = "no status reported yet"
    elif data.get("nodeName") != view["node"] or data.get("podUID") != view["podUID"]:
        view["reason"] = "waiting for this pod's status"
    elif now - updated > stale_seconds:
        view["reason"] = f"status is stale ({int(now - updated)} s old)"
    elif data.get("healthy") != "true":
        view["reason"] = data.get("message") or "probe failing"
    elif not node_ok:
        view["reason"] = node_reason
    else:
        view["up"] = True
        view["reason"] = "probe ok"
    return view


def build_policy(cfg: Config, gateways: list[dict], owner_uid: str | None) -> dict:
    """The policy for the given gateways (in config order). The caller makes sure the list is not empty."""
    if cfg.include_namespaces:
        selector = {
            "matchExpressions": [
                {"key": "io.kubernetes.pod.namespace", "operator": "In", "values": sorted(cfg.include_namespaces)}
            ]
        }
    else:
        selector = {
            "matchExpressions": [
                {"key": "io.kubernetes.pod.namespace", "operator": "NotIn", "values": cfg.exempt_namespaces}
            ]
        }
    entries = [
        {"nodeSelector": {"matchLabels": {"kubernetes.io/hostname": g["node"]}}, "interface": cfg.interface}
        for g in gateways
    ]
    metadata: dict = {
        "name": cfg.policy_name,
        "labels": {"app.kubernetes.io/name": "vpn-egress", "app.kubernetes.io/managed-by": "vpn-egress-controller"},
        # Cilium reads the link's ifindex only when the policy or a node changes. A gateway
        # that recreated its link gets a new ifindex here, which makes Cilium re-read it.
        "annotations": {"vpn-egress.vanillax.dev/links": ",".join(f"{g['node']}={g['ifindex']}" for g in gateways)},
    }
    if owner_uid:
        # Deleting the vpn-egress namespace garbage-collects the policy: pods go back to the home IP.
        metadata["ownerReferences"] = [
            {"apiVersion": "v1", "kind": "Namespace", "name": cfg.namespace, "uid": owner_uid}
        ]
    return {
        "apiVersion": "cilium.io/v2",
        "kind": "CiliumEgressGatewayPolicy",
        "metadata": metadata,
        "spec": {
            "selectors": [{"podSelector": selector}],
            "destinationCIDRs": ["0.0.0.0/0"],
            "excludedCIDRs": cfg.excluded_cidrs,
            # Required by the CRD; Cilium ignores it because egressGateways is set.
            "egressGateway": entries[0],
            "egressGateways": entries,
        },
    }


def namespace_coverage(cfg: Config, existing: list[str]) -> dict:
    existing = sorted(existing)
    if cfg.include_namespaces:
        covered = [n for n in existing if n in cfg.include_namespaces and n not in ALWAYS_EXEMPT]
        mode = "listed namespaces only (phase 1)"
    else:
        covered = [n for n in existing if n not in cfg.exempt_namespaces]
        mode = "all namespaces except exempt (phase 2)"
    return {
        "mode": mode,
        "covered": covered,
        "exempt": [n for n in existing if n not in covered],
        "configuredExempt": cfg.exempt_namespaces,
    }


class Controller:
    def __init__(self, cfg: Config, kube, clock=time.time) -> None:
        self.cfg = cfg
        self.kube = kube
        self.clock = clock
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.streak: dict[str, int] = {}
        self.identities: dict[str, tuple] = {}
        self.active_links: dict[str, str] = {}
        self.in_policy: list[str] = []
        self.prev_bytes: dict[str, tuple[float, int, int]] = {}
        self.rates: dict[str, tuple[float, float]] = {}
        self.seeded = False
        self.owner_uid: str | None = None
        self.reconcile_errors = 0
        self.policy_applies = 0
        self.policy_deletes = 0
        self.last_loop = 0.0
        self.snapshot: dict = {"ready": False}

    # --- desired state -------------------------------------------------------------
    def read_enabled(self) -> tuple[bool, dict]:
        path = f"/api/v1/namespaces/{self.cfg.namespace}/configmaps/{self.cfg.state_cm}"
        try:
            cm = self.kube.request("GET", path)
        except KubeError as err:
            if err.status != 404:
                raise
            cm = self._write_state(self.cfg.default_enabled, "controller default")
        data = cm.get("data", {}) or {}
        return data.get("enabled", "true") == "true", data

    def _write_state(self, enabled: bool, source: str) -> dict:
        body = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": self.cfg.state_cm,
                "namespace": self.cfg.namespace,
                "labels": {"app.kubernetes.io/name": "vpn-egress", "app.kubernetes.io/component": "desired-state"},
            },
            "data": {
                "enabled": "true" if enabled else "false",
                "changedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())),
                "changedBy": source[:60],
            },
        }
        path = (
            f"/api/v1/namespaces/{self.cfg.namespace}/configmaps/{self.cfg.state_cm}"
            "?fieldManager=vpn-egress-controller&force=true"
        )
        return self.kube.request("PATCH", path, body, "application/apply-patch+yaml")

    def set_enabled(self, enabled: bool, source: str) -> None:
        self._write_state(enabled, source)
        LOG.info("VPN turned %s by %s", "on" if enabled else "off", source)
        self.wake.set()

    # --- reconcile -----------------------------------------------------------------
    def reconcile(self) -> dict:
        cfg = self.cfg
        now = self.clock()
        errors: list[str] = []
        enabled, state = self.read_enabled()
        if not self.seeded:
            self._seed_from_live_policy()

        cms = self.kube.request(
            "GET", f"/api/v1/namespaces/{cfg.namespace}/configmaps?labelSelector={STATUS_SELECTOR}"
        ).get("items", [])
        status_by_name = {cm["metadata"]["name"]: cm.get("data", {}) for cm in cms}
        pods = self.kube.request(
            "GET", f"/api/v1/namespaces/{cfg.namespace}/pods?labelSelector=app=vpn-gateway"
        ).get("items", [])
        pods = {p["metadata"]["name"]: p for p in pods if any(
            o.get("kind") == "StatefulSet" and o.get("name") == "vpn-gateway" and o.get("controller")
            for o in p["metadata"].get("ownerReferences", [])
        )}
        nodes = {n["metadata"]["name"]: n for n in self.kube.request("GET", "/api/v1/nodes").get("items", [])}

        gateways = []
        for name in sorted(pods.keys() | status_by_name.keys()):
            pod = pods.get(name)
            node_name = (pod or {}).get("spec", {}).get("nodeName", "")
            view = gateway_view(name, status_by_name.get(name), nodes.get(node_name), now, cfg.stale_seconds, pod)
            identity = (node_name, view["podUID"], view["ifindex"])
            if self.identities.get(name) != identity:
                previous = self.identities.get(name)
                if previous is not None:
                    self.active_links.pop(previous[0], None)
                self.streak[name] = 0
                self.prev_bytes.pop(name, None)
                self.rates.pop(name, None)
            self.identities[name] = identity
            self._add_rates(view)
            self.streak[name] = self.streak.get(name, 0) + 1 if view["up"] else 0
            gateways.append(view)

        # Never advertise two tunnels on one host, even if scheduling/status is inconsistent.
        chosen = []
        seen_nodes = set()
        for g in gateways:
            retained = self.active_links.get(g["node"]) == g["ifindex"]
            if g["up"] and (retained or self.streak[g["name"]] >= cfg.rise) and g["node"] not in seen_nodes:
                chosen.append(g)
                seen_nodes.add(g["node"])

        if self.owner_uid is None:
            try:
                self.owner_uid = self.kube.request("GET", f"/api/v1/namespaces/{cfg.namespace}")["metadata"]["uid"]
            except (KubeError, KeyError) as err:
                errors.append(f"namespace lookup failed: {err}")

        policy_path = f"{POLICY_API}/{cfg.policy_name}"
        try:
            if enabled and chosen:
                body = build_policy(cfg, chosen, self.owner_uid)
                self.kube.request(
                    "PATCH",
                    f"{policy_path}?fieldManager=vpn-egress-controller&force=true",
                    body,
                    "application/apply-patch+yaml",
                )
                if [g["name"] for g in chosen] != self.in_policy:
                    LOG.info("policy gateways: %s", ", ".join(g["name"] for g in chosen))
                    self.policy_applies += 1
                self.in_policy = [g["name"] for g in chosen]
                self.active_links = {g["node"]: g["ifindex"] for g in chosen}
            else:
                try:
                    self.kube.request("DELETE", policy_path)
                    self.policy_deletes += 1
                    LOG.info("policy deleted (%s)", "VPN off" if not enabled else "no healthy gateway, home IP fallback")
                except KubeError as err:
                    if err.status != 404:
                        raise
                self.in_policy = []
                self.active_links = {}
        except KubeError as err:
            # Typical cause: the Cilium agents were not restarted, so the policy CRD is missing.
            errors.append(f"policy update failed: {err}")
            self.reconcile_errors += 1

        for g in gateways:
            g["inPolicy"] = g["name"] in self.in_policy

        try:
            ns_names = [n["metadata"]["name"] for n in self.kube.request("GET", "/api/v1/namespaces").get("items", [])]
        except KubeError as err:
            errors.append(f"namespace list failed: {err}")
            ns_names = []

        if not enabled:
            mode = "off"
        elif self.in_policy:
            mode = "on"
        else:
            mode = "fallback"
        snapshot = {
            "ready": True,
            "enabled": enabled,
            "mode": mode,
            "policyActive": bool(self.in_policy),
            "policyName": cfg.policy_name,
            "state": state,
            "gateways": gateways,
            "namespaces": namespace_coverage(cfg, ns_names),
            "excludedCIDRs": cfg.excluded_cidrs,
            "lastReconcile": now,
            "errors": errors,
        }
        with self.lock:
            self.snapshot = snapshot
            self.last_loop = now
        return snapshot

    def _add_rates(self, view: dict) -> None:
        """Bytes per second between the gateway's last two reports."""
        name, updated, rx, tx = view["name"], view["updated"], view["rxBytes"], view["txBytes"]
        prev = self.prev_bytes.get(name)
        if prev is None or updated > prev[0]:
            if prev is not None:
                # A recreated link restarts its counters at zero; skip that sample.
                if rx >= prev[1] and tx >= prev[2]:
                    dt = updated - prev[0]
                    self.rates[name] = ((rx - prev[1]) / dt, (tx - prev[2]) / dt)
                else:
                    self.rates.pop(name, None)
            self.prev_bytes[name] = (updated, rx, tx)
        fresh = view["statusAge"] is not None and view["statusAge"] <= self.cfg.stale_seconds
        view["rxRate"], view["txRate"] = self.rates.get(name, (None, None)) if fresh else (None, None)

    def _seed_from_live_policy(self) -> None:
        """After a restart, keep the gateways already in the policy so the restart doesn't flap traffic."""
        try:
            live = self.kube.request("GET", f"{POLICY_API}/{self.cfg.policy_name}")
        except KubeError as err:
            if err.status != 404:
                raise
            live = {}
        entries = live.get("spec", {}).get("egressGateways", []) if live else []
        live_nodes = {
            e.get("nodeSelector", {}).get("matchLabels", {}).get("kubernetes.io/hostname", "") for e in entries
        }
        links = live.get("metadata", {}).get("annotations", {}).get("vpn-egress.vanillax.dev/links", "")
        self.active_links = dict(part.split("=", 1) for part in links.split(",") if "=" in part and part.split("=", 1)[0] in live_nodes)
        self.seeded = True

    def run_forever(self) -> None:
        while True:
            try:
                self.reconcile()
            except Exception as err:  # noqa: BLE001 - keep the loop alive; the UI shows the error
                self.reconcile_errors += 1
                LOG.warning("reconcile failed: %s", err)
                with self.lock:
                    self.snapshot = {**self.snapshot, "errors": [f"reconcile failed: {err}"]}
                    self.last_loop = self.clock()
            self.wake.wait(self.cfg.interval)
            self.wake.clear()

    # --- metrics -------------------------------------------------------------------
    def metrics(self) -> str:
        with self.lock:
            snap = dict(self.snapshot)
        lines = [
            "# HELP vpn_egress_enabled 1 when the VPN toggle is on.",
            "# TYPE vpn_egress_enabled gauge",
            f"vpn_egress_enabled {int(bool(snap.get('enabled')))}",
            "# HELP vpn_egress_policy_active 1 when the egress policy exists and pods use the VPN.",
            "# TYPE vpn_egress_policy_active gauge",
            f"vpn_egress_policy_active {int(bool(snap.get('policyActive')))}",
            "# HELP vpn_egress_fallback 1 when the VPN is on but no gateway is healthy, so pods use the home IP.",
            "# TYPE vpn_egress_fallback gauge",
            f"vpn_egress_fallback {int(snap.get('mode') == 'fallback')}",
            "# HELP vpn_egress_reconcile_errors_total Failed reconcile loops.",
            "# TYPE vpn_egress_reconcile_errors_total counter",
            f"vpn_egress_reconcile_errors_total {self.reconcile_errors}",
        ]
        per_gw = [
            ("vpn_egress_gateway_up", "gauge", "1 when the gateway's probe through its tunnel works.", lambda g: int(g["up"])),
            ("vpn_egress_gateway_in_policy", "gauge", "1 when the policy sends pods to this gateway.", lambda g: int(g["inPolicy"])),
            ("vpn_egress_gateway_handshake_age_seconds", "gauge", "Seconds since the last WireGuard handshake.",
             lambda g: g["handshakeAge"]),
            ("vpn_egress_gateway_status_age_seconds", "gauge", "Seconds since the gateway last reported.",
             lambda g: g["statusAge"]),
            ("vpn_egress_gateway_receive_bytes_total", "counter", "Bytes received from Proton on the tunnel.",
             lambda g: g["rxBytes"]),
            ("vpn_egress_gateway_transmit_bytes_total", "counter", "Bytes sent to Proton on the tunnel.",
             lambda g: g["txBytes"]),
        ]
        gateways = snap.get("gateways", [])
        for metric, kind, help_text, fn in per_gw:
            lines += [f"# HELP {metric} {help_text}", f"# TYPE {metric} {kind}"]
            for g in gateways:
                value = fn(g)
                if value is not None:
                    lines.append(f'{metric}{{gateway="{g["name"]}",node="{_label(g["node"])}"}} {value}')
        lines += ["# HELP vpn_egress_gateway_info Exit IP and Proton endpoint per gateway.", "# TYPE vpn_egress_gateway_info gauge"]
        for g in gateways:
            lines.append(
                f'vpn_egress_gateway_info{{gateway="{g["name"]}",node="{_label(g["node"])}",exit_ip="{_label(g["exitIP"])}",endpoint="{_label(g["endpoint"])}"}} 1'
            )
        ns = snap.get("namespaces", {})
        lines += [
            "# HELP vpn_egress_namespaces Namespaces by VPN coverage.",
            "# TYPE vpn_egress_namespaces gauge",
            f'vpn_egress_namespaces{{coverage="covered"}} {len(ns.get("covered", []))}',
            f'vpn_egress_namespaces{{coverage="exempt"}} {len(ns.get("exempt", []))}',
        ]
        return "\n".join(lines) + "\n"

    def healthy(self) -> bool:
        with self.lock:
            return self.clock() - self.last_loop < max(60.0, self.cfg.interval * 6)


def _label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def make_handler(ctrl: Controller):
    class Handler(BaseHTTPRequestHandler):
        server_version = "vpn-egress"

        def log_message(self, fmt, *args):  # quiet access log; probes and scrapes are noisy
            pass

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/":
                try:
                    body = Path(ctrl.cfg.ui_file).read_bytes()
                except OSError:
                    body = b"<h1>UI file missing</h1>"
                self._send(200, body, "text/html; charset=utf-8")
            elif path == "/api/status":
                with ctrl.lock:
                    self._json(200, ctrl.snapshot)
            elif path == "/api/enabled":
                with ctrl.lock:
                    self._json(200, {"enabled": bool(ctrl.snapshot.get("enabled")), "mode": ctrl.snapshot.get("mode")})
            elif path == "/metrics":
                self._send(200, ctrl.metrics().encode(), "text/plain; version=0.0.4")
            elif path == "/healthz":
                ok = ctrl.healthy()
                self._send(200 if ok else 503, b"ok\n" if ok else b"reconcile loop stalled\n", "text/plain")
            else:
                self._send(404, b"not found\n", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path.split("?", 1)[0] != "/api/enabled":
                self._send(404, b"not found\n", "text/plain")
                return
            # Browsers can't send a custom header cross-site without a CORS preflight, which we
            # never answer. That blocks drive-by toggles from other web pages on the LAN.
            if self.headers.get(TOGGLE_HEADER) != "1":
                self._json(403, {"error": f"missing {TOGGLE_HEADER}: 1 header"})
                return
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 4096)
                payload = json.loads(self.rfile.read(length) or b"{}")
                enabled = payload["enabled"]
                if isinstance(enabled, str):
                    enabled = enabled.lower() in ("true", "on", "1")
                enabled = bool(enabled)
            except (ValueError, KeyError, TypeError):
                self._json(400, {"error": 'body must be {"enabled": true|false}'})
                return
            source = self.headers.get("X-VPN-Client") or "web UI"
            try:
                ctrl.set_enabled(enabled, source)
            except KubeError as err:
                self._json(502, {"error": f"could not save state: {err}"})
                return
            self._json(200, {"enabled": enabled})

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config()
    ctrl = Controller(cfg, Kube())
    threading.Thread(target=ctrl.run_forever, daemon=True).start()
    server = ThreadingHTTPServer(("", cfg.port), make_handler(ctrl))
    LOG.info("listening on :%d, discovering floating VPN gateways", cfg.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
