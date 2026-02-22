#!/bin/bash
# Run on TrueNAS via SSH: sudo bash debug-nfs-server.sh
# Best results: run DURING an active NFS transfer
echo "=========================================================="
echo " TrueNAS NFS 10G Debug Script"
echo "=========================================================="

echo ""
echo "---> [1] NFS SERVER THREADS <---"
THREADS=$(cat /proc/fs/nfsd/threads)
echo "Threads: $THREADS"
if [ "$THREADS" -lt 64 ]; then
  echo "  WARNING: Only $THREADS threads. Recommend 128 for 10G."
  echo "  Fix: TrueNAS UI > Shares > NFS > Settings > Servers = 128"
fi
echo ""

echo "---> [2] NFS EXPORTS & OPTIONS <---"
exportfs -v 2>/dev/null
echo ""

echo "---> [3] ZFS DATASET RECORDSIZE (AI model datasets) <---"
zfs get recordsize,compression,atime,primarycache -t filesystem BigTank 2>/dev/null
echo ""
echo "AI/model datasets:"
zfs get recordsize -t filesystem -r BigTank 2>/dev/null | grep -E "k8s|model|llm|ai|ollama|comfy"
echo ""

echo "---> [4] NETWORK INTERFACE CONFIG <---"
for iface in $(ip -o link show up | awk -F: '{print $2}' | tr -d ' ' | grep -v lo); do
  SPEED=$(ethtool "$iface" 2>/dev/null | grep "Speed:")
  RING_RX=$(ethtool -g "$iface" 2>/dev/null | grep -A4 "Current" | grep "RX:" | head -1)
  MTU=$(ip link show "$iface" | grep -o 'mtu [0-9]*')
  if [ -n "$SPEED" ]; then
    echo "  $iface: $SPEED  $MTU  $RING_RX"
  fi
done
echo ""

echo "---> [5] FLOW CONTROL (pause frames) <---"
for iface in $(ip -o link show up | awk -F: '{print $2}' | tr -d ' ' | grep -v lo); do
  SPEED=$(ethtool "$iface" 2>/dev/null | grep "Speed:" | grep -v Unknown)
  if [ -n "$SPEED" ]; then
    echo "  $iface:"
    ethtool -a "$iface" 2>/dev/null | grep -E "RX|TX|Autoneg"
  fi
done
echo ""

echo "---> [6] ACTIVE NFS CONNECTIONS <---"
ss -tn state established '( sport = :2049 )' | head -40
echo "Total NFS connections: $(ss -tn state established '( sport = :2049 )' | tail -n+2 | wc -l)"
echo ""

echo "---> [7] NFS NETWORK THROUGHPUT (5s sample) <---"
IFACE=$(ip route get 192.168.10.1 2>/dev/null | grep -o 'dev [a-z0-9]*' | awk '{print $2}')
if [ -z "$IFACE" ]; then IFACE=$(ip -o link show up | awk -F: 'NR==2{print $2}' | tr -d ' '); fi
echo "Monitoring interface: $IFACE"
RX1=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null)
TX1=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null)
sleep 5
RX2=$(cat /sys/class/net/$IFACE/statistics/rx_bytes 2>/dev/null)
TX2=$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null)
RX_RATE=$(( (RX2 - RX1) / 5 / 1024 / 1024 ))
TX_RATE=$(( (TX2 - TX1) / 5 / 1024 / 1024 ))
echo "  RX: ${RX_RATE} MB/s   TX: ${TX_RATE} MB/s"
echo "  (10G max: ~1100 MB/s)"
echo ""

echo "---> [8] ZFS ARC & POOL BANDWIDTH (5s) <---"
arcstat 5 1 2>/dev/null || echo "(arcstat not available)"
echo ""
zpool iostat BigTank 5 1 2>/dev/null
echo ""

echo "---> [9] NFSD CPU & THREAD UTILIZATION <---"
ps -eo pid,nlwp,pcpu,pmem,comm | grep -E "nfsd|PID" | head -40
echo ""

echo "---> [10] TCP RETRANSMIT RATE (5s delta) <---"
R1=$(cat /proc/net/snmp | grep "^Tcp:" | tail -1 | awk '{print $13}')
sleep 5
R2=$(cat /proc/net/snmp | grep "^Tcp:" | tail -1 | awk '{print $13}')
DELTA=$((R2 - R1))
echo "  Retransmits in 5s: $DELTA (should be near 0 on healthy 10G)"
echo "  Cumulative: $R2"
echo ""

echo "---> [11] NIC ERROR COUNTERS <---"
IFACE=$(ip route get 192.168.10.1 2>/dev/null | grep -o 'dev [a-z0-9]*' | awk '{print $2}')
if [ -n "$IFACE" ]; then
  ERRORS=$(ethtool -S "$IFACE" 2>/dev/null | grep -iE "drop|error|discard|pause|overflow|miss|crc|fcs" | grep -v ": 0$")
  if [ -n "$ERRORS" ]; then
    echo "  Non-zero error counters on $IFACE:"
    echo "$ERRORS"
  else
    echo "  No error counters on $IFACE (all zero - good)"
  fi
fi
echo ""

echo "---> [12] DISK UTILIZATION (1s snapshot) <---"
iostat -xd 1 1 2>/dev/null | grep -E "Device|sd" | head -20
echo ""

echo "=========================================================="
echo " Done. Paste output back!"
echo "=========================================================="
