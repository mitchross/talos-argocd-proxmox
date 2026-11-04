#!/usr/bin/env bash
# Proton WireGuard egress gateway for Cilium Egress Gateway.
#
# Runs in the host network namespace of one gateway node. It:
#   1. installs the kill switch: traffic from the tunnel address can only use
#      the tunnel routing table, and that table ends in a blackhole route;
#   2. creates the kernel WireGuard link from this node's Proton config;
#   3. sets the READY_LABEL on this node only while the tunnel passes traffic.
# The CiliumEgressGatewayPolicy selects gateways by that label. With no
# labelled gateway, Cilium drops the matched traffic instead of using the home IP.
set -euo pipefail

IFACE="${IFACE:-wg-proton}"
TABLE="${TABLE:-51820}"
RULE_PRIORITY="${RULE_PRIORITY:-90}"
MTU="${MTU:-1420}"
READY_LABEL="${READY_LABEL:-egress.vanillax.dev/vpn-ready}"
GATEWAY_NODES="${GATEWAY_NODES:?space-separated gateway node names}"
NODE_NAME="${NODE_NAME:?downward API spec.nodeName}"
CONF_DIR="${CONF_DIR:-/etc/proton}"
PROBE_URL="${PROBE_URL:-https://1.1.1.1/cdn-cgi/trace}"
INTERVAL="${INTERVAL:-15}"
FAILS_BEFORE_UNREADY="${FAILS_BEFORE_UNREADY:-3}"

CONF="${CONF_DIR}/${NODE_NAME}"
SA=/var/run/secrets/kubernetes.io/serviceaccount
API="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

kube() {
  local method=$1 path=$2
  shift 2
  curl -sS --fail --max-time 10 --cacert "$SA/ca.crt" \
    -H "Authorization: Bearer $(cat "$SA/token")" -X "$method" "$@" "$API$path"
}

set_label() {
  local node=$1 value=$2
  [[ $value == null ]] || value="\"$value\""
  kube PATCH "/api/v1/nodes/$node" -H 'Content-Type: application/merge-patch+json' \
    --data "{\"metadata\":{\"labels\":{\"$READY_LABEL\":$value}}}" >/dev/null
}

has_label() {
  jq -e --arg l "$READY_LABEL" '.metadata.labels[$l] == "true"' >/dev/null <<<"$1"
}

tunnel_addr() {
  # First IPv4 /32 on the Address line. IPv6 is never configured: pods are IPv4-only.
  grep -Ei '^[[:space:]]*Address[[:space:]]*=' "$CONF" | head -1 | cut -d= -f2 | tr ',' '\n' |
    tr -d ' ' | grep -E '^[0-9.]+/32$' | head -1
}

setup() {
  local addr=$1
  # Kill switch first, so it exists before the tunnel can carry anything.
  ip rule show | grep -q "^${RULE_PRIORITY}:[[:space:]]*from ${addr%/32} lookup ${TABLE}" ||
    ip rule add priority "$RULE_PRIORITY" from "$addr" lookup "$TABLE"
  ip route replace blackhole default metric 4096 table "$TABLE"

  local created=0
  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    ip link add "$IFACE" type wireguard
    created=1
  fi
  # wg setconf takes only the WireGuard keys; drop the wg-quick-only lines.
  wg setconf "$IFACE" <(grep -Eiv '^[[:space:]]*(Address|DNS|MTU|Table|PreUp|PostUp|PreDown|PostDown|SaveConfig)[[:space:]]*=' "$CONF")
  ip address replace "$addr" dev "$IFACE"
  ip link set "$IFACE" mtu "$MTU" up
  local peer
  peer=$(wg show "$IFACE" peers | head -1)
  wg set "$IFACE" peer "$peer" persistent-keepalive 25
  ip route replace default dev "$IFACE" table "$TABLE"
  log "tunnel $IFACE up as $addr (new link: $created)"
}

probe() {
  # Bind to the tunnel address: the ip rule sends it through the tunnel or the blackhole.
  curl -fsS --max-time 5 --interface "${1%/32}" "$PROBE_URL" | grep -E '^ip=' || return 1
}

reap_dead_peers() {
  # A powered-off gateway cannot remove its own label. Remove it for NotReady peers.
  local node json
  for node in $GATEWAY_NODES; do
    [[ $node == "$NODE_NAME" ]] && continue
    json=$(kube GET "/api/v1/nodes/$node") || continue
    has_label "$json" || continue
    if ! jq -e '.status.conditions[] | select(.type=="Ready") | .status == "True"' >/dev/null <<<"$json"; then
      log "peer $node is NotReady; removing $READY_LABEL"
      set_label "$node" null || true
    fi
  done
}

on_term() {
  log "stopping; removing $READY_LABEL (tunnel and kill switch stay in place)"
  set_label "$NODE_NAME" null || true
  exit 0
}
trap on_term TERM INT

[[ -r $CONF ]] || { log "no Proton config for $NODE_NAME at $CONF"; exit 1; }
ADDR=$(tunnel_addr)
[[ -n $ADDR ]] || { log "no IPv4 /32 Address in $CONF"; exit 1; }

# Cilium caches the egress interface. Unlabel first, so the later relabel makes it re-read the link.
set_label "$NODE_NAME" null
setup "$ADDR"
conf_sum=$(sha256sum "$CONF" | cut -d' ' -f1)
fails=0

while true; do
  new_sum=$(sha256sum "$CONF" | cut -d' ' -f1)
  if [[ $new_sum != "$conf_sum" ]] || ! ip link show "$IFACE" >/dev/null 2>&1; then
    log "config changed or link missing; rebuilding"
    set_label "$NODE_NAME" null || true
    ADDR=$(tunnel_addr)
    setup "$ADDR"
    conf_sum=$new_sum
  fi

  self=$(kube GET "/api/v1/nodes/$NODE_NAME") || self='{}'
  if exit_ip=$(probe "$ADDR"); then
    fails=0
    if ! has_label "$self"; then
      log "tunnel healthy ($exit_ip); setting $READY_LABEL"
      set_label "$NODE_NAME" true || true
    fi
  else
    fails=$((fails + 1))
    log "probe failed ($fails/$FAILS_BEFORE_UNREADY)"
    if ((fails >= FAILS_BEFORE_UNREADY)) && has_label "$self"; then
      log "tunnel unhealthy; removing $READY_LABEL"
      set_label "$NODE_NAME" null || true
    fi
  fi

  reap_dead_peers
  sleep "$INTERVAL" &
  wait $!
done
