#!/bin/sh
# Logs one line per node boot saying whether the previous boot ended cleanly.
# State lives on the node in /state (hostPath), so it survives reboots.
set -u
S=/state
mkdir -p "$S"

node="${NODE_NAME:-unknown}"
boot_id=$(cat /proc/sys/kernel/random/boot_id)
prev_boot=$(cat "$S/boot_id" 2>/dev/null || echo "")
clean_boot=$(cat "$S/clean" 2>/dev/null || echo "")
last_seen=$(cat "$S/last_seen" 2>/dev/null || echo 0)
now=$(date +%s)
uptime=$(cut -d. -f1 /proc/uptime)

# A watchdog that fired leaves WDIOF_CARDRESET (0x20) in bootstatus.
watchdog=none
for w in /sys/class/watchdog/watchdog*; do
  [ -r "$w/bootstatus" ] || continue
  bs=$(cat "$w/bootstatus")
  watchdog="$(basename "$w")=$bs"
  if [ $((bs & 32)) -ne 0 ]; then watchdog="$watchdog(fired)"; fi
done

if [ -z "$prev_boot" ]; then
  reason=first-run
elif [ "$prev_boot" = "$boot_id" ]; then
  reason=pod-restart
elif echo "$watchdog" | grep -q fired; then
  reason=watchdog
elif [ "$clean_boot" = "$prev_boot" ]; then
  reason=clean
else
  reason=unclean
fi

if [ "$last_seen" -gt 0 ]; then
  last_seen_at=$(date -u -d "@$last_seen" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "$last_seen")
else
  last_seen_at=unknown
fi

echo "{\"msg\":\"boot-reason\",\"node\":\"$node\",\"reason\":\"$reason\",\"previous_boot_last_seen\":\"$last_seen_at\",\"uptime_seconds\":$uptime,\"watchdog\":\"$watchdog\",\"boot_id\":\"$boot_id\",\"previous_boot_id\":\"$prev_boot\"}"

echo "$boot_id" > "$S/boot_id"
rm -f "$S/clean"

# Kubelet stops this pod during a planned shutdown; mark this boot as clean.
on_term() {
  echo "$boot_id" > "$S/clean"
  echo "{\"msg\":\"boot-reason-shutdown\",\"node\":\"$node\",\"boot_id\":\"$boot_id\"}"
  exit 0
}
trap on_term TERM INT

# Heartbeat: after a crash, the next boot reports the last time this node was alive.
while :; do
  date +%s > "$S/last_seen"
  sleep 30 &
  wait $!
done
