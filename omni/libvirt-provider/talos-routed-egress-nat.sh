#!/usr/bin/env bash

set -eu

readonly CHAIN="TALOS_ROUTED_EGRESS"
readonly SOURCE_CIDR="192.168.123.0/24"
readonly EGRESS_INTERFACE="wlan0"

start() {
  iptables -t nat -N "${CHAIN}" 2>/dev/null || true
  iptables -t nat -F "${CHAIN}"

  # Preserve routed homelab and Kubernetes traffic. Only public destinations
  # are masqueraded behind the CachyOS host's Wi-Fi address.
  iptables -t nat -A "${CHAIN}" -d 10.0.0.0/8 -j RETURN
  iptables -t nat -A "${CHAIN}" -d 172.16.0.0/12 -j RETURN
  iptables -t nat -A "${CHAIN}" -d 192.168.0.0/16 -j RETURN
  iptables -t nat -A "${CHAIN}" -j MASQUERADE

  if ! iptables -t nat -C POSTROUTING -s "${SOURCE_CIDR}" -o "${EGRESS_INTERFACE}" -j "${CHAIN}" 2>/dev/null; then
    iptables -t nat -I POSTROUTING 1 -s "${SOURCE_CIDR}" -o "${EGRESS_INTERFACE}" -j "${CHAIN}"
  fi
}

stop() {
  while iptables -t nat -C POSTROUTING -s "${SOURCE_CIDR}" -o "${EGRESS_INTERFACE}" -j "${CHAIN}" 2>/dev/null; do
    iptables -t nat -D POSTROUTING -s "${SOURCE_CIDR}" -o "${EGRESS_INTERFACE}" -j "${CHAIN}"
  done

  iptables -t nat -F "${CHAIN}" 2>/dev/null || true
  iptables -t nat -X "${CHAIN}" 2>/dev/null || true
}

case "${1:-}" in
  start)
    start
    ;;
  stop)
    stop
    ;;
  restart)
    stop
    start
    ;;
  *)
    echo "usage: $0 {start|stop|restart}" >&2
    exit 2
    ;;
esac
