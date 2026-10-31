#!/usr/bin/env bash
# radar-ng only: wait for a ghcr-backend release run, then open the talos PR that bumps every backend ref.
# Reads tag@digest from the run's `published` annotations, checks each against the registry,
# rewrites all radar-ng-{tile-server,temporal-worker,open-meteo-worker} refs, renders with kustomize.
# Usage: bump_radar_backend.sh <ghcr-backend run id> <ci-rust run id> <radar-ng merge sha> <radar-ng PR number>
set -u
R=mitchross/radar-ng; T=mitchross/talos-argocd-proxmox
RUN=$1; CI=$2; SHA=$3; SRCPR=$4
gh run watch "$RUN" -R $R --interval 60 --exit-status >/dev/null 2>&1 || { echo "BACKEND RUN FAILED"; exit 1; }
gh run watch "$CI" -R $R --interval 60 --exit-status >/dev/null 2>&1 || echo "WARN ci-rust not green"
declare -A D; NEW=""
for j in $(gh api repos/$R/actions/runs/$RUN/jobs --jq '.jobs[].id'); do
  while read -r ref; do
    [ -z "$ref" ] && continue
    img=${ref#ghcr.io/mitchross/radar-ng-}; img=${img%%:*}
    tag=${ref#*:}; tag=${tag%%@*}; NEW=$tag
    D[$img]=${ref#*@}
  done < <(gh api repos/$R/check-runs/$j/annotations --jq '.[]|select(.title=="published")|.message' 2>/dev/null)
done
[ ${#D[@]} -eq 3 ] || { echo "expected 3 images, got ${#D[@]}"; exit 1; }
echo "NEW=$NEW"; for k in "${!D[@]}"; do echo "  $k ${D[$k]}"; done
ACCEPT="application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json"
for img in "${!D[@]}"; do
  repo=mitchross/radar-ng-$img
  tok=$(curl -fsS "https://ghcr.io/token?scope=repository:$repo:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
  got=$(curl -fsSI -H "Authorization: Bearer $tok" -H "Accept: $ACCEPT" "https://ghcr.io/v2/$repo/manifests/$NEW" | tr -d '\r' | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}')
  [ "$got" = "${D[$img]}" ] && echo "registry ok $img" || { echo "MISMATCH $img $got"; exit 1; }
done
BR=chore/radar-ng-backend-$NEW; WT=/opt/data/workspace/wt-radar-ng-$NEW
cd /opt/data/workspace/talos-argocd-proxmox && git fetch -q origin && git worktree add -q -b "$BR" "$WT" origin/main || exit 1
cd "$WT/my-apps/personal-projects/radar-ng"
for img in "${!D[@]}"; do
  grep -rlE "radar-ng-$img:v[0-9.]+@" . | xargs sed -i -E "s#radar-ng-$img:v[0-9.]+@sha256:[0-9a-f]{64}#radar-ng-$img:$NEW@${D[$img]}#g"
done
OUT=$(kubectl kustomize .)
echo "new refs: $(grep -cE "radar-ng-(tile-server|temporal-worker|open-meteo-worker):$NEW@" <<<"$OUT")"
echo "other refs: $(grep -E "radar-ng-(tile-server|temporal-worker|open-meteo-worker):v" <<<"$OUT" | grep -vc ":$NEW@" || true)"
cd "$WT"
BODY=${TMPDIR:-/opt/data/cache/scratch}/talos-radar-ng-$NEW-body.md
cat > "$BODY" <<EOF
Bumps the radar-ng backend images to $NEW (radar-ng ${SHA:0:7}, PR mitchross/radar-ng#$SRCPR).

| Image | Refs |
|---|---|
| temporal-worker | 5 worker pools |
| open-meteo-worker | serve + sync sidecar |
| tile-server | 1 |

Checks: each \`tag@digest\` comes from the release run's \`published\` annotations and matches the registry. \`kubectl kustomize\` renders every backend ref on $NEW. Web is unchanged.

Rollback: revert this PR. The worker pools smoke-test each new version before traffic moves.
EOF
git commit -q --only my-apps/personal-projects/radar-ng -m "chore(radar-ng): bump backend images to $NEW" && git show --stat HEAD | tail -1
git push -q -u origin "$BR" 2>&1 | tail -1
gh pr create -R $T --base main --head "$BR" --title "chore(radar-ng): bump backend images to $NEW" --body-file "$BODY"
