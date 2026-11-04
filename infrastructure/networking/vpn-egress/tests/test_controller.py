"""Tests for the vpn-egress controller against a fake Kubernetes API."""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("controller", HERE.parent / "scripts" / "controller.py")
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)

NODES = ["hp-elite-gen13", "mini-pc-dell-ultra-worker", "hp-elite-gen12"]
POLICY = "/apis/cilium.io/v2/ciliumegressgatewaypolicies/vpn-egress"


class FakeKube:
    """Just enough of the API server: ConfigMaps, nodes, namespaces and one egress policy."""

    def __init__(self) -> None:
        self.configmaps: dict[str, dict] = {}
        self.nodes = {n: {"metadata": {"name": n}, "spec": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}} for n in NODES}
        self.namespaces = ["default", "kube-system", "vpn-egress", "vpn-egress-test", "argocd", "jellyfin", "vllm"]
        self.policy: dict | None = None
        self.policy_crd = True
        self.calls: list[tuple[str, str]] = []

    def request(self, method, path, body=None, content_type="application/json"):
        self.calls.append((method, path))
        base = path.split("?", 1)[0]
        if base.startswith("/api/v1/namespaces/vpn-egress/configmaps"):
            name = base.rsplit("/", 1)[-1]
            if name == "configmaps":
                items = [cm for cm in self.configmaps.values() if cm["metadata"].get("labels", {}).get("app.kubernetes.io/component") == "gateway-status"]
                return {"items": items}
            if method == "GET":
                if name not in self.configmaps:
                    raise controller.KubeError(404, "not found")
                return self.configmaps[name]
            if method == "PATCH":
                assert content_type == "application/apply-patch+yaml"
                self.configmaps[name] = body
                return body
        if base == "/api/v1/nodes":
            return {"items": list(self.nodes.values())}
        if base == "/api/v1/namespaces":
            return {"items": [{"metadata": {"name": n}} for n in self.namespaces]}
        if base == "/api/v1/namespaces/vpn-egress":
            return {"metadata": {"name": "vpn-egress", "uid": "ns-uid-1"}}
        if base == POLICY:
            if not self.policy_crd:
                raise controller.KubeError(404, "the server could not find the requested resource")
            if method == "GET":
                if self.policy is None:
                    raise controller.KubeError(404, "not found")
                return self.policy
            if method == "PATCH":
                self.policy = body
                return body
            if method == "DELETE":
                if self.policy is None:
                    raise controller.KubeError(404, "not found")
                self.policy = None
                return {}
        raise AssertionError(f"unexpected call {method} {path}")

    def report(self, node, now, healthy=True, ifindex="12", rx=1000, tx=500, handshake_age=30):
        self.configmaps[f"vpn-gateway-{node}"] = {
            "metadata": {"name": f"vpn-gateway-{node}", "labels": {"app.kubernetes.io/component": "gateway-status"}},
            "data": {
                "node": node, "healthy": "true" if healthy else "false", "exitIP": f"185.0.0.{NODES.index(node) + 1}",
                "message": "probe ok" if healthy else "probe failed (3 in a row)", "latestHandshake": str(int(now - handshake_age)),
                "rxBytes": str(rx), "txBytes": str(tx), "endpoint": "149.88.0.1:51820", "ifindex": ifindex, "updated": str(int(now)),
            },
        }


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(env=None):
    base = {
        "POD_NAMESPACE": "vpn-egress",
        "GATEWAY_NODES": " ".join(NODES),
        "INCLUDE_NAMESPACES": "vpn-egress-test",
        "EXEMPT_NAMESPACES": "kube-system argocd vpn-egress vllm",
        "RISE": "2",
        "STALE_SECONDS": "60",
    }
    base.update(env or {})
    kube, clock = FakeKube(), Clock()
    return controller.Controller(controller.Config(base), kube, clock), kube, clock


def policy_gateways(kube):
    return [e["nodeSelector"]["matchLabels"]["kubernetes.io/hostname"] for e in kube.policy["spec"]["egressGateways"]]


def all_report(kube, clock, **kw):
    for n in NODES:
        kube.report(n, clock.t, **kw)


def test_first_start_creates_state_on_and_waits_for_rise():
    ctrl, kube, clock = make()
    all_report(kube, clock)
    snap = ctrl.reconcile()
    assert kube.configmaps["vpn-egress-state"]["data"]["enabled"] == "true"
    # One good check is not enough to join.
    assert kube.policy is None and snap["mode"] == "fallback"
    clock.t += 10
    all_report(kube, clock)
    snap = ctrl.reconcile()
    assert snap["mode"] == "on"
    assert policy_gateways(kube) == NODES
    assert kube.policy["metadata"]["ownerReferences"][0]["uid"] == "ns-uid-1"
    assert kube.policy["metadata"]["annotations"]["vpn-egress.vanillax.dev/links"].count("=12") == 3


def test_policy_scope_phase1_and_phase2():
    ctrl, kube, clock = make()
    body = controller.build_policy(ctrl.cfg, [{"name": NODES[0], "ifindex": "3"}], None)
    expr = body["spec"]["selectors"][0]["podSelector"]["matchExpressions"][0]
    assert expr == {"key": "io.kubernetes.pod.namespace", "operator": "In", "values": ["vpn-egress-test"]}
    assert body["spec"]["egressGateway"] == body["spec"]["egressGateways"][0]
    assert "10.0.0.0/8" in body["spec"]["excludedCIDRs"]

    ctrl2, _, _ = make({"INCLUDE_NAMESPACES": "", "EXEMPT_NAMESPACES": "argocd"})
    body = controller.build_policy(ctrl2.cfg, [{"name": NODES[0], "ifindex": "3"}], None)
    expr = body["spec"]["selectors"][0]["podSelector"]["matchExpressions"][0]
    assert expr["operator"] == "NotIn"
    # kube-system and vpn-egress stay exempt even when the config forgets them.
    assert {"argocd", "kube-system", "vpn-egress"} <= set(expr["values"])


def running(rounds=2):
    ctrl, kube, clock = make()
    for _ in range(rounds):
        all_report(kube, clock)
        ctrl.reconcile()
        clock.t += 10
    assert kube.policy is not None
    return ctrl, kube, clock


def test_unhealthy_gateway_leaves_and_rejoins_after_rise():
    ctrl, kube, clock = running()
    for n in NODES:
        kube.report(n, clock.t, healthy=(n != NODES[1]))
    ctrl.reconcile()
    assert policy_gateways(kube) == [NODES[0], NODES[2]]
    clock.t += 10
    all_report(kube, clock)
    ctrl.reconcile()
    assert policy_gateways(kube) == [NODES[0], NODES[2]], "one good check must not re-add it"
    clock.t += 10
    all_report(kube, clock)
    ctrl.reconcile()
    assert policy_gateways(kube) == NODES


def test_all_down_deletes_policy_fallback_to_home():
    ctrl, kube, clock = running()
    all_report(kube, clock, healthy=False)
    snap = ctrl.reconcile()
    assert kube.policy is None
    assert snap["mode"] == "fallback" and snap["enabled"] is True and not snap["policyActive"]
    assert "vpn_egress_fallback 1" in ctrl.metrics()


def test_stale_status_and_cordoned_or_notready_node_drop_gateway():
    ctrl, kube, clock = running()
    kube.report(NODES[0], clock.t - 120)  # stopped reporting 2 min ago
    kube.report(NODES[1], clock.t)
    kube.report(NODES[2], clock.t)
    kube.nodes[NODES[1]]["spec"]["unschedulable"] = True
    snap = ctrl.reconcile()
    assert policy_gateways(kube) == [NODES[2]]
    reasons = {g["name"]: g["reason"] for g in snap["gateways"]}
    assert "stale" in reasons[NODES[0]] and reasons[NODES[1]] == "node cordoned"
    kube.nodes[NODES[2]]["status"]["conditions"][0]["status"] = "False"
    kube.nodes[NODES[1]]["spec"]["unschedulable"] = False
    clock.t += 10
    all_report(kube, clock)
    kube.report(NODES[0], clock.t - 120)
    snap = ctrl.reconcile()
    # gen13 stale, gen12 NotReady, the Dell has one good check after its cordon: nobody qualifies.
    assert kube.policy is None and snap["mode"] == "fallback"


def test_toggle_off_deletes_policy_and_on_restores():
    ctrl, kube, clock = running()
    ctrl.set_enabled(False, "web UI")
    assert kube.configmaps["vpn-egress-state"]["data"]["changedBy"] == "web UI"
    all_report(kube, clock)
    snap = ctrl.reconcile()
    assert kube.policy is None and snap["mode"] == "off"
    assert "vpn_egress_enabled 0" in ctrl.metrics()
    # Tunnels keep reporting while off.
    assert all(g["up"] for g in snap["gateways"])
    ctrl.set_enabled(True, "home-assistant")
    clock.t += 10
    all_report(kube, clock)
    snap = ctrl.reconcile()
    assert snap["mode"] == "on" and policy_gateways(kube) == NODES


def test_restart_keeps_live_policy_without_flapping():
    _, kube, clock = running()
    kube.calls.clear()
    ctrl2 = controller.Controller(make()[0].cfg, kube, clock)
    all_report(kube, clock)
    snap = ctrl2.reconcile()
    assert snap["mode"] == "on" and policy_gateways(kube) == NODES
    assert ("DELETE", POLICY) not in kube.calls


def test_new_link_ifindex_changes_policy_annotation():
    ctrl, kube, clock = running()
    for n in NODES:
        kube.report(n, clock.t, ifindex="99" if n == NODES[0] else "12")
    ctrl.reconcile()
    assert f"{NODES[0]}=99" in kube.policy["metadata"]["annotations"]["vpn-egress.vanillax.dev/links"]


def test_missing_crd_reports_error_and_keeps_running():
    ctrl, kube, clock = make()
    kube.policy_crd = False
    for _ in range(2):
        all_report(kube, clock)
        snap = ctrl.reconcile()
        clock.t += 10
    assert any("policy update failed" in e for e in snap["errors"])
    assert len(snap["gateways"]) == 3


def test_rates_from_successive_reports():
    ctrl, kube, clock = make()
    all_report(kube, clock, rx=0, tx=0)
    ctrl.reconcile()
    clock.t += 10
    all_report(kube, clock, rx=125_000_000, tx=12_500_000)
    snap = ctrl.reconcile()
    g = snap["gateways"][0]
    assert g["rxRate"] == pytest.approx(12_500_000) and g["txRate"] == pytest.approx(1_250_000)
    assert g["handshakeAge"] == pytest.approx(30)


def test_namespace_coverage():
    ctrl, kube, clock = make()
    cov = controller.namespace_coverage(ctrl.cfg, kube.namespaces)
    assert cov["covered"] == ["vpn-egress-test"]
    assert "jellyfin" in cov["exempt"]
    ctrl2, _, _ = make({"INCLUDE_NAMESPACES": ""})
    cov = controller.namespace_coverage(ctrl2.cfg, kube.namespaces)
    assert cov["covered"] == ["default", "jellyfin", "vpn-egress-test"]
    assert cov["exempt"] == ["argocd", "kube-system", "vllm", "vpn-egress"]


def test_metrics_names():
    ctrl, kube, clock = running()
    text = ctrl.metrics()
    for name in [
        "vpn_egress_enabled 1",
        "vpn_egress_policy_active 1",
        'vpn_egress_gateway_up{gateway="hp-elite-gen13"} 1',
        'vpn_egress_gateway_in_policy{gateway="hp-elite-gen12"} 1',
        'vpn_egress_gateway_receive_bytes_total{gateway="hp-elite-gen13"} 1000',
        'vpn_egress_gateway_handshake_age_seconds{gateway="hp-elite-gen13"}',
        'vpn_egress_gateway_info{gateway="hp-elite-gen13",exit_ip="185.0.0.1",endpoint="149.88.0.1:51820"} 1',
        'vpn_egress_namespaces{coverage="covered"} 1',
    ]:
        assert name in text, name


@pytest.fixture
def server():
    ctrl, kube, clock = running()
    clock.t = __import__("time").time()
    ctrl.last_loop = clock.t
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), controller.make_handler(ctrl))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", ctrl, kube
    httpd.shutdown()


def post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_toggle_requires_header(server):
    url, ctrl, kube = server
    code, _ = post(url + "/api/enabled", {"enabled": False}, {"Content-Type": "application/json"})
    assert code == 403
    assert kube.configmaps["vpn-egress-state"]["data"]["enabled"] == "true"
    code, body = post(url + "/api/enabled", {"enabled": False}, {"X-VPN-Toggle": "1", "X-VPN-Client": "home-assistant"})
    assert code == 200 and body == {"enabled": False}
    assert kube.configmaps["vpn-egress-state"]["data"]["changedBy"] == "home-assistant"
    code, _ = post(url + "/api/enabled", {"nope": 1}, {"X-VPN-Toggle": "1"})
    assert code == 400


def test_http_pages(server):
    url, ctrl, kube = server
    with urllib.request.urlopen(url + "/api/enabled") as r:
        assert json.loads(r.read()) == {"enabled": True, "mode": "on"}
    with urllib.request.urlopen(url + "/healthz") as r:
        assert r.status == 200
    with urllib.request.urlopen(url + "/metrics") as r:
        assert b"vpn_egress_enabled 1" in r.read()
    with urllib.request.urlopen(url + "/") as r:
        assert b"VPN egress" in r.read()
