#!/bin/sh
# Lists volume content that neither Git nor the image installs. Informational: it never deletes.
H="${HERMES_HOME:-/opt/data}"
G=/etc/hermes-scripts
report() { echo "[drift] $1: ${2:-none}"; }

# Prints the names in directory $1 that do not match the extended regex $2.
unlisted() { for e in "$1"/*; do [ -e "$e" ] && ! printf '%s\n' "${e##*/}" | grep -Eq "$2" && printf '%s ' "${e##*/}"; done; }

# Keep these lists equal to what seed.sh installs.
report "tools outside the image" "$(unlisted "$H/tools" '^(rustup|craft-anything-.*)$')"
report "plugins the seed does not install" "$(unlisted "$H/plugins" '^(hindsight|homeassistant|advanced-delegation)$')"
report "cron scripts missing from Git" "$(for f in "$H"/scripts/*; do
  [ -f "$f" ] && [ ! -f "$G/cron-${f##*/}" ] && printf '%s ' "${f##*/}"; done)"
report "cron scripts that differ from Git" "$(for f in "$G"/cron-*.py; do
  n="${f##*/cron-}"; [ -f "$H/scripts/$n" ] && ! cmp -s "$f" "$H/scripts/$n" && printf '%s ' "$n"; done)"
report "cron jobs missing from Git" "$(grep -o '"name": *"[^"]*"' "$H/cron/jobs.json" 2>/dev/null | cut -d'"' -f4 | while read -r n; do
  [ "$n" = homelab-digest ] || grep -qs "^$n|" "$G/cron-jobs.txt" || printf '%s; ' "$n"; done)"
