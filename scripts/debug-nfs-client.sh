#!/bin/bash
# NFS Client Debug for Talos/Proxmox setup
#
# Network path: TrueNAS 10G NIC → switch → Proxmox 10G NIC → vmbr → Talos VM
#
# Run this on the PROXMOX HOST (not inside Talos - it's immutable)
# This checks both the physical NIC layer AND queries Talos via talosctl
#
# Usage: bash debug-nfs-client.sh [talos-node-ip]
# Example: bash debug-nfs-client.sh 192.168.10.142

TRUENAS_IP="192.168.10.133"
TALOS_NODE="${1:-}"

echo "=========================================================="
echo " NFS Client 10G Debug (Proxmox + Talos)"
echo "=========================================================="

# =========================================================
# PART 1: PROXMOX HOST (physical layer)
# =========================================================
echo ""
echo "========== PART 1: PROXMOX HOST =========="
echo ""

echo "---> [1] PROXMOX NETWORK INTERFACES <---"
for iface in $(ip -o link show up | awk -F: '{print $2}' | tr -d ' ' | grep -v lo); do
  SPEED=$(ethtool "$iface" 2>/dev/null | grep "Speed:")
  MTU=$(ip link show "$iface" | grep -o 'mtu [0-9]*')
  TYPE=""
  if [[ "$iface" == vmbr* ]]; then TYPE="(bridge)"; fi
  if [[ "$iface" == eno* ]] || [[ "$iface" == enp* ]] || [[ "$iface" == ens* ]] || [[ "$iface" == eth* ]]; then TYPE="(physical)"; fi
  if [[ "$iface" == tap* ]] || [[ "$iface" == fwbr* ]] || [[ "$iface" == fwln* ]]; then TYPE="(VM tap)"; fi
  echo "  $iface: $SPEED  $MTU  $TYPE"
done
echo ""

echo "---> [2] BRIDGE CONFIG (which NIC backs vmbr) <---"
for br in $(ip -o link show type bridge 2>/dev/null | awk -F: '{print $2}' | tr -d ' '); do
  MEMBERS=$(bridge link show 2>/dev/null | grep "master $br" | awk '{print $2}')
  echo "  $br members: $MEMBERS"
done
echo ""

echo "---> [3] ROUTE TO TRUENAS <---"
ip route get $TRUENAS_IP 2>/dev/null
echo ""

echo "---> [4] PROXMOX NIC FLOW CONTROL <---"
IFACE=$(ip route get $TRUENAS_IP 2>/dev/null | grep -o 'dev [a-z0-9]*' | awk '{print $2}')
# If route goes through a bridge, find the physical NIC behind it
if [[ "$IFACE" == vmbr* ]]; then
  PHYS=$(bridge link show 2>/dev/null | grep "master $IFACE" | awk '{print $2}' | grep -v tap | grep -v fwbr | grep -v fwln | head -1)
  if [ -n "$PHYS" ]; then
    echo "  Bridge $IFACE backed by physical: $PHYS"
    IFACE="$PHYS"
  fi
fi
if [ -n "$IFACE" ]; then
  echo "  Flow control on $IFACE:"
  ethtool -a "$IFACE" 2>/dev/null | grep -E "RX|TX|Autoneg"
  echo ""
  echo "  Ring buffer on $IFACE:"
  ethtool -g "$IFACE" 2>/dev/null | grep -A5 "Current"
  echo ""
  echo "  Offloads on $IFACE:"
  ethtool -k "$IFACE" 2>/dev/null | grep -E "^(tcp-segmentation|generic-segmentation|generic-receive|rx-checksumming|tx-checksumming|scatter-gather)"
fi
echo ""

echo "---> [5] PROXMOX NIC ERROR COUNTERS <---"
if [ -n "$IFACE" ]; then
  ERRORS=$(ethtool -S "$IFACE" 2>/dev/null | grep -iE "drop|error|discard|pause|overflow|miss|crc|fcs" | grep -v ": 0$")
  if [ -n "$ERRORS" ]; then
    echo "  Non-zero error counters on $IFACE:"
    echo "$ERRORS"
  else
    echo "  All error counters zero on $IFACE (good)"
  fi
fi
echo ""

echo "---> [6] PROXMOX TCP RETRANSMIT RATE (5s) <---"
R1=$(cat /proc/net/snmp | grep "^Tcp:" | tail -1 | awk '{print $13}')
echo "  Sampling for 5 seconds..."
sleep 5
R2=$(cat /proc/net/snmp | grep "^Tcp:" | tail -1 | awk '{print $13}')
DELTA=$((R2 - R1))
echo "  Retransmits in 5s: $DELTA"
echo "  Cumulative: $R2"
echo ""

echo "---> [7] PROXMOX NETWORK THROUGHPUT (5s) <---"
NETIFACE=$(ip route get $TRUENAS_IP 2>/dev/null | grep -o 'dev [a-z0-9]*' | awk '{print $2}')
if [ -n "$NETIFACE" ]; then
  RX1=$(cat /sys/class/net/$NETIFACE/statistics/rx_bytes 2>/dev/null)
  TX1=$(cat /sys/class/net/$NETIFACE/statistics/tx_bytes 2>/dev/null)
  sleep 5
  RX2=$(cat /sys/class/net/$NETIFACE/statistics/rx_bytes 2>/dev/null)
  TX2=$(cat /sys/class/net/$NETIFACE/statistics/tx_bytes 2>/dev/null)
  RX_RATE=$(( (RX2 - RX1) / 5 / 1024 / 1024 ))
  TX_RATE=$(( (TX2 - TX1) / 5 / 1024 / 1024 ))
  echo "  $NETIFACE - RX: ${RX_RATE} MB/s  TX: ${TX_RATE} MB/s"
fi
echo ""

echo "---> [8] VM NIC TYPE (virtio vs e1000) <---"
echo "  Checking QEMU VMs for NIC model..."
for VMID in $(qm list 2>/dev/null | awk 'NR>1{print $1}'); do
  NET=$(qm config $VMID 2>/dev/null | grep "^net" | head -3)
  NAME=$(qm config $VMID 2>/dev/null | grep "^name:" | awk '{print $2}')
  if [ -n "$NET" ]; then
    echo "  VM $VMID ($NAME):"
    echo "    $NET"
    # Check for multiqueue
    if echo "$NET" | grep -q "queues="; then
      echo "    (multiqueue enabled)"
    else
      echo "    WARNING: no multiqueue - add queues=4 for 10G"
    fi
  fi
done
echo ""

# =========================================================
# PART 2: TALOS NODE (via talosctl)
# =========================================================
if [ -z "$TALOS_NODE" ]; then
  echo "========== PART 2: TALOS NODE (skipped - no node IP given) =========="
  echo "  Re-run with: bash $0 <talos-node-ip>"
  echo "  Example: bash $0 192.168.10.142"
  echo ""
else
  echo "========== PART 2: TALOS NODE ($TALOS_NODE) =========="
  echo ""

  echo "---> [9] TALOS NFS MOUNTS <---"
  talosctl -n "$TALOS_NODE" read /proc/mounts 2>/dev/null | grep nfs
  echo ""

  echo "---> [10] TALOS NFS CONNECTIONS TO TRUENAS <---"
  talosctl -n "$TALOS_NODE" netstat 2>/dev/null | grep ":2049" | head -30
  NCONN=$(talosctl -n "$TALOS_NODE" netstat 2>/dev/null | grep ":2049" | grep ESTABLISHED | wc -l)
  echo "  Total NFS connections: $NCONN"
  echo "  (nconnect=16 per mount = expect 16 connections per NFS share)"
  echo ""

  echo "---> [11] TALOS NETWORK INTERFACES <---"
  talosctl -n "$TALOS_NODE" get addresses 2>/dev/null
  echo ""

  echo "---> [12] TALOS TCP STATS <---"
  talosctl -n "$TALOS_NODE" read /proc/net/snmp 2>/dev/null | grep -E "^Tcp"
  echo ""
fi

echo "=========================================================="
echo " Done. Paste output back!"
echo "=========================================================="
