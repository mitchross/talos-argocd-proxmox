"""Run gateway.sh against mocked ip, wg and curl (probe + Kubernetes API)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gateway.sh"
NODE = "worker-a"

CONF = """[Interface]
# Test key
PrivateKey = cHJpdmF0ZWtleXByaXZhdGVrZXlwcml2YXRla2V5cHI=
Address = 10.2.0.2/32, 2a07:b944::2:2/128
DNS = 10.2.0.1

[Peer]
PublicKey = cHVibGlja2V5cHVibGlja2V5cHVibGlja2V5cHVibGk=
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 149.88.0.1:51820
"""

MOCK_IP = r"""#!/usr/bin/env bash
S="$MOCK_STATE"; echo "ip $*" >> "$S/calls"
case "$*" in
  "rule del "*) exit 1 ;;
  "link del wg-proton") rm -f "$S/link" ;;
  "rule show") cat "$S/rules" 2>/dev/null ;;
  "rule add priority "*) echo "${3}:	from ${6%/32} lookup ${8}" >> "$S/rules" ;;
  "link show wg-proton") [[ -e $S/link ]]; exit ;;
  "-o link show wg-proton") [[ -e $S/link ]] || exit 1
    if [[ -e $S/down ]]; then echo "7: wg-proton: <POINTOPOINT,NOARP> mtu 1420"; else echo "7: wg-proton: <POINTOPOINT,NOARP,UP> mtu 1420"; fi ;;
  "link set wg-proton mtu 1420 up") rm -f "$S/down" ;;
  "link add wg-proton type wireguard") touch "$S/link" ;;
esac
exit 0
"""

MOCK_WG = r"""#!/usr/bin/env bash
S="$MOCK_STATE"; echo "wg $*" >> "$S/calls"
case "$1 $3" in
  "setconf "*) cat "$3" > "$S/setconf" ;;
  "show peers") echo PEERKEY ;;
  "show latest-handshakes") printf 'PEERKEY\t1800000000\n' ;;
  "show transfer") printf 'PEERKEY\t123456\t7890\n' ;;
  "show endpoints") printf 'PEERKEY\t149.88.0.1:51820\n' ;;
esac
exit 0
"""

MOCK_CURL = r"""#!/usr/bin/env bash
S="$MOCK_STATE"
args=("$@")
for i in "${!args[@]}"; do
  if [[ ${args[$i]} == --interface ]]; then
    n=$(( $(cat "$S/probes" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$S/probes"
    # FLAP_LINK: the link goes down right after the first probe.
    if [[ -n ${FLAP_LINK:-} && $n == 1 ]]; then touch "$S/down"; fi
    if [[ -n ${PROBE_OK_ROUNDS:-} ]] && (( n > PROBE_OK_ROUNDS )); then exit 7; fi
    printf 'fl=1\nh=1.1.1.1\nip=185.159.157.10\nts=1\n'; exit 0
  fi
done
for i in "${!args[@]}"; do
  [[ ${args[$i]} == --data ]] && printf '%s\n' "${args[$((i+1))]}" >> "$S/writes"
  [[ ${args[$i]} == -X ]] && echo "${args[$((i+1))]} ${args[-1]}" >> "$S/api"
  [[ ${args[$i]} == -H && ${args[$((i+1))]} == Authorization:* ]] && echo "${args[$((i+1))]}" > "$S/auth"
done
echo '{}'
"""


@pytest.fixture
def env(tmp_path):
    bin_dir, state, conf, sa = (tmp_path / d for d in ("bin", "state", "conf", "sa"))
    for d in (bin_dir, state, conf, sa):
        d.mkdir()
    for name, body in (("ip", MOCK_IP), ("wg", MOCK_WG), ("curl", MOCK_CURL)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    (conf / "config-1").write_text(CONF)
    (sa / "token").write_text("test-token")
    (sa / "namespace").write_text("vpn-egress")
    (sa / "ca.crt").write_text("")
    e = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MOCK_STATE": str(state),
        "NODE_NAME": NODE,
        "POD_NAME": "vpn-gateway-0",
        "POD_UID": "pod-uid",
        "READY_FILE": str(state / "ready"),
        "CONF_DIR": str(conf),
        "SA_DIR": str(sa),
        "KUBE_API": "https://api.test:6443",
        "INTERVAL": "0",
    }
    return e, state


def run(e, **extra):
    return subprocess.run(["bash", str(SCRIPT)], env={**e, **extra}, capture_output=True, text=True, timeout=30)


def writes(state):
    return [cm for line in (state / "writes").read_text().splitlines()
            if (cm := json.loads(line))["data"]["message"] != "gateway stopping"]


def test_healthy_round_sets_up_tunnel_and_reports(env):
    e, state = env
    r = run(e, MAX_ROUNDS="1")
    assert r.returncode == 0, r.stderr
    calls = (state / "calls").read_text()
    assert "ip rule add priority 90 from 10.2.0.2/32 lookup 51820" in calls
    assert "ip route replace blackhole default metric 4096 table 51820" in calls
    assert "ip route replace default dev wg-proton table 51820" in calls
    assert "wg set wg-proton peer PEERKEY persistent-keepalive 25" in calls
    setconf = (state / "setconf").read_text()
    assert "PrivateKey" in setconf and "Address" not in setconf and "DNS" not in setconf
    [cm] = writes(state)
    assert cm["metadata"]["name"] == "vpn-gateway-0"
    assert cm["metadata"]["labels"]["app.kubernetes.io/component"] == "gateway-status"
    d = cm["data"]
    assert d["nodeName"] == NODE and d["podUID"] == "pod-uid"
    assert d["healthy"] == "true" and d["exitIP"] == "185.159.157.10"
    assert (d["rxBytes"], d["txBytes"], d["latestHandshake"]) == ("123456", "7890", "1800000000")
    assert (d["endpoint"], d["ifindex"]) == ("149.88.0.1:51820", "7")
    api = (state / "api").read_text()
    assert "PATCH https://api.test:6443/api/v1/namespaces/vpn-egress/configmaps/vpn-gateway-0?fieldManager=vpn-gateway&force=true" in api
    assert (state / "auth").read_text().strip() == "Authorization: Bearer test-token"
    # No node labels any more.
    assert "/nodes/" not in api


def test_rule_is_added_once_across_rounds(env):
    e, state = env
    assert run(e, MAX_ROUNDS="3").returncode == 0
    calls = (state / "calls").read_text()
    assert calls.count("ip rule add") == 1
    assert calls.count("ip link add") == 1
    assert calls.count("wg setconf") == 1


def test_link_down_is_rebuilt_with_routes(env):
    e, state = env
    r = run(e, MAX_ROUNDS="2", FLAP_LINK="1")
    assert r.returncode == 0, r.stderr
    assert "link missing or down; rebuilding" in r.stdout
    calls = (state / "calls").read_text()
    assert calls.count("ip route replace default dev wg-proton table 51820") == 2
    assert calls.count("ip link add") == 2


def test_reports_down_only_after_consecutive_failures(env):
    e, state = env
    r = run(e, MAX_ROUNDS="4", PROBE_OK_ROUNDS="1", FAILS_BEFORE_DOWN="2")
    assert r.returncode == 0, r.stderr
    healthy = [w["data"]["healthy"] for w in writes(state)]
    assert healthy == ["true", "true", "false", "false"]
    last = writes(state)[-1]["data"]
    # The last known exit IP stays visible while down.
    assert last["exitIP"] == "185.159.157.10" and "probe failed" in last["message"]


def test_never_healthy_reports_false(env):
    e, state = env
    assert run(e, MAX_ROUNDS="1", PROBE_OK_ROUNDS="0").returncode == 0
    assert writes(state)[0]["data"]["healthy"] == "false"


def test_missing_config_exits(env):
    e, _ = env
    r = run(e, POD_NAME="vpn-gateway-3", MAX_ROUNDS="1")
    assert r.returncode == 1 and "no Proton config" in r.stdout


def test_sigterm_exits_cleanly_and_removes_host_state(env):
    e, state = env
    p = subprocess.Popen(["bash", str(SCRIPT)], env={**e, "INTERVAL": "30"}, stdout=subprocess.PIPE, text=True)
    for _ in range(100):
        if (state / "writes").exists():
            break
        time.sleep(0.05)
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=10)
    assert p.returncode == 0
    calls = (state / "calls").read_text()
    assert "ip link del wg-proton" in calls
    assert "ip rule del priority 90 lookup 51820" in calls
    assert "ip route flush table 51820" in calls
    assert not (state / "link").exists() and not (state / "ready").exists()
    assert json.loads((state / "writes").read_text().splitlines()[-1])["data"]["healthy"] == "false"


@pytest.mark.parametrize("ordinal", [1, 2])
def test_config_selected_by_ordinal(env, ordinal):
    e, state = env
    (Path(e["CONF_DIR"]) / f"config-{ordinal + 1}").write_text(CONF.replace("149.88.0.1", f"149.88.0.{ordinal + 1}"))
    result = run(e, POD_NAME=f"vpn-gateway-{ordinal}", MAX_ROUNDS="1")
    assert result.returncode == 0, result.stderr
    assert f"149.88.0.{ordinal + 1}" in (state / "setconf").read_text()
    assert writes(state)[0]["metadata"]["name"] == f"vpn-gateway-{ordinal}"


def test_start_replaces_leftover_link_and_exit_cleans_it(env):
    e, state = env
    (state / "link").touch()
    result = run(e, MAX_ROUNDS="1")
    assert result.returncode == 0, result.stderr
    calls = (state / "calls").read_text()
    assert calls.index("ip link del wg-proton") < calls.index("ip link add wg-proton")
    assert calls.count("ip link del wg-proton") == 2
    assert not (state / "link").exists()
