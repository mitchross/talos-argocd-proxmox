#!/usr/bin/env bash
# Proton WireGuard tunnel for one Cilium egress gateway node.
#
# Runs in the host network namespace of one gateway node. It:
#   1. sends traffic from the tunnel address only to the tunnel table, which ends in a
#      blackhole, so a packet SNATed to the tunnel address never leaves on the LAN NIC;
#   2. creates the kernel WireGuard link from this node's Proton config;
#   3. every INTERVAL, probes through the tunnel and writes health, exit IP, handshake
#      and byte counters to the ConfigMap vpn-gateway-<node>.
# The vpn-egress controller reads those ConfigMaps and picks the gateways for the
# CiliumEgressGatewayPolicy. This script never touches the policy or node labels.
# The tunnel lives in the kernel: it keeps forwarding while this pod restarts.
set -euo pipefail

IFACE="${IFACE:-wg-proton}"
TABLE="${TABLE:-51820}"
RULE_PRIORITY="${RULE_PRIORITY:-90}"
MTU="${MTU:-1420}"
NODE_NAME="${NODE_NAME:?downward API spec.nodeName}"
CONF_DIR="${CONF_DIR:-/etc/proton}"
PROBE_URL="${PROBE_URL:-https://1.1.1.1/cdn-cgi/trace}"
INTERVAL="${INTERVAL:-15}"
FAILS_BEFORE_DOWN="${FAILS_BEFORE_DOWN:-3}"
SA="${SA_DIR:-/var/run/secrets/kubernetes.io/serviceaccount}"
NAMESPACE="${NAMESPACE:-$(cat "$SA/namespace")}"
API="${KUBE_API:-https://${KUBERNETES_SERVICE_HOST:-}:${KUBERNETES_SERVICE_PORT:-}}"

CONF="${CONF_DIR}/${NODE_NAME}"
STATUS_CM="vpn-gateway-${NODE_NAME}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

kube() {
  local method=$1 path=$2 token
  shift 2
  token=$(cat "$SA/token")
  curl -sS --fail --max-time 10 --cacert "$SA/ca.crt" \
    -H "Authorization: Bearer ${token}" -X "$method" "$@" "$API$path"
}

tunnel_addr() {
  # First IPv4 /32 on the Address line. IPv6 is never configured: pods are IPv4-only.
  grep -Ei '^[[:space:]]*Address[[:space:]]*=' "$CONF" | head -1 | cut -d= -f2 | tr ',' '\n' |
    tr -d ' ' | grep -E '^[0-9.]+/32$' | head -1
}

setup() {
  local addr=$1
  # Source rule first, so it exists before the tunnel can carry anything.
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
  curl -fsS --max-time 5 --interface "${1%/32}" "$PROBE_URL" | sed -n 's/^ip=//p' | grep . || return 1
}

write_status() {
  local healthy=$1 exit_ip=$2 message=$3
  local handshake="" rx="" tx="" endpoint="" ifindex="" body
  handshake=$(wg show "$IFACE" latest-handshakes 2>/dev/null | awk 'NR==1 {print $2}') || true
  read -r rx tx < <(wg show "$IFACE" transfer 2>/dev/null | awk 'NR==1 {print $2, $3}') || true
  endpoint=$(wg show "$IFACE" endpoints 2>/dev/null | awk 'NR==1 {print $2}') || true
  # The controller puts the ifindex on the policy: a recreated link makes Cilium re-read it.
  ifindex=$(ip -o link show "$IFACE" 2>/dev/null | cut -d: -f1) || true
  body=$(jq -cn \
    --arg name "$STATUS_CM" --arg ns "$NAMESPACE" --arg node "$NODE_NAME" \
    --arg healthy "$healthy" --arg exit_ip "$exit_ip" --arg message "$message" \
    --arg handshake "${handshake:-0}" --arg rx "${rx:-0}" --arg tx "${tx:-0}" \
    --arg endpoint "${endpoint:-}" --arg ifindex "${ifindex:-0}" --arg updated "$(date +%s)" \
    '{apiVersion: "v1", kind: "ConfigMap",
      metadata: {name: $name, namespace: $ns,
                 labels: {"app.kubernetes.io/name": "vpn-egress", "app.kubernetes.io/component": "gateway-status"}},
      data: {node: $node, healthy: $healthy, exitIP: $exit_ip, message: $message,
             latestHandshake: $handshake, rxBytes: $rx, txBytes: $tx,
             endpoint: $endpoint, ifindex: $ifindex, updated: $updated}}')
  # Server-side apply creates the ConfigMap on the first run and updates it after.
  kube PATCH "/api/v1/namespaces/$NAMESPACE/configmaps/$STATUS_CM?fieldManager=vpn-gateway&force=true" \
    -H 'Content-Type: application/apply-patch+yaml' --data "$body" >/dev/null ||
    log "could not write status ConfigMap $STATUS_CM"
}

# Leave the tunnel and the last status in place: the kernel keeps forwarding while
# the pod restarts. The controller drops this gateway if the status goes stale.
sleep_pid=""
trap 'log "stopping; tunnel stays up"; [[ -z $sleep_pid ]] || kill "$sleep_pid" 2>/dev/null; exit 0' TERM INT

[[ -r $CONF ]] || { log "no Proton config for $NODE_NAME at $CONF"; exit 1; }
ADDR=$(tunnel_addr)
[[ -n $ADDR ]] || { log "no IPv4 /32 Address in $CONF"; exit 1; }

setup "$ADDR"
conf_sum=$(sha256sum "$CONF" | cut -d' ' -f1)
fails=0
healthy=false
exit_ip=""
rounds=0

while true; do
  new_sum=$(sha256sum "$CONF" | cut -d' ' -f1)
  # A link that went down also lost its routes; setup brings both back.
  if [[ $new_sum != "$conf_sum" ]] || ! ip -o link show "$IFACE" 2>/dev/null | grep -q '[<,]UP[,>]'; then
    log "config changed or link missing or down; rebuilding"
    ADDR=$(tunnel_addr)
    setup "$ADDR"
    conf_sum=$new_sum
  fi

  if ip=$(probe "$ADDR"); then
    fails=0
    [[ $healthy == true && $ip == "$exit_ip" ]] || log "tunnel healthy, exit IP $ip"
    healthy=true
    exit_ip=$ip
    message="probe ok"
  else
    fails=$((fails + 1))
    message="probe failed ($fails in a row)"
    log "$message"
    if ((fails >= FAILS_BEFORE_DOWN)) && [[ $healthy == true ]]; then
      log "tunnel unhealthy; reporting down"
      healthy=false
    fi
  fi

  write_status "$healthy" "$exit_ip" "$message"
  # Tests set MAX_ROUNDS to stop the loop; the DaemonSet never does.
  rounds=$((rounds + 1))
  if [[ -n ${MAX_ROUNDS:-} ]] && ((rounds >= MAX_ROUNDS)); then exit 0; fi
  sleep "$INTERVAL" &
  sleep_pid=$!
  wait "$sleep_pid"
done
